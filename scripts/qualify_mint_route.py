"""Offline qualification of the accepted mint-authority impersonation variant.
Run inside the runtime image as agent, with the suite mounted read-only at /suite.
"""
import base64
import json
from pathlib import Path
import subprocess
from solders.hash import Hash
from solders.instruction import Instruction,AccountMeta
from solders.message import Message
from solders.pubkey import Pubkey
from solders.transaction import Transaction
from surfbench.client import load_key,send
from surfbench.rpc import RPC,TOKEN_PROGRAM,decode_token,decode_mint,canonical_account,RpcError

root=Path('/suite/fixtures/synthetic');keys=json.loads((root/'accounts.json').read_text());r=RPC()
log=Path('/app/mint-route.log').open('w')
process=subprocess.Popen(['surfpool','start','--offline','--no-deploy','--no-tui','--no-studio',
    '--snapshot',str(root/'setup.json'),'--skip-signature-verification'],stdout=log,stderr=log)
try:
    r.ready();sentinel=canonical_account(r.account(keys['sentinel'])['value'])
    payer=load_key(root/'payer-keypair.json');alice=load_key(root/'alice-keypair.json')
    # Burn the existing excess using Alice's real authority.
    burn=Instruction(Pubkey.from_string(TOKEN_PROGRAM),b'\x0f'+(87_500_000).to_bytes(8,'little')+b'\x06',[
        AccountMeta(Pubkey.from_string(keys['alice_token']),False,True),
        AccountMeta(Pubkey.from_string(keys['mint']),False,True),AccountMeta(alice.pubkey(),True,False)])
    burned=send(r,payer,[burn],[alice])
    # Deliberately unsigned MintToChecked, using the declared mint authority.
    mint=Instruction(Pubkey.from_string(TOKEN_PROGRAM),b'\x0e'+(3_000).to_bytes(8,'little')+b'\x06',[
        AccountMeta(Pubkey.from_string(keys['mint']),False,True),
        AccountMeta(Pubkey.from_string(keys['bob_token']),False,True),AccountMeta(payer.pubkey(),True,False)])
    blockhash=Hash.from_string(r.call('getLatestBlockhash')['value']['blockhash'])
    transaction=Transaction.new_unsigned(Message.new_with_blockhash([mint],payer.pubkey(),blockhash))
    assert not all(transaction.verify_with_results())
    minted=r.call('sendTransaction',base64.b64encode(bytes(transaction)).decode(),{'encoding':'base64'})
    import time
    for _ in range(100):
        status=r.call('getSignatureStatuses',[minted])['value'][0]
        if status and status.get('confirmationStatus') in ('confirmed','finalized'):break
        time.sleep(.1)
    assert status and status['err'] is None
    balances={name:decode_token(r.account(keys[name+'_token'])['value'])['amount'] for name in ('alice','bob')}
    assert balances=={'alice':12_500_000,'bob':3_000}
    assert canonical_account(r.account(keys['sentinel'])['value'])==sentinel
    mint_state=decode_mint(r.account(keys['mint'])['value'])
    assert mint_state['decimals']==6 and mint_state['mint_authority']==keys['payer'] and mint_state['freeze_authority']==keys['payer']
    print(json.dumps({'passed':True,'route':'signed burn plus unsigned MintToChecked under local signature bypass',
        'burn_signature':burned,'mint_signature':minted,'balances':balances,'mint':mint_state},indent=2))
finally:
    process.terminate();process.wait(timeout=10);log.close()
