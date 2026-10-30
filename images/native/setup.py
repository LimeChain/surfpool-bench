"""Container startup: copy fixed inputs and start observation before the agent."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import time

from surfbench.fixture_store import validate_saved
from surfbench.rpc import RPC


def launch(command, log):
    with open(log, 'a') as output:
        return subprocess.Popen(command, stdout=output, stderr=output,
                                stdin=subprocess.DEVNULL, start_new_session=True)


def main():
    case = os.environ['SURFBENCH_CASE']
    if case not in ('SP001','SP002','SP003','SP004','SP005','SP006','SP011','SP012'):
        raise ValueError(f'Unknown case: {case}')
    seed = int(os.environ.get('SURFBENCH_FIXTURE_SEED', '0'))
    source = validate_saved('/opt/surfbench-data/variants', seed)
    fixtures = Path('/fixtures'); fixtures.mkdir(exist_ok=True)
    names = ['accounts.json', 'payer-keypair.json']
    if case in ('SP002', 'SP011'): names += ['setup.json','alice-keypair.json','bob-keypair.json']
    if case == 'SP006': names += ['diagnosis.json','alice-keypair.json','bob-keypair.json']
    if case == 'SP011': names += ['oracle.json']
    if case == 'SP003': names += ['base.json','overlay.json']
    if case == 'SP005': names += ['program-keypair.json','counter-keypair.json']
    for name in names: shutil.copyfile(source/name, fixtures/name)
    if case == 'SP005':
        for name in ('counter.so','counter.c','counter-abi.json'):
            shutil.copyfile(Path('/opt/surfbench-data')/name, fixtures/name)
    if case == 'SP012': shutil.copyfile('/opt/surfbench-data/remote.json', fixtures/'remote.json')
    shutil.copyfile(source/'manifest.json', '/protected/fixture-manifest.json')
    sentinel_token = None
    if case == 'SP004':
        sentinel_token = secrets.token_hex(24)
        Path('/protected/sentinel-token').write_text(sentinel_token)
        launch(['python','/protected/sentinel.py'], '/protected/sentinel.log')
    if case in ('SP002','SP006','SP011'):
        snapshot = 'diagnosis.json' if case == 'SP006' else 'setup.json'
        launch(['runuser','-u','agent','--','surfpool','start','--offline','--no-deploy',
                '--no-tui','--no-studio','--snapshot',f'/fixtures/{snapshot}'], '/app/surfpool.log')
        RPC().ready()
    addresses = json.loads((fixtures/'accounts.json').read_text())
    remote = None
    if case == 'SP012':
        remote = json.loads((fixtures/'remote.json').read_text())
        addresses = {key:remote[key] for key in ('mint','token_account')}
    keys = list(dict.fromkeys(addresses.values()))
    spec = {'case':case, 'addresses':addresses, 'keys':keys,
            'rpc':'http://127.0.0.1:'+('18899' if case == 'SP004' else '8899'),
            'fixture_seed':seed,
            'fixture_manifest_sha256':hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest(),
            'surfpool_sha256':hashlib.sha256(Path('/usr/local/bin/surfpool').read_bytes()).hexdigest(),
            'initial_hashes':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in fixtures.rglob('*') if p.is_file()},
            'initial_accounts':{}}
    if remote: spec['datasource'] = remote['datasource']
    if sentinel_token: spec.update(sentinel_url='http://127.0.0.1:8899', sentinel_token=sentinel_token)
    if case == 'SP003':
        spec['expected_snapshot'] = json.loads((fixtures/'base.json').read_text()) | json.loads((fixtures/'overlay.json').read_text())
    if case in ('SP002','SP006','SP011'):
        values = RPC().call('getMultipleAccounts',keys,{'encoding':'base64','commitment':'confirmed'})['value']
        spec['initial_accounts'] = dict(zip(keys, values))
    Path('/protected/spec.json').write_text(json.dumps(spec, indent=2))
    capture = launch(['tcpdump','-i','lo','-nn','-U','--immediate-mode','-B','8192','-s','0',
                      '-w','/protected/rpc.pcap','tcp port 8899 or tcp port 18899'], '/protected/tcpdump.log')
    Path('/protected/tcpdump.pid').write_text(str(capture.pid))
    observer = launch(['python','/protected/observe.py'], '/protected/observer.log')
    observer_starts = 1
    observer_started = time.monotonic()
    deadline = time.monotonic()+15
    while time.monotonic() < deadline:
        if capture.poll() is not None:
            raise RuntimeError('Packet capture exited during startup')
        if observer.poll() is not None:
            # Docker Desktop's amd64 emulation can abort during early /proc
            # inspection. Retry only before handing the environment to an agent.
            if observer_starts >= 3:
                raise RuntimeError('Observer exited during startup three times')
            Path('/protected/observer.ready').unlink(missing_ok=True)
            time.sleep(.5)
            observer = launch(['python','/protected/observe.py'], '/protected/observer.log')
            observer_starts += 1
            observer_started = time.monotonic()
            continue
        if time.monotonic()-observer_started >= 2 and Path('/protected/observer.ready').exists() and Path('/protected/rpc.pcap').exists():
            Path('/protected/observer.pid').write_text(str(observer.pid))
            Path('/protected/setup.complete').touch()
            return
        time.sleep(.1)
    raise TimeoutError('Observer did not become ready')


if __name__ == '__main__': main()
