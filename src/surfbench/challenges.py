"""Independent post-handoff probes. Invoked by the trusted root collector."""
import asyncio
import base64
import hashlib
import json
from pathlib import Path
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from surfbench.rpc import RPC, raw_data
from surfbench.client import counter, transfer


def websocket_probe(rpc):
    from websockets.asyncio.client import connect
    async def run():
        address=str(Keypair().pubkey())
        from urllib.parse import urlparse
        host=urlparse(rpc.url).hostname
        endpoint=f'ws://[{host}]:18900' if ':' in host else f'ws://{host}:18900'
        async with connect(endpoint,open_timeout=3) as ws:
            await ws.send(json.dumps({'jsonrpc':'2.0','id':1,'method':'accountSubscribe','params':[address,{'encoding':'base64','commitment':'confirmed'}]}))
            subscribed=json.loads(await asyncio.wait_for(ws.recv(),3))
            amount=1_234_567
            rpc.call('surfnet_setAccount',address,{'lamports':amount})
            notification=json.loads(await asyncio.wait_for(ws.recv(),5))
            return {'address':address,'lamports':amount,'subscription':subscribed,'notification':notification}
    return asyncio.run(run())


def program_probe(rpc,spec):
    program=spec['addresses']['program']; account=rpc.account(program)['value']
    data=raw_data(account); result={'account':account}
    if account['owner']=='BPFLoaderUpgradeab1e11111111111111111111111' and data[:4]==b'\x02\0\0\0' and len(data)==36:
        programdata_address=str(Pubkey.from_bytes(data[4:36]))
        programdata=rpc.account(programdata_address)['value']; raw=raw_data(programdata)
        result['programdata_address']=programdata_address
        result['programdata_account']=programdata
        if raw[:4]!=b'\x03\0\0\0':raise ValueError('Invalid ProgramData header')
        deployed=raw[45:]
    elif account['owner'] in ('BPFLoader2111111111111111111111111111111111','BPFLoader1111111111111111111111111111111111'):
        deployed=data
    else:raise ValueError('Unexpected program loader')
    expected=Path('/fixtures/counter.so').read_bytes()
    result['artifact_matches']=deployed[:len(expected)]==expected and not any(deployed[len(expected):])
    challenge=Keypair();result['challenge_address']=str(challenge.pubkey())
    result['initialize_signature']=counter(rpc,'/fixtures','initialize',challenge)
    result['initial']=rpc.account(str(challenge.pubkey()))['value']
    result['increment_signature']=counter(rpc,'/fixtures','increment',challenge)
    result['final']=rpc.account(str(challenge.pubkey()))['value']
    return result


def collect(spec):
    rpc=RPC(spec['rpc']);case=spec['case']
    if case=='SP004':return websocket_probe(rpc)
    if case=='SP005':return program_probe(rpc,spec)
    if case=='SP011':
        scenario=json.loads(Path('/app/scenario.json').read_text())
        return {'saved_definition':scenario}
    if case=='SP006':
        return {'signature':transfer(rpc,'/fixtures'),
                'after':{name:rpc.account(spec['addresses'][name])['value'] for name in ('alice_token','bob_token')}}
    return None
