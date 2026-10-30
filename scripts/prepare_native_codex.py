"""Prepare the native Codex profile; reuse fixed tasks and grading contracts."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from harbor.models.task.task import Task
from surfbench.specs import CASES

ROOT = Path(__file__).resolve().parents[1]
TAG = 'surfbench-codex:0.2.0'


def main():
    context = ROOT/'images/native-codex'
    subprocess.run(['docker','build','--platform','linux/amd64','-t',TAG,str(context)],check=True)
    for case in CASES:
        source = ROOT/'tasks-harbor'/case
        target = ROOT/'tasks-harbor-codex'/case
        shutil.copytree(source,target,dirs_exist_ok=True)
        file = target/'task.toml'
        config = file.read_text().replace('surfbench-harbor:0.2.0',TAG)
        hosts = ['chatgpt.com','api.openai.com','auth.openai.com','ab.chatgpt.com']
        if case == 'SP012': hosts.append('mainnet-proxy')
        config = re.sub(r'^allowed_hosts = .*$', 'allowed_hosts = '+json.dumps(hosts),config,flags=re.M)
        file.write_text(config)
        Task(target)
    images = ['surfbench-harbor:0.2.0',TAG,'surfbench-harbor-verifier:0.2.0']
    inspected = json.loads(subprocess.check_output(['docker','image','inspect',*images],text=True))
    report = {'codex_cli_version':'0.164.0','images':{tag:obj['Id'] for tag,obj in zip(images,inspected)},
              'dockerfile_sha256':hashlib.sha256((context/'Dockerfile').read_bytes()).hexdigest()}
    (ROOT/'reports/native-codex-build.json').write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__': main()
