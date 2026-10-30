"""Wrong-outcome controls derived from qualified real Surfpool runs."""
import base64
import copy
import json
from pathlib import Path
import pytest
from surfbench.grade import grade

ROOT=Path(__file__).parent/'golden'
CASES=['SP001','SP002','SP003','SP004','SP005','SP006','SP011','SP012']

def evidence(case):return json.loads((ROOT/f'{case}.json').read_text())

def mutate_data(e,name,offset,replacement):
    index=e['keys'].index(e['addresses'][name])
    for sample in e['final_samples']:
        account=sample['accounts']['value'][index]
        data=bytearray(base64.b64decode(account['data'][0]));data[offset:offset+len(replacement)]=replacement
        account['data'][0]=base64.b64encode(data).decode()

@pytest.mark.parametrize('case',CASES)
def test_qualified_reference_evidence_passes(case):
    rewards,checks=grade(evidence(case));assert rewards['completion']==1,checks

@pytest.mark.parametrize('case',CASES)
def test_fake_or_unowned_rpc_cannot_pass(case):
    e=evidence(case)
    for sock in e['listeners']:sock['pids']=[]
    assert grade(e)[0]['completion']==0

@pytest.mark.parametrize('case',CASES)
def test_unprotected_simulator_cannot_pass(case):
    e=evidence(case)
    for proc in e['processes']:proc['status']['Gid']='1000 1000 1000 1000'
    assert grade(e)[0]['completion']==0

@pytest.mark.parametrize('case',CASES)
def test_binary_plugin_alias_is_rejected(case):
    e=evidence(case);e['processes'][0]['argv']+=['-g','/app/replacement.so']
    assert grade(e)[0]['completion']==0

@pytest.mark.parametrize('mutation',['decimals','wrong_mint','wrong_wallet','wrong_amount'])
def test_token_contract_rejects_wrong_identity_and_scale(mutation):
    e=evidence('SP002')
    if mutation=='decimals':mutate_data(e,'mint',44,b'\x09')
    elif mutation=='wrong_mint':mutate_data(e,'alice_token',0,bytes(32))
    elif mutation=='wrong_wallet':mutate_data(e,'bob_token',32,bytes(32))
    else:mutate_data(e,'alice_token',64,(12_500).to_bytes(8,'little'))
    assert grade(e)[0]['completion']==0

def test_reversed_snapshots_fail_even_with_correct_final_state():
    e=evidence('SP003');argv=e['processes'][0]['argv'];a=argv.index('/fixtures/base.json');b=argv.index('/fixtures/overlay.json');argv[a],argv[b]=argv[b],argv[a]
    assert grade(e)[0]['completion']==0

def test_equivalent_snapshot_equals_syntax_is_accepted():
    e=evidence('SP003');argv=e['processes'][0]['argv'];e['processes'][0]['argv']=[x for x in argv if x not in ('--snapshot','/fixtures/base.json','/fixtures/overlay.json')]+['--snapshot=/fixtures/base.json','--snapshot=/fixtures/overlay.json']
    assert grade(e)[0]['completion']==1

@pytest.mark.parametrize('mutation',['public_bind','missing_notification','sentinel_interrupted'])
def test_custom_endpoint_contract(mutation):
    e=evidence('SP004')
    if mutation=='public_bind':
        for sock in e['listeners']:
            if sock['port']==18900:sock['address_hex']='00000000'
    elif mutation=='missing_notification':e['challenge']['notification']={}
    else:e['observations'][0]['sentinel']='other service'
    assert grade(e)[0]['completion']==0

@pytest.mark.parametrize('mutation',['wrong_artifact','noop_program','fake_counter','no_transaction'])
def test_deployment_requires_real_invocation(mutation):
    e=evidence('SP005')
    if mutation=='wrong_artifact':e['challenge']['artifact_matches']=False
    elif mutation=='noop_program':e['challenge']['final']=e['challenge']['initial']
    elif mutation=='fake_counter':e['rpc_exchanges'].append({'request':{'method':'surfnet_setAccount','params':[e['addresses']['counter'],{'data':'AQAAAAAAAAA='}]},'response':{'result':None},'time':0})
    else:e['rpc_exchanges']=[p for p in e['rpc_exchanges'] if p['request']['method']!='sendTransaction']
    assert grade(e)[0]['completion']==0

@pytest.mark.parametrize('mutation',['no_failure','fake_balances','wrong_cause'])
def test_diagnosis_requires_failure_correction_and_same_transaction(mutation):
    e=evidence('SP006')
    if mutation=='no_failure':e['rpc_exchanges']=[p for p in e['rpc_exchanges'] if 'error' not in p['response']]
    elif mutation=='fake_balances':e['rpc_exchanges'].append({'request':{'method':'surfnet_setTokenAccount','params':[e['addresses']['alice'],e['addresses']['mint'],{'amount':99_000_000}]},'response':{'result':None},'time':0})
    else:e['report']={'cause':'Alice has insufficient SOL for the fee'}
    assert grade(e)[0]['completion']==0

@pytest.mark.parametrize('mutation',['staging_only','manual_price','wrong_offset','no_replay','wrong_timeline'])
def test_scenarios_require_scheduler_observation_and_replay(mutation):
    e=evidence('SP011')
    if mutation=='staging_only':e['rpc_exchanges']=[p for p in e['rpc_exchanges'] if p['request']['method']!='surfnet_registerScenario']
    elif mutation=='manual_price':e['rpc_exchanges'].append({'request':{'method':'surfnet_setAccount','params':[e['addresses']['oracle'],{}]},'response':{'result':None},'time':0})
    elif mutation=='wrong_offset':e['challenge']['saved_definition']['overrides'][1]['scenarioRelativeSlot']=19
    elif mutation=='no_replay':e['challenge']['replay']['timeline_valid']=False
    else:
        e['observations']=[]
        e['rpc_exchanges']=[p for p in e['rpc_exchanges'] if p['request']['method'] not in ('getAccountInfo','getMultipleAccounts')]
    assert grade(e)[0]['completion']==0

@pytest.mark.parametrize('mutation',['no_live_source','different_upstream','direct_only','fabricated_state','streaming'])
def test_remote_loading_requires_exact_live_source_and_local_reads(mutation):
    e=evidence('SP012')
    if mutation=='no_live_source':e['remote_records']=[]
    elif mutation=='different_upstream':
        for r in e['remote_records']:
            value=r.get('response',{}).get('result',{})
            if isinstance(value,dict) and isinstance(value.get('value'),dict):value['value']['lamports']+=1
    elif mutation=='direct_only':e['rpc_exchanges']=[]
    else:e['rpc_exchanges'].append({'request':{'method':'surfnet_streamAccount' if mutation=='streaming' else 'surfnet_setAccount','params':[e['addresses']['mint']]},'response':{'result':None},'time':0})
    assert grade(e)[0]['completion']==0

def test_read_only_stream_inventory_is_accepted():
    e=evidence('SP012');e['rpc_exchanges'].append({'request':{'method':'surfnet_getStreamedAccounts','params':[]},'response':{'result':{'value':{'accounts':[]}}},'time':0})
    assert grade(e)[0]['completion']==1

def test_upstream_rate_limit_is_infrastructure_failure():
    e=evidence('SP012');e['final_samples']=[];e['remote_records']=[{'http_status':429,'mode':'live','source_tls_verified':True,'finished':0}]
    rewards,_=grade(e);assert rewards['completion']==0 and rewards['infrastructure_error']==1


def test_snapshot_mutation_is_rejected_even_if_final_bytes_are_correct():
    e=evidence('SP003');e['rpc_exchanges'].append({'request':{'method':'surfnet_setAccount','params':[e['addresses']['alice'],{'lamports':2_000_000_000}]},'response':{'result':None},'time':0})
    assert grade(e)[0]['completion']==0


def test_negated_diagnosis_cannot_pass_on_keyword_presence():
    e=evidence('SP006');e['report']={'cause':'The Alice source account was not frozen; this was an insufficient SOL error'}
    assert grade(e)[0]['completion']==0


def test_invalid_token_option_tags_fail_usability():
    e=evidence('SP002');mutate_data(e,'alice_token',72,(2).to_bytes(4,'little'))
    assert grade(e)[0]['completion']==0


def test_invalid_mint_boolean_does_not_equal_true():
    e=evidence('SP002');mutate_data(e,'mint',45,b'\x02')
    assert grade(e)[0]['completion']==0


def test_local_mint_route_may_change_supply_and_skip_signatures():
    e=evidence('SP002');mutate_data(e,'mint',36,(12_503_000).to_bytes(8,'little'))
    e['processes'][0]['argv'].append('--skip-signature-verification')
    assert grade(e)[0]['completion']==1


def test_mint_route_does_not_allow_blockhash_bypass():
    e=evidence('SP002');e['processes'][0]['argv'].append('--skip-blockhash-check')
    assert grade(e)[0]['completion']==0


def test_scenario_can_use_the_native_current_slot_default():
    e=evidence('SP011')
    for pair in e['rpc_exchanges']:
        if pair['request']['method']=='surfnet_registerScenario':
            start=pair['request']['params'][1]
            pair['request']['params'][1]=None
            pair['response']['result']['context']['slot']=start
    assert grade(e)[0]['completion']==1


def test_native_pda_scenario_form_is_equivalent_to_pubkey():
    e=evidence('SP011')
    from surfbench.scenario_check import validate_definition,resolve_account
    definition=e['challenge']['saved_definition']
    for item in definition['overrides']:
        item['account']={'pda':{'programId':'pythWSnswVUd12oZpeFP8e9CVaEqJg25g1Vtc2biRsT',
                              'seeds':[{'u16Le':0},{'bytes32Ref':'feed_id'}]}}
        assert resolve_account(item)==e['addresses']['oracle']
    assert validate_definition(definition,e['addresses']['oracle'])
    for pair in e['rpc_exchanges']:
        if pair['request']['method']=='surfnet_registerScenario':pair['request']['params'][0]=copy.deepcopy(definition)
    assert grade(e)[0]['completion']==1


def test_wrong_pda_seed_does_not_target_the_supplied_oracle():
    e=evidence('SP011')
    from surfbench.scenario_check import validate_definition
    definition=e['challenge']['saved_definition']
    definition['overrides'][0]['account']={'pda':{'programId':'pythWSnswVUd12oZpeFP8e9CVaEqJg25g1Vtc2biRsT',
        'seeds':[{'u16Le':1},{'bytes32Ref':'feed_id'}]}}
    assert not validate_definition(definition,e['addresses']['oracle'])


def test_an_unrelated_transfer_error_is_not_the_original_failure():
    e=evidence('SP006')
    for pair in e['rpc_exchanges']:
        if pair['request']['method']=='sendTransaction' and 'error' in pair['response']:
            pair['response']['error']['data']['err']='BlockhashNotFound'
    assert grade(e)[0]['completion']==0


def test_clock_controlled_boundary_reads_prove_all_three_transitions():
    from surfbench.scenario_check import timeline_valid
    e=evidence('SP011');initial=e['initial_accounts'][e['addresses']['oracle']];samples=[]
    for offset,price in ((0,100),(20,60),(40,90)):
        account=copy.deepcopy(initial);raw=bytearray(base64.b64decode(account['data'][0]));raw[73:81]=(price*100_000_000).to_bytes(8,'little',signed=True)
        account['data'][0]=base64.b64encode(raw).decode()
        samples.append({'accounts':{'context':{'slot':100+offset},'value':account}})
    assert timeline_valid(samples,100,e['addresses']['oracle'])
    wrong=copy.deepcopy(samples[1]);wrong['accounts']['context']['slot']=110;samples.append(wrong)
    assert not timeline_valid(samples,100,e['addresses']['oracle'])
