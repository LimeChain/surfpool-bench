"""Executed inside an offline qualification container against real Surfpool."""
import json
import struct
import time
from pathlib import Path
from surfbench.rpc import RPC, canonical_account, decode_mint, decode_token, raw_data
from surfbench.fixtures import SOL_FEED
from surfbench.client import transfer

root=Path('/suite/fixtures/synthetic')
keys=json.loads((root/'accounts.json').read_text())
expected=json.loads((root/'setup.json').read_text())
r=RPC();r.ready()
result={'version':r.call('getVersion'),'checks':{}}
for name in ('mint','alice_token','bob_token','oracle','sentinel'):
    account=r.account(keys[name])['value']
    actual=canonical_account(account)
    reference={k:v for k,v in expected[keys[name]].items() if k!='parsedData'}
    assert actual==reference,(name,actual,reference)
result['checks']['snapshot_fields']=True
r.call('surfnet_setTokenAccount',keys['alice'],keys['mint'],{'amount':12_500_000},None)
r.call('surfnet_setTokenAccount',keys['bob'],keys['mint'],{'amount':3_000},None)
assert decode_token(r.account(keys['alice_token'])['value'])['amount']==12_500_000
assert decode_token(r.account(keys['bob_token'])['value'])['amount']==3_000
result['checks']['token_balances']=True
r.call('surfnet_setTokenAccount',keys['alice'],keys['mint'],{'state':'frozen'},None)
failed=transfer(r,root,simulate=True)
assert failed['value']['err'] is not None,failed
result['frozen_error']=failed
r.call('surfnet_setTokenAccount',keys['alice'],keys['mint'],{'state':'initialized'},None)
result['transfer_signature']=transfer(r,root)
assert decode_token(r.account(keys['alice_token'])['value'])['amount']==11_500_000
assert decode_token(r.account(keys['bob_token'])['value'])['amount']==1_003_000
result['checks']['diagnosis_transfer']=True
scenario={'id':'qualification-price','name':'Qualification price timeline','description':'Synthetic offline test',
          'tags':['qualification'], 'overrides':[
              {'id':f'price-{offset}','templateId':'pyth-price-feed-v2',
               'values':{'feed_id':'0x'+SOL_FEED,'price_message.price':price*100_000_000},
               'account':{'pubkey':keys['oracle']},'scenarioRelativeSlot':offset,
               'enabled':True,'fetchBeforeUse':False} for offset,price in [(0,100),(20,60),(40,90)]]}
start=r.call('getSlot', {'commitment':'confirmed'})+10
result['scenario_registration']=r.call('surfnet_registerScenario',scenario,start)
result['scenario_start']=start
seen=[]
deadline=time.monotonic()+45
while time.monotonic()<deadline:
    response=r.account(keys['oracle']); slot=response['context']['slot']
    price=struct.unpack_from('<q',raw_data(response['value']),73)[0]
    seen.append([slot,price])
    if slot>=start+45: break
    time.sleep(.05)
for lo,hi,price in [(1,18,100),(21,38,60),(41,45,90)]:
    observations=[p for slot,p in seen if start+lo<=slot<=start+hi]
    assert observations and all(p==price*100_000_000 for p in observations),(lo,hi,observations,seen)
result['checks']['scenario_timeline']=True; result['observations']=seen
Path('/tmp/qualification.json').write_text(json.dumps(result,indent=2))
print(json.dumps({'checks':result['checks'],'version':result['version']}))
