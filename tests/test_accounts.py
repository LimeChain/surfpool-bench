import base64
import copy
import struct
import pytest
from surfbench.fixtures import create
from surfbench.rpc import decode_mint, decode_token, canonical_account
import json

def rpc_account(snapshot):
    result=dict(snapshot); result['data']=[result['data'],'base64']; return result

@pytest.fixture
def fixture(tmp_path):
    keys=create(tmp_path)
    return keys,json.loads((tmp_path/'setup.json').read_text())

def test_mint_and_wallet_identity(fixture):
    keys,accounts=fixture
    mint=decode_mint(rpc_account(accounts[keys['mint']]))
    assert mint=={'mint_authority':keys['payer'],'freeze_authority':keys['payer'],
                  'decimals':6,'initialized':True,'supply':100_000_000}
    token=decode_token(rpc_account(accounts[keys['alice_token']]))
    assert token=={'mint':keys['mint'],'wallet':keys['alice'],'amount':100_000_000,'state':1}

def test_wrong_program_rejected(fixture):
    keys,accounts=fixture
    account=rpc_account(accounts[keys['alice_token']]);account['owner']=keys['program']
    with pytest.raises(ValueError): decode_token(account)

def test_invalid_base64_and_truncated_accounts_rejected(fixture):
    keys,accounts=fixture
    account=rpc_account(accounts[keys['mint']]);account['data']=['not base64!!','base64']
    with pytest.raises(ValueError): decode_mint(account)
    account['data']=[base64.b64encode(bytes(81)).decode(),'base64']
    with pytest.raises(ValueError): decode_mint(account)

def test_frozen_fixture_and_oracle_offsets(tmp_path):
    keys=create(tmp_path)
    accounts=json.loads((tmp_path/'diagnosis.json').read_text())
    assert decode_token(rpc_account(accounts[keys['alice_token']]))['state']==2
    raw=base64.b64decode(accounts[keys['oracle']]['data'])
    assert struct.unpack_from('<q',raw,73)[0]==10_000_000_000
    assert struct.unpack_from('<i',raw,89)[0]==-8

def test_seed_and_snapshot_precedence(tmp_path):
    keys=create(tmp_path/'a',1); other=create(tmp_path/'b',2)
    assert keys['alice']!=other['alice']
    base=json.loads((tmp_path/'a/base.json').read_text())
    overlay=json.loads((tmp_path/'a/overlay.json').read_text())
    merged=base|overlay
    assert len(merged)==3
    assert base64.b64decode(merged[keys['sentinel']]['data'])==b'overlay-state'
