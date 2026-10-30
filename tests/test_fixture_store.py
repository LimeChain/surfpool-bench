import json
from pathlib import Path
import shutil

import pytest

from surfbench.fixture_store import copy_saved, validate_saved
from surfbench.fixtures import create

STORE = Path(__file__).resolve().parents[1] / 'fixtures/variants'


@pytest.mark.parametrize('seed', range(6))
def test_stored_variant_preserves_existing_generator_bytes(seed, tmp_path):
    saved = validate_saved(STORE, seed)
    generated = tmp_path / 'generated'
    create(generated, seed)
    assert {p.name: p.read_bytes() for p in saved.iterdir()} == {
        p.name: p.read_bytes() for p in generated.iterdir()
    }


def test_attempt_copy_is_independent_and_does_not_generate(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Run-time fixture generation must not occur')
    monkeypatch.setattr('surfbench.fixtures.create', forbidden)
    first, second = tmp_path / 'first', tmp_path / 'second'
    info = copy_saved(STORE, 2, first)
    copy_saved(STORE, 2, second)
    assert info['seed'] == 2
    before = (second / 'setup.json').read_bytes()
    (first / 'setup.json').write_text('{}')
    assert (second / 'setup.json').read_bytes() == before
    assert (validate_saved(STORE, 2) / 'setup.json').read_bytes() == before


@pytest.mark.parametrize('damage', ['missing', 'modified', 'manifest'])
def test_corrupt_saved_fixture_is_rejected_before_copy(tmp_path, damage):
    store = tmp_path / 'store'
    shutil.copytree(STORE, store)
    path = store / 'seed-0' / ('manifest.json' if damage == 'manifest' else 'setup.json')
    if damage == 'missing':
        path.unlink()
    else:
        path.write_text('{}')
    destination = tmp_path / 'attempt'
    with pytest.raises((FileNotFoundError, ValueError)):
        copy_saved(store, 0, destination)
    assert not destination.exists()


def test_unstored_seed_and_existing_destination_are_rejected(tmp_path):
    with pytest.raises(ValueError, match='No stored fixtures'):
        copy_saved(STORE, 6, tmp_path / 'missing')
    destination = tmp_path / 'existing'
    destination.mkdir()
    (destination / 'sentinel').write_text('keep')
    with pytest.raises(FileExistsError):
        copy_saved(STORE, 0, destination)
    assert (destination / 'sentinel').read_text() == 'keep'
