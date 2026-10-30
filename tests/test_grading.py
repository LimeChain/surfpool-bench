import copy
import json
import pytest
from surfbench.fixtures import create,snapshot_account
from surfbench.grade import grade


def rpc_form(a):
    a=dict(a);a['data']=[a['data'],'base64'];return a

@pytest.fixture
def good(tmp_path):
    keys=create(tmp_path)
    lookup={keys['alice']:rpc_form(snapshot_account(lamports=2_000_000_000)),
            keys['bob']:rpc_form(snapshot_account(lamports=125_000_000))}
    return {'case':'SP001','addresses':keys,'keys':list(lookup),'rpc':'http://127.0.0.1:8899',
            'surfpool_sha256':'real-binary','processes':[{'pid':123,'status':{'Gid':'1000 1001 1001 1001'},'binary_sha256':'real-binary','argv':['surfpool','start','--offline']}],
            'listeners':[{'port':8899,'pids':[123]}],
            'initial_hashes':{'accounts.json':'a'},'final_hashes':{'accounts.json':'a'},
            'final_samples':[{'time':t,'accounts':{'context':{'slot':50},'value':list(lookup.values())}} for t in (1.,3.5,6.)],
            'report':{'rpc_url':'http://127.0.0.1:8899'}}


def test_good_reference_passes(good):
    rewards,assertions=grade(good)
    assert rewards['completion']==1 and all(assertions.values())

@pytest.mark.parametrize('mutation',['wrong_balance','fake_server','dead_process','edited_input','signature_bypass','short_liveness'])
def test_wrong_outcomes_fail(good,mutation):
    if mutation=='wrong_balance':good['final_samples'][-1]['accounts']['value'][0]['lamports']=2
    elif mutation=='fake_server':good['processes'][0]['binary_sha256']='fake'
    elif mutation=='dead_process':good['processes']=[]
    elif mutation=='edited_input':good['final_hashes']['accounts.json']='edited'
    elif mutation=='signature_bypass':good['processes'][0]['argv'].append('--skip-signature-verification')
    elif mutation=='short_liveness':good['final_samples'][-1]['time']=4
    assert grade(good)[0]['completion']==0


def test_report_does_not_replace_state(good):
    good['report']={'rpc_url':'http://127.0.0.1:8899','summary':'All perfect'}
    good['final_samples']=[]
    assert grade(good)[0]['completion']==0


def test_reporting_is_separate_from_state_completion(good):
    good['report']=None
    rewards,_=grade(good)
    assert rewards['completion']==1 and rewards['reporting_endpoint']==0
