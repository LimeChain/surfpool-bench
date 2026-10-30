#!/bin/sh
set -eu
python - <<'PYCODE'
import json
import shutil,subprocess
from pathlib import Path
from surfbench.rpc import RPC
keys=json.loads(Path('/fixtures/accounts.json').read_text())
r=RPC()
import time,struct
from surfbench.rpc import raw_data
oracle=json.loads(Path('/fixtures/oracle.json').read_text())
scenario={'id':'reference-price','name':'Offline price scenario','description':'Synthetic price drop and recovery','tags':['offline'],
 'overrides':[{'id':f'price-{offset}','templateId':'pyth-price-feed-v2','values':{'feed_id':oracle['feed_id'],'price_message.price':price*100_000_000},
 'account':{'pubkey':oracle['address']},'scenarioRelativeSlot':offset,'enabled':True,'fetchBeforeUse':False} for offset,price in [(0,100),(20,60),(40,90)]]}
Path('/app/scenario.json').write_text(json.dumps(scenario))
start=r.call('getSlot',{'commitment':'confirmed'})+10
print(r.call('surfnet_registerScenario',scenario,start))
while r.call('getSlot',{'commitment':'confirmed'})<start+45:time.sleep(.1)
Path('/app/report.json').write_text(json.dumps({'rpc_url':r.url,'summary':'Reference solution completed', **(json.loads(Path('/app/diagnosis.json').read_text()) if Path('/app/diagnosis.json').exists() else {})}))
PYCODE
