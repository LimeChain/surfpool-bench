"""Scenario contract checks and clean offline replay for the trusted collector."""
import json
import os
import struct
import subprocess
import time
from pathlib import Path
from surfbench.rpc import RPC,raw_data,canonical_account
from solders.pubkey import Pubkey


def resolve_account(item):
    account=item.get('account',{})
    if 'pubkey' in account:return account['pubkey']
    pda=account.get('pda',{});seeds=[]
    try:
        for seed in pda['seeds']:
            if set(seed)=={'u16Le'}:seeds.append(int(seed['u16Le']).to_bytes(2,'little'))
            elif set(seed)=={'bytes32Ref'}:
                value=item['values'][seed['bytes32Ref']]
                data=bytes.fromhex(value.removeprefix('0x'))
                if len(data)!=32:return None
                seeds.append(data)
            else:return None
        return str(Pubkey.find_program_address(seeds,Pubkey.from_string(pda['programId']))[0])
    except (ValueError,KeyError,TypeError,OverflowError):return None


def validate_definition(scenario,oracle):
    if not isinstance(scenario,dict):return False
    overrides=scenario.get('overrides',[])
    if len(overrides)!=3:return False
    expected={0:100,20:60,40:90}
    seen=set()
    for item in overrides:
        if not isinstance(item,dict):return False
        offset=item.get('scenarioRelativeSlot')
        if offset not in expected or offset in seen:return False
        seen.add(offset)
        if item.get('templateId')!='pyth-price-feed-v2' or item.get('enabled') is not True or item.get('fetchBeforeUse') is not False:return False
        if resolve_account(item)!=oracle:return False
        values=item.get('values',{})
        if values.get('price_message.price')!=expected[offset]*100_000_000:return False
        if set(values)-{'price_message.price','feed_id'}:return False
    return True


def timeline_valid(samples,start,oracle):
    windows=[(0,19,100),(20,39,60),(40,48,90)]
    values=[]
    for sample in samples:
        accounts=sample.get('accounts')
        if not accounts:continue
        if isinstance(accounts,dict) and 'value' in accounts:
            # Replay collects the oracle account directly.
            account=accounts['value'];slot=accounts['context']['slot']
        else:continue
        try:values.append((slot,struct.unpack_from('<q',raw_data(account),73)[0]))
        except (ValueError,TypeError,KeyError,struct.error):continue
    for lo,hi,price in windows:
        expected=price*100_000_000
        selected=[p for slot,p in values if start+lo<=slot<=start+hi]
        interior=[p for slot,p in values if start+lo<slot<start+hi]
        # A clock-controlled run may only read slots 0, 20 and 40. At a
        # transition slot, allow the qualified brief pre-materialization value,
        # but require the scheduled value to have actually been observed.
        if expected not in selected or any(p!=expected for p in interior):return False
    return True


def replay(spec,scenario,snapshot_path='/fixtures/setup.json',work_root='/protected'):
    if not validate_definition(scenario,spec['addresses']['oracle']):return {'definition_valid':False}
    rpc=RPC('http://127.0.0.1:19899',timeout=2)
    work_root=Path(work_root);work_root.mkdir(parents=True,exist_ok=True)
    log=(work_root/'replay.log').open('w')
    process=subprocess.Popen(['surfpool','start','--offline','--no-deploy','--no-tui','--no-studio',
        '--port','19899','--ws-port','19900','--snapshot',str(snapshot_path)],stdout=log,stderr=log,cwd=work_root,env={**os.environ,'HOME':str(work_root)})
    try:
        rpc.ready();start=rpc.call('getSlot',{'commitment':'confirmed'})+10
        registration=rpc.call('surfnet_registerScenario',scenario,start)
        samples=[];deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            account=rpc.account(spec['addresses']['oracle'])
            samples.append({'time':time.time(),'accounts':account})
            if account['context']['slot']>=start+45:break
            time.sleep(.05)
        return {'definition_valid':True,'start_slot':start,'registration':registration,'samples':samples,
                'timeline_valid':timeline_valid(samples,start,spec['addresses']['oracle'])}
    finally:
        process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()
