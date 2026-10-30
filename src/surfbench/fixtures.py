"""Deterministic synthetic fixtures. Keys are local test keys, never funded externally."""
import argparse
import base64
import hashlib
import json
import struct
from pathlib import Path
from solders.keypair import Keypair
from solders.pubkey import Pubkey
from .rpc import SYSTEM_PROGRAM, TOKEN_PROGRAM, ata

PYTH_PROGRAM = "rec5EKMGg6MxZYaMdyBfgwp4d5rB9T1VQH5pJv5LtFJ"
PYTH_PUSH_PROGRAM = "pythWSnswVUd12oZpeFP8e9CVaEqJg25g1Vtc2biRsT"
SOL_FEED = "ef0d8b6fda2ceba41da15d4095d1da392a0d2f8ed0c6c7bc0f4cfac8c280b56d"


def keypair(label, seed=0):
    return Keypair.from_seed(hashlib.sha256(f"surfbench-v1:{seed}:{label}".encode()).digest())


def snapshot_account(data=b"", lamports=2_000_000, owner=SYSTEM_PROGRAM, executable=False):
    return {"lamports":lamports, "owner":owner, "executable":executable,
            "rentEpoch":0, "data":base64.b64encode(data).decode(), "parsedData":None}


def mint_bytes(authority, decimals=6, supply=100_000_000):
    return (struct.pack("<I",1)+bytes(Pubkey.from_string(authority))+
            struct.pack("<QBBI", supply, decimals, 1, 1)+bytes(Pubkey.from_string(authority)))


def token_bytes(mint, wallet, amount=0, state=1):
    data=bytearray(165)
    data[:32]=bytes(Pubkey.from_string(mint)); data[32:64]=bytes(Pubkey.from_string(wallet))
    struct.pack_into("<Q",data,64,amount); data[108]=state
    return bytes(data)


def oracle_bytes(authority, price=100_00000000):
    # Pyth PriceUpdateV2 Borsh, VerificationLevel::Full (enum variant 1).
    return (bytes([34,241,35,99,157,126,244,205])+bytes(Pubkey.from_string(authority))+b'\x01'+
            bytes.fromhex(SOL_FEED)+struct.pack("<qQiqqqQQ", price, 100, -8, 1700000000,
                                             1699999999, 100_00000000, 100, 0))


def create(root, seed=0):
    root=Path(root); root.mkdir(parents=True,exist_ok=True)
    labels=['alice','bob','payer','mint','sentinel','extra','program','counter']
    keys={name:keypair(name,seed) for name in labels}
    addresses={name:str(k.pubkey()) for name,k in keys.items()}
    addresses['alice_token']=ata(addresses['alice'],addresses['mint'])
    addresses['bob_token']=ata(addresses['bob'],addresses['mint'])
    addresses['oracle']=str(Pubkey.find_program_address([bytes(2),bytes.fromhex(SOL_FEED)],Pubkey.from_string(PYTH_PUSH_PROGRAM))[0])
    accounts={addresses['payer']:snapshot_account(lamports=100_000_000_000),
              addresses['sentinel']:snapshot_account(b'surfbench-sentinel-v1',owner=addresses['program']),
              addresses['mint']:snapshot_account(mint_bytes(addresses['payer']),owner=TOKEN_PROGRAM),
              addresses['alice_token']:snapshot_account(token_bytes(addresses['mint'],addresses['alice'],100_000_000),owner=TOKEN_PROGRAM),
              addresses['bob_token']:snapshot_account(token_bytes(addresses['mint'],addresses['bob']),owner=TOKEN_PROGRAM),
              addresses['oracle']:snapshot_account(oracle_bytes(addresses['payer']),owner=PYTH_PROGRAM)}
    diagnosis=dict(accounts)
    diagnosis[addresses['alice_token']]=snapshot_account(token_bytes(addresses['mint'],addresses['alice'],100_000_000,2),owner=TOKEN_PROGRAM)
    base={addresses['alice']:snapshot_account(lamports=2_000_000_000),
          addresses['sentinel']:snapshot_account(b'base-state',owner=addresses['program'])}
    overlay={addresses['sentinel']:snapshot_account(b'overlay-state',lamports=3_000_000,owner=addresses['program']),
             addresses['bob']:snapshot_account(lamports=125_000_000)}
    files={'accounts.json':addresses,'setup.json':accounts,'diagnosis.json':diagnosis,
           'base.json':base,'overlay.json':overlay,
           'oracle.json':{'address':addresses['oracle'],'template_id':'pyth-price-feed-v2','account_type':'PriceUpdateV2','feed_id':'0x'+SOL_FEED,'price_field':'price_message.price','exponent':-8,'initial_price':100,'fetch_before_use':False}}
    for label,k in keys.items(): files[label+'-keypair.json']=list(bytes(k))
    for name,obj in files.items(): (root/name).write_text(json.dumps(obj,indent=2)+'\n')
    manifest={'fixture_version':'0.1.0','seed':seed,'provenance':'synthetic; deterministic local-only keys',
              'decimals':6,'token_program':TOKEN_PROGRAM,'oracle_price_offset':73,
              'oracle_exponent':-8,'pyth_feed_id':'0x'+SOL_FEED,
              'sha256':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in files}}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return addresses

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('root'); parser.add_argument('--seed',type=int,default=0)
    a=parser.parse_args(); create(a.root,a.seed)
