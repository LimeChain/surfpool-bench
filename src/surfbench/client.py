"""Small supplied developer client; transactions are restricted to loopback RPC."""
import argparse
import base64
import json
import time
from pathlib import Path
from urllib.parse import urlparse
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.hash import Hash
from solders.transaction import Transaction
from solders.instruction import Instruction, AccountMeta
from solders.system_program import create_account, CreateAccountParams
from .rpc import RPC, RpcError, TOKEN_PROGRAM, raw_data


def local_rpc(url):
    if urlparse(url).hostname not in ('127.0.0.1','localhost','::1'):
        raise ValueError('This fixture client only sends transactions to local loopback RPC')
    return RPC(url)


def load_key(path):
    return Keypair.from_bytes(bytes(json.loads(Path(path).read_text())))


def send(rpc, payer, instructions, signers=(), simulate=False):
    blockhash=Hash.from_string(rpc.call('getLatestBlockhash')['value']['blockhash'])
    tx=Transaction.new_signed_with_payer(instructions,payer.pubkey(),[payer,*signers],blockhash)
    encoded=base64.b64encode(bytes(tx)).decode()
    if simulate:
        return rpc.call('simulateTransaction',encoded,{'encoding':'base64','sigVerify':True})
    signature=rpc.call('sendTransaction',encoded,{'encoding':'base64','skipPreflight':False})
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        status=rpc.call('getSignatureStatuses',[signature])['value'][0]
        if status:
            if status['err'] is not None: raise RpcError('transaction',status['err'])
            if status.get('confirmationStatus') in ('confirmed','finalized'): return signature
        time.sleep(.1)
    raise TimeoutError(f'Transaction not confirmed: {signature}')


def transfer(rpc, keys_dir, amount=1_000_000, simulate=False):
    root=Path(keys_dir); keys=json.loads((root/'accounts.json').read_text())
    alice=load_key(root/'alice-keypair.json'); payer=load_key(root/'payer-keypair.json')
    # SPL Token TransferChecked: discriminator 12, raw u64 amount, u8 decimals.
    ix=Instruction(Pubkey.from_string(TOKEN_PROGRAM),b'\x0c'+amount.to_bytes(8,'little')+b'\x06',[
        AccountMeta(Pubkey.from_string(keys['alice_token']),False,True),
        AccountMeta(Pubkey.from_string(keys['mint']),False,False),
        AccountMeta(Pubkey.from_string(keys['bob_token']),False,True),
        AccountMeta(alice.pubkey(),True,False)])
    return send(rpc,payer,[ix],[alice],simulate=simulate)


def counter(rpc, keys_dir, action, counter_key=None):
    root=Path(keys_dir); keys=json.loads((root/'accounts.json').read_text())
    payer=load_key(root/'payer-keypair.json'); counter_key=counter_key or load_key(root/'counter-keypair.json')
    program=Pubkey.from_string(keys['program']); ixs=[]; signers=[]
    if action=='initialize':
        rent=rpc.call('getMinimumBalanceForRentExemption',8)
        ixs.append(create_account(CreateAccountParams(from_pubkey=payer.pubkey(),to_pubkey=counter_key.pubkey(),
                                  lamports=rent,space=8,owner=program)))
        signers.append(counter_key)
    ixs.append(Instruction(program,bytes([0 if action=='initialize' else 1]),[
        AccountMeta(counter_key.pubkey(),False,True)]))
    return send(rpc,payer,ixs,signers)

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('action',choices=['transfer','simulate-transfer','initialize','increment','read-counter'])
    parser.add_argument('--fixtures',default='/fixtures'); parser.add_argument('--rpc',default='http://127.0.0.1:8899')
    args=parser.parse_args(); rpc=local_rpc(args.rpc)
    try:
        if args.action in ('transfer','simulate-transfer'):
            result=transfer(rpc,args.fixtures,simulate=args.action=='simulate-transfer')
        elif args.action=='read-counter':
            key=json.loads((Path(args.fixtures)/'accounts.json').read_text())['counter']
            result=int.from_bytes(raw_data(rpc.account(key)['value']),'little')
        else: result=counter(rpc,args.fixtures,args.action)
        print(json.dumps({'result':result}))
    except RpcError as error:
        print(json.dumps({'error':error.error,'method':error.method})); raise SystemExit(1)
