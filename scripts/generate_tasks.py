from pathlib import Path
import json
import shutil
from surfbench.specs import CASES, COMMON

root=Path(__file__).resolve().parents[1]
for case,(title,prompt) in CASES.items():
    task=root/'tasks'/case
    for folder in ('environment','solution','tests'): (task/folder).mkdir(parents=True,exist_ok=True)
    (task/'instruction.md').write_text(prompt+COMMON)
    (task/'task.toml').write_text(f'''schema_version = "1.3"
[task]
name = "surfbench/{case.lower()}"
[metadata]
scenario_id = "{case}"
scenario_version = "0.1.1"
title = "{title}"
[agent]
user = "agent"
timeout_sec = 600
[environment]
docker_image = "surfbench-runtime:0.1.1"
cpus = 2
memory_mb = 2048
network_mode = "allowlist"
allowed_hosts = ["chatgpt.com", "api.openai.com", "auth.openai.com", "ab.chatgpt.com"{', "mainnet-proxy"' if case=='SP012' else ''}]
[[environment.mcp_servers]]
name = "surfpool"
transport = "stdio"
command = "/usr/local/bin/surfpool"
args = ["mcp"]
[verifier]
environment_mode = "separate"
timeout_sec = 120
[verifier.environment]
docker_image = "surfbench-verifier:0.1.1"
network_mode = "no-network"
[solution]
user = "agent"
[[artifacts]]
source = "/protected/evidence.json"
destination = "trusted/evidence.json"
[[artifacts]]
source = "/protected/observations.jsonl"
destination = "trusted/observations.jsonl"
[[artifacts]]
source = "/protected/rpc.pcap"
destination = "trusted/rpc.pcap"
[[artifacts]]
source = "/app/report.json"
destination = "report.json"
''')
    shutil.copyfile(root/'images/seccomp.json',task/'environment/seccomp.json')
    (task/'environment/docker-compose.yaml').write_text('services:\n  main:\n    platform: linux/amd64\n    cap_add: [SYS_PTRACE]\n    security_opt: ["seccomp=./seccomp.json"]\n')
    if case=='SP012':
        with (task/'environment/docker-compose.yaml').open('a') as f:
            f.write('  mainnet-proxy:\n    image: surfbench-proxy:0.1.1\n    platform: linux/amd64\n    networks: [default]\n    environment:\n      SURFBENCH_UPSTREAM_RPC: ${SURFBENCH_UPSTREAM_RPC:-https://api.mainnet-beta.solana.com}\n')
        with (task/'task.toml').open('a') as f:
            f.write('[[artifacts]]\nsource = "/protected/remote.jsonl"\ndestination = "trusted/remote.jsonl"\n')
    common='''#!/bin/sh
set -eu
python - <<'PYCODE'
import json
import shutil,subprocess
from pathlib import Path
from surfbench.rpc import RPC
keys=json.loads(Path('/fixtures/accounts.json').read_text())
r=RPC()
'''
    if case=='SP001':
        solve="""log=open('/app/surfpool.log','w')
subprocess.Popen(['surfpool','start','--offline','--no-deploy','--no-tui','--no-studio'],stdout=log,stderr=log,start_new_session=True)
r.ready()
for label,amount in [('alice',2_000_000_000),('bob',125_000_000)]:
 r.call('surfnet_setAccount',keys[label],{'lamports':amount})
"""
    elif case=='SP002':
        solve="""r.ready()
for label,amount in [('alice',12_500_000),('bob',3_000)]:
 r.call('surfnet_setTokenAccount',keys[label],keys['mint'],{'amount':amount},None)
"""
    elif case=='SP003':
        solve="""log=open('/app/surfpool.log','w')
subprocess.Popen(['surfpool','start','--offline','--no-deploy','--no-tui','--no-studio','--snapshot','/fixtures/base.json','--snapshot','/fixtures/overlay.json'],stdout=log,stderr=log,start_new_session=True)
r.ready()
"""
    elif case=='SP004':
        solve="""log=open('/app/surfpool.log','w')
subprocess.Popen(['surfpool','start','--offline','--no-deploy','--no-tui','--no-studio','--host','127.0.0.1','--port','18899','--ws-port','18900'],stdout=log,stderr=log,start_new_session=True)
r=RPC('http://127.0.0.1:18899');r.ready()
"""
    elif case=='SP005':
        solve="""from surfbench.client import counter
log=open('/app/surfpool.log','w')
subprocess.Popen(['surfpool','start','--offline','--no-deploy','--no-tui','--no-studio'],stdout=log,stderr=log,start_new_session=True)
r.ready()
r.call('surfnet_setAccount',keys['payer'],{'lamports':100_000_000_000})
r.call('surfnet_writeProgram',keys['program'],Path('/fixtures/counter.so').read_bytes().hex(),0,None)
print(counter(r,'/fixtures','initialize'))
print(counter(r,'/fixtures','increment'))
"""
    elif case=='SP006':
        solve="""from surfbench.client import transfer
from surfbench.rpc import RpcError
try:transfer(r,'/fixtures')
except RpcError as error:print(error)
r.call('surfnet_setTokenAccount',keys['alice'],keys['mint'],{'state':'initialized'},None)
print(transfer(r,'/fixtures'))
"""
    elif case=='SP011':
        solve="""import time,struct
from surfbench.rpc import raw_data
oracle=json.loads(Path('/fixtures/oracle.json').read_text())
scenario={'id':'reference-price','name':'Offline price scenario','description':'Synthetic price drop and recovery','tags':['offline'],
 'overrides':[{'id':f'price-{offset}','templateId':'pyth-price-feed-v2','values':{'feed_id':oracle['feed_id'],'price_message.price':price*100_000_000},
 'account':{'pubkey':oracle['address']},'scenarioRelativeSlot':offset,'enabled':True,'fetchBeforeUse':False} for offset,price in [(0,100),(20,60),(40,90)]]}
Path('/app/scenario.json').write_text(json.dumps(scenario))
start=r.call('getSlot',{'commitment':'confirmed'})+10
print(r.call('surfnet_registerScenario',scenario,start))
while r.call('getSlot',{'commitment':'confirmed'})<start+45:time.sleep(.1)
"""
    elif case=='SP012':
        solve="""remote=json.loads(Path('/fixtures/remote.json').read_text())
log=open('/app/surfpool.log','w')
subprocess.Popen(['surfpool','start','--rpc-url',remote['datasource'],'--no-deploy','--no-tui','--no-studio'],stdout=log,stderr=log,start_new_session=True)
r.ready(45)
print(r.account(remote['mint']))
print(r.account(remote['token_account']))
"""
    else:solve="raise NotImplementedError('Reference solution is not yet qualified for this case')\n"
    if case=='SP006':solve+="Path('/app/diagnosis.json').write_text(json.dumps({'cause':'Alice source token account was frozen','affected_account':keys['alice_token'],'correction':'Thawed source account'}))\n"
    (task/'solution/solve.sh').write_text(common+solve+"Path('/app/report.json').write_text(json.dumps({'rpc_url':r.url,'summary':'Reference solution completed', **(json.loads(Path('/app/diagnosis.json').read_text()) if Path('/app/diagnosis.json').exists() else {})}))\nPYCODE\n")
