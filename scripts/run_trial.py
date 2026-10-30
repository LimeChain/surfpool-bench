"""Harbor runner with trusted pre-teardown collection. Required entrypoint for this suite."""
import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import platform
import importlib.metadata
import re
import shutil
from pathlib import Path
from harbor.models.trial.config import TrialConfig
from harbor.trial.trial import Trial
from harbor.trial.hooks import TrialEvent

ROOT=Path(__file__).resolve().parents[1]

async def main(args):
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.run):raise ValueError('Run name must contain only letters, digits, hyphens and underscores')
    if args.case == 'SP005':
        from build_counter import ensure_counter
        ensure_counter()
    trial_dir=ROOT/'runs'/args.run
    if (trial_dir/(args.case.lower()+'-'+args.agent)).exists():raise FileExistsError('Use a new run name; existing evidence must not be overwritten')
    from surfbench.fixture_store import validate_saved, copy_saved
    fixture_store=ROOT/'fixtures/variants'
    validate_saved(fixture_store,args.seed)
    task_root=ROOT/'tasks';extra_options={};profile=None
    agent_env={} if args.agent=='oracle' else {'CODEX_FORCE_AUTH_JSON':'1'}
    if args.profile=='ogi':
        if args.agent!='codex':raise ValueError('Ogi profile requires the Codex harness')
        from ogi_profile import runtime_options
        extra_options,profile=runtime_options(args.model)
        task_root=ROOT/'tasks-ogi'
        agent_env={'CODEX_FORCE_AUTH_JSON':'0','CODEX_AUTH_JSON_PATH':''}
    config=TrialConfig.model_validate({
        'task':{'path':task_root/args.case},'trial_name':args.case.lower()+'-'+args.agent,
        'trials_dir':trial_dir,'environment':{'type':'docker','import_path':'surfbench.docker_environment:SurfbenchDockerEnvironment','delete':True},
        'agent':{'name':args.agent,'model_name':None if args.agent=='oracle' else args.model,
                 'kwargs':{} if args.agent=='oracle' else {'version':'0.155.1','reasoning_effort':'high','disable_web_search':True,**extra_options},
                 'env':agent_env}})
    trial=await Trial.create(config)
    env=trial.agent_environment
    bundle=trial.paths.trial_dir/'controller-code';bundle.mkdir()
    for name in ('observe.py','capture.py','challenges.py','sentinel.py','scenario_check.py'):
        shutil.copyfile(ROOT/'src/surfbench'/name,bundle/name)
    fixture_root=trial.paths.trial_dir/'fixtures-generated'
    fixture_source=copy_saved(fixture_store,args.seed,fixture_root)
    image_names=['surfbench-runtime:0.1.1','surfbench-verifier:0.1.1','surfbench-egress:0.1.1']+(['surfbench-proxy:0.1.1'] if args.case=='SP012' else [])
    images=json.loads(subprocess.check_output(['docker','image','inspect',*image_names],text=True))
    manifest={'case':args.case,'seed':args.seed,'fixture_source':fixture_source,'agent':args.agent,'model':args.model if args.agent=='codex' else None,
        'reasoning_effort':'high','agent_timeout_sec':600,'token_cap':None,'token_cap_enforced':False,
        'harbor_version':importlib.metadata.version('harbor'),'host_platform':platform.platform(),
        'image_ids':{name:info['Id'] for name,info in zip(image_names,images)},
        'controller_bundle_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in bundle.iterdir()},
        'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for directory in ('src','docs','scripts','images') for p in (ROOT/directory).rglob('*') if p.is_file() and '__pycache__' not in str(p) and p.suffix not in ('.gz','.pyc')},
        'task_sha256':hashlib.sha256((task_root/args.case/'instruction.md').read_bytes()).hexdigest(),
        'task_config_sha256':hashlib.sha256((task_root/args.case/'task.toml').read_bytes()).hexdigest(),
        'provider_profile':profile,
        'skills':[],'model_web_search':'disabled','authentication':(profile['authentication'] if profile else 'existing Codex ChatGPT login; scoped temporary forwarding') if args.agent=='codex' else None}
    (trial.paths.trial_dir/'run-manifest.json').write_text(json.dumps(manifest,indent=2))

    async def setup(event):
        result=await env.exec(command='mkdir -p /fixtures /protected && chmod 700 /protected && chmod 755 /fixtures',user='root')
        if result.return_code:raise RuntimeError(str(result.stdout)+str(result.stderr))
        names=['accounts.json','payer-keypair.json']
        if args.case in ('SP002','SP011'):names+=['setup.json','alice-keypair.json','bob-keypair.json']
        if args.case=='SP006':names+=['diagnosis.json','alice-keypair.json','bob-keypair.json']
        if args.case=='SP011':names+=['oracle.json']
        if args.case=='SP003':names+=['base.json','overlay.json']
        if args.case=='SP005':names+=['program-keypair.json','counter-keypair.json']
        if args.case=='SP012':await env.upload_file(ROOT/'fixtures/remote.json','/fixtures/remote.json')
        for name in names:await env.upload_file(fixture_root/name,'/fixtures/'+name)
        for name in ('observe.py','capture.py','challenges.py','sentinel.py','scenario_check.py'):await env.upload_file(bundle/name,'/protected/'+name)
        if args.case=='SP005':
            for name in ('counter.so','counter.c','counter-abi.json'):
                await env.upload_file(ROOT/'fixtures'/name,'/fixtures/'+name)
        if args.case=='SP004':
            import secrets
            token=secrets.token_hex(24)
            await env.exec(command=f"printf %s {token} >/protected/sentinel-token; nohup python /protected/sentinel.py >/protected/sentinel.log 2>&1 </dev/null &",user='root')
        if args.case in ('SP002','SP006','SP011'):
            snapshot='diagnosis.json' if args.case=='SP006' else 'setup.json'
            await env.exec(command=f"nohup surfpool start --offline --no-deploy --no-tui --no-studio --snapshot /fixtures/{snapshot} >/app/surfpool.log 2>&1 </dev/null &",user='agent')
            ready=await env.exec(command="python -c 'from surfbench.rpc import RPC;RPC().ready()'",user='root')
            if ready.return_code:raise RuntimeError(ready.stderr)
        addresses=json.loads((fixture_root/'accounts.json').read_text())
        if args.case=='SP012':
            remote=json.loads((ROOT/'fixtures/remote.json').read_text())
            addresses={k:remote[k] for k in ('mint','token_account')}
        keys=list(dict.fromkeys(addresses.values()))
        spec={'case':args.case,'addresses':addresses,'keys':keys,
              'rpc':'http://127.0.0.1:'+('18899' if args.case=='SP004' else '8899')}
        if args.case=='SP012':spec['datasource']=remote['datasource']
        if args.case=='SP004':spec.update(sentinel_url='http://127.0.0.1:8899',sentinel_token=token)
        if args.case=='SP003':
            spec['expected_snapshot']=json.loads((fixture_root/'base.json').read_text())|json.loads((fixture_root/'overlay.json').read_text())
        temp=trial.paths.trial_dir/'observer-spec.json';temp.write_text(json.dumps(spec))
        await env.upload_file(temp,'/protected/spec.json')
        result=await env.exec(command='''python - <<'PYCODE'
import json,hashlib
from pathlib import Path
from surfbench.rpc import RPC
p=Path('/protected/spec.json');spec=json.loads(p.read_text())
spec['surfpool_sha256']=hashlib.sha256(Path('/usr/local/bin/surfpool').read_bytes()).hexdigest()
spec['initial_hashes']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/fixtures').rglob('*') if p.is_file()}
spec['initial_accounts']={}
if spec['case'] in ('SP002','SP006','SP011'):
 r=RPC(spec['rpc']); values=r.call('getMultipleAccounts',spec['keys'],{'encoding':'base64','commitment':'confirmed'})['value']
 spec['initial_accounts']=dict(zip(spec['keys'],values))
p.write_text(json.dumps(spec))
PYCODE''',user='root')
        if result.return_code:raise RuntimeError(str(result.stdout)+str(result.stderr))

    async def observe(event):
        result=await env.exec(command="nohup tcpdump -i lo -nn -U --immediate-mode -B 8192 -s 0 -w /protected/rpc.pcap 'tcp port 8899 or tcp port 18899' >/protected/tcpdump.log 2>&1 </dev/null & echo $! >/protected/tcpdump.pid",user='root')
        if result.return_code:raise RuntimeError(str(result.stdout)+str(result.stderr))
        result=await env.exec(command='nohup python /protected/observe.py >/protected/observer.log 2>&1 </dev/null &',user='root')
        if result.return_code:raise RuntimeError(str(result.stdout)+str(result.stderr))

        ready=await env.exec(command="python -c \"import time;from pathlib import Path;p=Path('/protected/observer.ready');deadline=time.monotonic()+8;exec('while not p.exists() and time.monotonic()<deadline:time.sleep(.1)');assert p.exists(),Path('/protected/observer.log').read_text()\"",user='root')
        if ready.return_code:raise RuntimeError('Observer startup failed: '+str(ready.stdout)+str(ready.stderr))

    async def capture(event):
        result=await env.exec(command='python /protected/capture.py',user='root',timeout_sec=60)
        if result.return_code:raise RuntimeError('Trusted capture failed: '+str(result.stderr))
        if args.case=='SP012':
            path=trial.paths.trial_dir/'remote.jsonl'
            await env.service_download_file('/records/remote.jsonl',path,service='mainnet-proxy')
            await env.upload_file(path,'/protected/remote.jsonl')
        print(result.stdout,flush=True)

    trial.add_hook(TrialEvent.AGENT_START,setup)
    trial.add_hook(TrialEvent.AGENT_START,observe)
    trial.add_hook(TrialEvent.AGENT_END,capture)
    result=await trial.run()
    rewards=result.verifier_result.rewards if result.verifier_result else {}
    timeout=bool(result.exception_info and result.exception_info.exception_type=='AgentTimeoutError')
    infrastructure=bool(result.exception_info and not timeout) or bool(rewards.get('infrastructure_error'))
    status='budget_exhaustion' if timeout else 'infrastructure_error' if infrastructure else 'pass' if rewards.get('completion')==1 else 'agent_failure'
    summary={'case':args.case,'agent':args.agent,'seed':args.seed,'status':status,'rewards':rewards,'trial_dir':str(trial.paths.trial_dir)}
    (trial.paths.trial_dir/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
    return 2 if infrastructure else 0 if status=='pass' else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('case');parser.add_argument('--agent',choices=['oracle','codex'],default='oracle')
    parser.add_argument('--model',default='openai/gpt-6-astra');parser.add_argument('--run',default='qualification');parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--profile',choices=['default','ogi'],default='default')
    raise SystemExit(asyncio.run(main(parser.parse_args())))
