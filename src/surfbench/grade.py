"""Deterministic grading from protected live observations. Fail closed."""
import hashlib
import json
import sys
import re
from pathlib import Path
from .rpc import canonical_account,decode_token,decode_mint,raw_data,TOKEN_PROGRAM,canonical_upstream


STATE_MUTATORS={'surfnet_setAccount','surfnet_setTokenAccount','surfnet_cloneProgramAccount',
    'surfnet_setSupply','surfnet_setProgramAuthority','surfnet_resetAccount','surfnet_resetNetwork',
    'surfnet_writeProgram','surfnet_registerScenario','surfnet_streamAccount','surfnet_streamAccounts'}

def grade(evidence):
    assertions={}
    def check(name,value): assertions[name]=bool(value)
    case=evidence['case']; keys=evidence['addresses']
    remote_errors=[r for r in evidence.get('remote_records',[]) if not r.get('blocked') and (r.get('infrastructure_error') or r.get('http_status',200) in (401,403,429) or r.get('http_status',200)>=500 or r.get('response',{}).get('error',{}).get('code') in (429,-32005))]
    if remote_errors:evidence['infrastructure_error']=True
    observations=evidence.get('final_samples',[])
    expected_binary=evidence['surfpool_sha256']
    processes=evidence.get('processes',[])
    check('real_surfpool',bool(processes) and all(p['binary_sha256']==expected_binary for p in processes))
    check('simulator_memory_protected',bool(processes) and all(p.get('status',{}).get('Gid','').split()[1:2]==['1001'] for p in processes))
    check('safe_runtime_flags',all(not any(flag in [arg.split('=',1)[0] for arg in p['argv']] for flag in (['--skip-blockhash-check','--geyser-plugin-config','-g']+([] if case=='SP002' else ['--skip-signature-verification']))) for p in processes))
    check('no_injected_libraries',all(not {'LD_PRELOAD','LD_LIBRARY_PATH','LD_AUDIT'}.intersection(p.get('environ_keys',[])) for p in processes))
    port=int(evidence['rpc'].rsplit(':',1)[1])
    own={p['pid'] for p in processes if 'pid' in p}
    sockets=[s for s in evidence.get('listeners',[]) if s['port']==port]
    check('rpc_listener_owned',bool(sockets) and all(own.intersection(s['pids']) for s in sockets))
    check('post_handoff_liveness',len(observations)>=3 and all('accounts' in o for o in observations)
          and observations[-1]['time']-observations[0]['time']>=4.8)
    check('fixture_integrity',evidence['initial_hashes']==evidence['final_hashes'])
    account_samples=[]
    for observation in observations:
        if 'accounts' in observation:
            account_samples.append(dict(zip(evidence['keys'],observation['accounts']['value'])))
    if not account_samples:
        return {'completion':0.,'correctness':sum(assertions.values())/len(assertions),'reporting_endpoint':0.,'infrastructure_error':float(evidence.get('infrastructure_error',False))},assertions
    pairs=evidence.get('rpc_exchanges',[])
    from .transactions import submitted_transactions,transaction
    transactions=submitted_transactions(pairs)
    for tx in transactions:
        status=evidence.get('transaction_statuses',{}).get(tx['signature'])
        if status:tx['confirmed']=status.get('err') is None and status.get('confirmationStatus') in ('confirmed','finalized')
    if case=='SP001':
        check('single_surfpool_instance',len(processes)==1)
        for label,amount in [('alice',2_000_000_000),('bob',125_000_000)]:
            check(label+'_lamports',all(a.get(keys[label]) is not None and a[keys[label]]['lamports']==amount for a in account_samples))
    elif case=='SP002':
        for label,amount in [('alice',12_500_000),('bob',3_000)]:
            valid=True
            for accounts in account_samples:
                try:
                    state=decode_token(accounts[keys[label+'_token']])
                    valid &= state=={'mint':keys['mint'],'wallet':keys[label],'amount':amount,'state':1}
                except (ValueError,KeyError,TypeError):valid=False
            check(label+'_token',valid)
        try:
            before=decode_mint(evidence['initial_accounts'][keys['mint']])
            after=decode_mint(account_samples[-1][keys['mint']])
            before.pop('supply');after.pop('supply')
            check('mint_configuration',before==after)
        except (ValueError,TypeError,KeyError):check('mint_configuration',False)
        check('sentinel_unchanged',canonical_account(account_samples[-1].get(keys['sentinel']))==canonical_account(evidence['initial_accounts'].get(keys['sentinel'])))
    elif case=='SP003':
        for address,expected in evidence['expected_snapshot'].items():
            expected={k:v for k,v in expected.items() if k!='parsedData'}
            check('snapshot_'+address,all(canonical_account(a.get(address))==expected for a in account_samples))
        argv=processes[0]['argv'] if processes else []
        loaded=[x.split('=',1)[1] if x.startswith('--snapshot=') else argv[i+1] for i,x in enumerate(argv) if x=='--snapshot' or x.startswith('--snapshot=')]
        import posixpath
        loaded=[posixpath.normpath(x) for x in loaded]
        check('snapshot_order',loaded==['/fixtures/base.json','/fixtures/overlay.json'])
        target_addresses=set(evidence['expected_snapshot'])
        changes=[p for p in pairs if p['request'].get('method') in STATE_MUTATORS and
                 (p['request']['method']=='surfnet_resetNetwork' or any(key in json.dumps(p['request'].get('params',[])) for key in target_addresses))]
        check('no_post_load_target_mutation',not changes)
    elif case=='SP004':
        sockets=[s for s in evidence.get('listeners',[]) if s['port'] in (18899,18900)]
        check('loopback_bindings',bool(sockets) and {s['port'] for s in sockets}=={18899,18900}
              and all(s['address_hex'] in ('0100007F','00000000000000000000000001000000') and own.intersection(s['pids']) for s in sockets))
        samples=[o for o in evidence.get('observations',[]) if 'sentinel' in o or 'sentinel_error' in o]
        check('sentinel_continuity',len(samples)>=2 and all(o.get('sentinel')==evidence['sentinel_token'] for o in samples))
        challenge=evidence.get('challenge') or {}
        notification=challenge.get('notification',{})
        result=notification.get('params',{}).get('result',{})
        check('websocket_event',notification.get('method')=='accountNotification' and
              notification.get('params',{}).get('subscription')==challenge.get('subscription',{}).get('result') and
              result.get('value',{}).get('lamports')==challenge.get('lamports') and challenge.get('lamports') is not None)
    elif case=='SP005':
        challenge=evidence.get('challenge') or {}
        check('program_artifact',challenge.get('artifact_matches') and challenge.get('account',{}).get('executable'))
        def counter_value(account,expected):
            try:return account['owner']==keys['program'] and len(raw_data(account))==8 and int.from_bytes(raw_data(account),'little')==expected
            except (ValueError,TypeError,KeyError):return False
        check('counter_one',all(counter_value(a.get(keys['counter']),1) for a in account_samples))
        for op,name in [(0,'initialize'),(1,'increment')]:
            check(name+'_transaction',any(t['accepted'] and t['confirmed'] and t['valid_signatures'] and
                 any(i['program']==keys['program'] and i['accounts']==[keys['counter']] and i['data']==bytes([op]) for i in t['instructions']) for t in transactions))
        check('fresh_counter_invocation',counter_value(challenge.get('initial'),0) and counter_value(challenge.get('final'),1))
        forbidden=[]
        for pair in pairs:
            req=pair['request'];method=req.get('method','');params=req.get('params',[])
            if method in STATE_MUTATORS-{'surfnet_writeProgram'}:
                if not (method=='surfnet_setAccount' and params and params[0]==keys['payer']):forbidden.append(method)
        check('no_counter_state_injection',not forbidden and all('--snapshot' not in [arg.split('=',1)[0] for arg in p['argv']] for p in processes))
    elif case=='SP006':
        expected_ix={'program':TOKEN_PROGRAM,'accounts':[keys['alice_token'],keys['mint'],keys['bob_token'],keys['alice']],
                     'data':b'\x0c'+(1_000_000).to_bytes(8,'little')+b'\x06'}
        failures=[]
        for pair in pairs:
            if pair['request'].get('method') not in ('sendTransaction','simulateTransaction'):continue
            try:
                tx=transaction(pair);response=pair['response']
                result=response.get('result')
                error=response.get('error') or {}
                detail=error.get('data',{}).get('err') or (result.get('value',{}).get('err') if isinstance(result,dict) else None)
                failed=detail.get('InstructionError') if isinstance(detail,dict) else None
                frozen=bool(isinstance(failed,list) and len(failed)==2 and failed[1]=={'Custom':17} and
                            isinstance(failed[0],int) and 0<=failed[0]<len(tx['instructions']) and tx['instructions'][failed[0]]==expected_ix)
                if tx['valid_signatures'] and frozen:failures.append(pair)
            except (ValueError,TypeError,KeyError,IndexError):pass
        check('original_failure_reproduced',bool(failures))
        check('same_transfer_succeeded',any(expected_ix in t['instructions'] and t['accepted'] and t['confirmed'] and t['valid_signatures'] for t in transactions))
        for name,amount in [('alice_token',99_000_000),('bob_token',1_000_000)]:
            try:
                initial=evidence['initial_accounts'][keys[name]];expected=bytearray(raw_data(initial))
                expected[64:72]=amount.to_bytes(8,'little');expected[108]=1
                check(name+'_minimal_change',all(raw_data(a[keys[name]])==bytes(expected) and a[keys[name]]['owner']==initial['owner'] for a in account_samples))
            except (ValueError,TypeError,KeyError):check(name+'_minimal_change',False)
        bad=[]
        for pair in pairs:
            req=pair['request'];method=req.get('method','');params=req.get('params',[])
            if method in STATE_MUTATORS:
                if not (method=='surfnet_setTokenAccount' and len(params)>=3 and params[:2]==[keys['alice'],keys['mint']] and params[2]=={'state':'initialized'}):bad.append(method)
        check('correction_only',not bad)
        report=evidence.get('report') or {}
        diagnosis=str(report.get('cause') or report.get('summary','')).lower().replace('_',' ')
        contradiction=bool(re.search(r"\b(not|never|isn't|wasn't|is not|was not)\s+(?:actually\s+|already\s+)?(?:frozen|freez\w*)\b",diagnosis))
        check('diagnosis_supported',not contradiction and bool(re.search(r'\b(frozen|freez\w*)\b',diagnosis)) and
              (report.get('affected_account') in (keys['alice_token'],keys['alice']) or keys['alice_token'] in diagnosis or 'alice' in diagnosis or 'source' in diagnosis))
        challenge=evidence.get('challenge') or {}
        check('independent_transfer',bool(challenge.get('signature')))
        for name in ('mint','sentinel'):
            check(name+'_unchanged',canonical_account(account_samples[-1].get(keys[name]))==canonical_account(evidence['initial_accounts'].get(keys[name])))
    elif case=='SP011':
        from .scenario_check import validate_definition,timeline_valid
        challenge=evidence.get('challenge') or {};definition=challenge.get('saved_definition')
        check('saved_scenario_definition',validate_definition(definition,keys['oracle']))
        registrations=[p for p in pairs if p['request'].get('method')=='surfnet_registerScenario' and 'result' in p['response']]
        matching=[p for p in registrations if p['request'].get('params',[None])[0]==definition]
        check('scheduler_execution',bool(matching))
        start=matching[-1]['request']['params'][1] if matching and len(matching[-1]['request']['params'])>1 else None
        if start is None and matching:start=matching[-1]['response'].get('result',{}).get('context',{}).get('slot')
        samples=[]
        for sample in evidence.get('observations',[]):
            if 'accounts' not in sample:continue
            accounts=dict(zip(evidence['keys'],sample['accounts']['value']))
            samples.append({'accounts':{'context':sample['accounts']['context'],'value':accounts.get(keys['oracle'])}})
        for pair in pairs:
            request=pair['request'];result=pair['response'].get('result');params=request.get('params',[])
            if not isinstance(result,dict) or 'value' not in result or not params:continue
            if request['method']=='getAccountInfo' and params[0]==keys['oracle']:
                samples.append({'accounts':result})
            elif request['method']=='getMultipleAccounts' and keys['oracle'] in params[0]:
                samples.append({'accounts':{'context':result['context'],'value':result['value'][params[0].index(keys['oracle'])]}})
        check('observed_timeline',isinstance(start,int) and timeline_valid(samples,start,keys['oracle']))
        check('clean_replay',challenge.get('replay',{}).get('timeline_valid'))
        initial=evidence['initial_accounts'][keys['oracle']]
        try:
            expected=bytearray(raw_data(initial));expected[73:81]=(90*100_000_000).to_bytes(8,'little',signed=True)
            check('oracle_terminal_and_unrelated_fields',all(raw_data(a[keys['oracle']])==bytes(expected) and
                {k:v for k,v in canonical_account(a[keys['oracle']]).items() if k!='data'}==
                {k:v for k,v in canonical_account(initial).items() if k!='data'} for a in account_samples))
        except (ValueError,KeyError,TypeError):check('oracle_terminal_and_unrelated_fields',False)
        check('sentinel_unchanged',all(canonical_account(a.get(keys['sentinel']))==canonical_account(evidence['initial_accounts'].get(keys['sentinel'])) for a in account_samples))
        writes=[p['request']['method'] for p in pairs if p['request'].get('method') in STATE_MUTATORS-{'surfnet_registerScenario'}]
        check('no_manual_state_writes',not writes)
    elif case=='SP012':
        records=evidence.get('remote_records',[])
        live=[r for r in records if r.get('mode')=='live' and r.get('source_tls_verified') and r.get('finished',float('inf'))<=evidence['handoff_time']]
        captured={key:[] for key in keys.values()}
        for record in live:
            req=record.get('request',{});response=record.get('response',{});result=response.get('result')
            if not isinstance(result,dict) or 'value' not in result:continue
            params=req.get('params',[])
            if not params:continue
            if req.get('method')=='getAccountInfo':items=[(params[0],result['value'])]
            elif req.get('method')=='getMultipleAccounts':items=zip(params[0],result['value'])
            else:continue
            for address,value in items:
                if address in captured and value is not None:captured[address].append(value)
        for name,address in keys.items():
            check(name+'_live_upstream',bool(captured[address]))
            check(name+'_exact_response',bool(captured[address]) and all(any(canonical_account(a.get(address))==canonical_upstream(source) for source in captured[address]) for a in account_samples))
            reads=[]
            for pair in pairs:
                req=pair['request'];params=req.get('params',[]);method=req.get('method');response=pair['response']
                if 'result' not in response or not params:continue
                if method=='getAccountInfo' and params[0]==address and response['result'].get('value') is not None:reads.append(pair)
                elif method=='getMultipleAccounts' and address in params[0] and response['result']['value'][params[0].index(address)] is not None:reads.append(pair)
                elif method in ('getTokenAccountBalance','getTokenSupply') and params[0]==address:reads.append(pair)
            check(name+'_local_load_observed',bool(reads))
        try:
            mint=decode_mint(account_samples[-1][keys['mint']]);token=decode_token(account_samples[-1][keys['token_account']])
            check('decoded_identity',mint['initialized'] and token['mint']==keys['mint'] and token['state'] in (1,2))
        except (ValueError,TypeError,KeyError):check('decoded_identity',False)
        check('configured_datasource',any(any(x in ('--rpc-url','-u') and i+1<len(p['argv']) and p['argv'][i+1]==evidence['datasource'] for i,x in enumerate(p['argv'])) for p in processes))
        check('no_remote_writes',not any(r.get('blocked') for r in records))
        check('no_state_fabrication',not any(p['request'].get('method') in STATE_MUTATORS for p in pairs) and
              all('--snapshot' not in [arg.split('=',1)[0] for arg in p['argv']] and '--geyser-plugin-config' not in p['argv'] for p in processes))
        failures=remote_errors
        evidence['infrastructure_error']=bool(failures) and not all(captured.values())
    else:
        check('case_grader_implemented',False)
    try:
        report=evidence.get('report',{})
        reporting=float(evidence.get('report_endpoint_usable',report.get('rpc_url')==evidence['rpc']))
    except (AttributeError,TypeError):reporting=0.
    rewards={'completion':float(all(assertions.values())),
             'correctness':sum(assertions.values())/len(assertions),'reporting_endpoint':reporting,'infrastructure_error':float(evidence.get('infrastructure_error',False))}
    return rewards,assertions


def main():
    protected=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
    evidence=json.loads((protected/'evidence.json').read_text())
    from .wire import read_pcap,exchanges
    pcap=protected/'rpc.pcap'
    if pcap.exists():evidence['rpc_exchanges']=exchanges(read_pcap(pcap))
    observations=protected/'observations.jsonl'
    if observations.exists():evidence['observations']=[json.loads(line) for line in observations.read_text().splitlines() if line]
    remote=protected/'remote.jsonl'
    if remote.exists():evidence['remote_records']=[json.loads(line) for line in remote.read_text().splitlines() if line]
    if evidence['case']=='SP011':
        from .scenario_check import replay
        import tempfile
        with tempfile.TemporaryDirectory(prefix='surfbench-replay-') as temporary:
            snapshot=Path(temporary)/'setup.json'
            snapshot.write_text(json.dumps({key:canonical_account(value) for key,value in evidence['initial_accounts'].items() if value is not None}))
            definition=(evidence.get('challenge') or {}).get('saved_definition')
            replay_result=replay(evidence,definition,snapshot,temporary)
            evidence.setdefault('challenge',{})['replay']=replay_result
            (out/'scenario-replay.json').write_text(json.dumps(replay_result,indent=2))
    rewards,assertions=grade(evidence)
    (out/'assertions.json').write_text(json.dumps(assertions,indent=2))
    (out/'reward.json').write_text(json.dumps(rewards))
    print(json.dumps({'rewards':rewards,'assertions':assertions},indent=2))

if __name__=='__main__':main()
