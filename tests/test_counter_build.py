"""Build input corruption must never silently change the benchmark program."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest


@pytest.fixture
def builder(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1]/'scripts/build_counter.py'
    spec = importlib.util.spec_from_file_location('counter_builder', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    fixtures = tmp_path/'fixtures'
    fixtures.mkdir()
    (fixtures/'PROVENANCE.json').write_text(json.dumps({
        'counter': {'sha256': hashlib.sha256(b'expected program').hexdigest()}}))
    return module


def test_corrupted_cached_program_is_rejected(builder):
    (builder.ROOT/'fixtures/counter.so').write_bytes(b'changed program')
    with pytest.raises(RuntimeError, match='Cached counter checksum mismatch'):
        builder.ensure_counter()


def test_unverified_download_is_not_extracted(builder, monkeypatch):
    monkeypatch.delenv('SURFBENCH_SBF_TOOLCHAIN', raising=False)
    monkeypatch.setattr(builder.platform, 'system', lambda: 'Linux')
    monkeypatch.setattr(builder.platform, 'machine', lambda: 'x86_64')
    monkeypatch.setattr(builder, 'urlopen', lambda *a, **kw: io.BytesIO(b'bad archive'))
    with pytest.raises(RuntimeError, match='download checksum mismatch'):
        builder.toolchain()
    assert list((builder.ROOT/'.cache').iterdir()) == []


def test_mismatched_compilation_is_not_published(builder, monkeypatch):
    monkeypatch.setattr(builder, 'toolchain', lambda: Path('/unused'))

    def fake_compiler(command, **kwargs):
        Path(command[command.index('-o') + 1]).write_bytes(b'wrong program')

    monkeypatch.setattr(builder.subprocess, 'run', fake_compiler)
    with pytest.raises(RuntimeError, match='Counter build checksum mismatch'):
        builder.ensure_counter()
    assert not (builder.ROOT/'fixtures/counter.so').exists()
    assert sorted(p.name for p in (builder.ROOT/'fixtures').iterdir()) == ['PROVENANCE.json']
