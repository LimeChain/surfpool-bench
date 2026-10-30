"""Package the existing contracts with Harbor-native startup and collection."""
from pathlib import Path
import json
import re
import shutil
from harbor.models.task.task import Task
from surfbench.specs import CASES

ROOT = Path(__file__).resolve().parents[1]


def main():
    for case in CASES:
        legacy = ROOT/'tasks'/case
        target = ROOT/'tasks-harbor'/case
        for folder in ('environment','tests','solution'):
            (target/folder).mkdir(parents=True,exist_ok=True)
        for name in ('instruction.md','solution/solve.sh','environment/seccomp.json'):
            shutil.copyfile(legacy/name,target/name)
        config = (legacy/'task.toml').read_text().replace('scenario_version = "0.1.1"','scenario_version = "0.2.0"')
        config = config.replace('docker_image = "surfbench-runtime:0.1.1"','docker_image = "surfbench-harbor:0.2.0"')
        hosts = ['api.anthropic.com','claude.ai','platform.claude.com','console.anthropic.com']
        if case == 'SP012': hosts.append('mainnet-proxy')
        config = re.sub(r'^allowed_hosts = .*$', 'allowed_hosts = '+json.dumps(hosts),config,flags=re.M)
        config = config.replace('[[environment.mcp_servers]]',f'''[environment.env]
SURFBENCH_CASE = "{case}"
SURFBENCH_FIXTURE_SEED = "${{SURFBENCH_FIXTURE_SEED:-0}}"
[environment.healthcheck]
command = "test -f /protected/setup.complete"
interval_sec = 1
timeout_sec = 3
retries = 60
[[environment.mcp_servers]]''')
        config = config.replace('docker_image = "surfbench-verifier:0.1.1"','docker_image = "surfbench-harbor-verifier:0.2.0"')
        config = config.replace('[verifier.environment]', f'[verifier.env]\nSURFBENCH_CASE = "{case}"\n[verifier.environment]')
        config = config.replace('[verifier.env]', '''[[verifier.collect]]
command = "/protected/collect.sh"
service = "main"
user = "root"
timeout_sec = 60
[verifier.env]''')
        config += '''[[artifacts]]
source = "/protected/collection.complete"
destination = "trusted/collection.complete"
[[artifacts]]
source = "/protected/fixture-manifest.json"
destination = "trusted/fixture-manifest.json"
[[artifacts]]
source = "/protected/setup.log"
destination = "trusted/setup.log"
[[artifacts]]
source = "/protected/observer.log"
destination = "trusted/observer.log"
[[artifacts]]
source = "/protected/tcpdump.log"
destination = "trusted/tcpdump.log"
'''
        if case == 'SP012':
            config = config.replace('source = "/protected/remote.jsonl"','source = "/records/remote.jsonl"\nservice = "mainnet-proxy"')
        (target/'task.toml').write_text(config)
        shutil.copyfile(legacy/'environment/docker-compose.yaml',target/'environment/docker-compose.yaml')
        shutil.copyfile(ROOT/'images/native-verifier/test.sh',target/'tests/test.sh')
        Task(target)
    print(f'Generated {len(CASES)} native Harbor tasks.')


if __name__ == '__main__': main()
