from pathlib import Path
import subprocess

import pytest
from harbor.models.task.task import Task
from harbor.models.task.verifier_mode import resolve_verifier_environment_definition
from surfbench.specs import CASES

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('case', CASES)
def test_native_task_preserves_contract_and_bundles_verifier(case):
    native = ROOT/'tasks-harbor'/case
    for name in ('instruction.md','solution/solve.sh'):
        assert (native/name).read_bytes() == (ROOT/'tasks'/case/name).read_bytes()
    task = Task(native)
    definition = resolve_verifier_environment_definition(task.config, task.paths)
    assert definition.bundled_tests
    assert definition.config.docker_image == 'surfbench-harbor-verifier:0.2.0'
    assert task.config.verifier.env['SURFBENCH_CASE'] == case
    assert (native/'tests/test.sh').read_bytes() == (ROOT/'images/native-verifier/test.sh').read_bytes()


def test_verifier_rejects_missing_collection_before_invoking_grade(tmp_path):
    script = (ROOT/'images/native-verifier/test.sh').read_text()
    script = script.replace('/protected/', str(tmp_path)+'/')
    # Even otherwise valid evidence cannot bypass a failed collection hook.
    (tmp_path/'evidence.json').write_text('{"case":"SP001"}')
    result = subprocess.run(['sh','-c',script],capture_output=True,text=True)
    assert result.returncode != 0
    assert result.stdout == ''
    assert result.stderr == ''
