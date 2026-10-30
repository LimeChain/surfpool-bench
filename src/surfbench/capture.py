"""Trusted final collection, executed as root before Harbor stops main."""
import hashlib
import json
import os
import sys
import signal
import subprocess
import time
from pathlib import Path
from surfbench.rpc import RPC
from observe import processes,freeze_agent_processes,listeners

root=Path('/protected')
spec=json.loads((root/'spec.json').read_text())
evidence=dict(spec)
evidence['observer_log']=(root/'observer.log').read_text()
evidence['stopped_agent_pids']=freeze_agent_processes()
evidence['processes']=processes()
evidence['listeners']=listeners()
evidence['handoff_time']=time.time()
# Close agent-phase capture before independent verifier challenges.
if (root/'tcpdump.pid').exists():
    time.sleep(.25)
    os.kill(int((root/'tcpdump.pid').read_text()),signal.SIGINT)
    time.sleep(.5)
evidence['capture_log']=(root/'tcpdump.log').read_text() if (root/'tcpdump.log').exists() else ''
evidence['final_samples']=[]
r=RPC(spec['rpc'],timeout=2)
# Both IPv4 and IPv6 loopback satisfy the local endpoint contract.
try:r.call('getHealth')
except Exception:
    alternative=RPC(spec['rpc'].replace('127.0.0.1','[::1]'),timeout=2)
    try:
        if alternative.call('getHealth')=='ok':r=alternative
    except Exception:pass
evidence['rpc']=r.url
spec={**spec,'rpc':r.url}
from surfbench.wire import read_pcap,exchanges
from surfbench.transactions import submitted_transactions
pairs=exchanges(read_pcap(root/'rpc.pcap'))
signatures=list(dict.fromkeys(t['signature'] for t in submitted_transactions(pairs) if t['accepted']))
evidence['transaction_statuses']={}
if signatures:
    try:
        statuses=r.call('getSignatureStatuses',signatures,{'searchTransactionHistory':True})['value']
        evidence['transaction_statuses']=dict(zip(signatures,statuses))
    except Exception as error:evidence['transaction_status_error']=str(error)
for _ in range(3):
    sample={'time':time.time()}
    try:sample['accounts']=r.call('getMultipleAccounts',spec['keys'],{'encoding':'base64','commitment':'confirmed'})
    except Exception as error:sample['error']=str(error)
    evidence['final_samples'].append(sample)
    time.sleep(2.5)
evidence['final_hashes']={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/fixtures').rglob('*') if p.is_file()}
try:evidence['report']=json.loads(Path('/app/report.json').read_text())
except (OSError,ValueError):evidence['report']=None
try:
    from urllib.parse import urlparse
    reported=(evidence.get('report') or {}).get('rpc_url','')
    parsed=urlparse(reported)
    valid=parsed.hostname in ('127.0.0.1','localhost','::1') and parsed.port==urlparse(r.url).port
    evidence['report_endpoint_usable']=bool(valid and RPC(reported,timeout=2).call('getHealth')=='ok')
except Exception:evidence['report_endpoint_usable']=False
try:
    from challenges import collect
    evidence['challenge']=collect(spec)
except Exception as error:evidence['challenge_error']=str(error)
(root/'stop').touch()
(root/'evidence.json').write_text(json.dumps(evidence,indent=2))
print(json.dumps({'case':spec['case'],'samples':len(evidence['final_samples']),'surfpool_processes':len(evidence['processes'])}))
