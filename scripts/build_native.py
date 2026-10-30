"""Build the native Harbor/Claude runtime from the fixed assets; no model calls."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TAG = 'surfbench-harbor:0.2.0'
VERIFIER_TAG = 'surfbench-harbor-verifier:0.2.0'


def main():
    base_tags = ['surfbench-runtime:0.1.1','surfbench-verifier:0.1.1',
                 'surfbench-egress:0.1.1','surfbench-proxy:0.1.1']
    if subprocess.run(['docker','image','inspect',*base_tags],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
        manifest = ROOT/'reports/build-manifest.json'
        if manifest.exists():
            backup = manifest.with_name('build-manifest-before-native.json')
            if not backup.exists(): shutil.copyfile(manifest,backup)
        subprocess.run([sys.executable,str(ROOT/'scripts/build_images.py')],check=True)
    from surfbench.fixture_store import validate_saved
    for seed in range(6): validate_saved(ROOT/'fixtures/variants',seed)
    with tempfile.TemporaryDirectory(prefix='surfbench-native-') as directory:
        context = Path(directory)
        shutil.copyfile(ROOT/'images/native/Dockerfile',context/'Dockerfile')
        shutil.copyfile(ROOT/'src/surfbench/fixture_store.py',context/'fixture_store.py')
        shutil.copytree(ROOT/'images/native',context/'protected',ignore=shutil.ignore_patterns('Dockerfile','__pycache__'))
        for name in ('observe.py','capture.py','challenges.py','sentinel.py','scenario_check.py'):
            shutil.copyfile(ROOT/'src/surfbench'/name,context/'protected'/name)
        shutil.copytree(ROOT/'fixtures/variants',context/'data/variants')
        for name in ('counter.so','counter.c','counter-abi.json','remote.json'):
            shutil.copyfile(ROOT/'fixtures'/name,context/'data'/name)
        hashes = {str(p.relative_to(context)):hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in context.rglob('*') if p.is_file()}
        subprocess.run(['docker','build','--platform','linux/amd64','-t',TAG,str(context)],check=True)
    verifier_context = ROOT/'images/native-verifier'
    subprocess.run(['docker','build','--platform','linux/amd64','-t',VERIFIER_TAG,str(verifier_context)],check=True)
    hashes.update({'verifier/'+p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in verifier_context.iterdir() if p.is_file()})
    inspected = json.loads(subprocess.check_output(['docker','image','inspect',TAG,VERIFIER_TAG,*base_tags],text=True))
    report = {'runtime':TAG,'claude_code_version':'2.1.314','harbor_version':'0.25.0',
              'images':{tag:item['Id'] for tag,item in zip([TAG,VERIFIER_TAG,*base_tags],inspected)},'build_inputs_sha256':hashes}
    (ROOT/'reports/native-build-manifest.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__': main()
