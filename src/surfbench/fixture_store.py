"""Read verified, pre-generated fixture variants without generating runtime data."""
import hashlib
import json
from pathlib import Path
import shutil


def _verify_bundle(path, seed, manifest_sha256):
    manifest_bytes = (path / 'manifest.json').read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != manifest_sha256:
        raise ValueError(f'Fixture manifest checksum mismatch: {path}')
    manifest = json.loads(manifest_bytes)
    if manifest['seed'] != seed:
        raise ValueError(f'Fixture seed mismatch: {path}')
    for name, expected in manifest['sha256'].items():
        if Path(name).name != name:
            raise ValueError(f'Invalid fixture filename: {name}')
        if hashlib.sha256((path / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Fixture checksum mismatch: {path / name}')


def validate_saved(store, seed):
    store = Path(store)
    index = json.loads((store / 'index.json').read_text())
    entry = index['variants'].get(str(seed))
    if entry is None:
        raise ValueError(f'No stored fixtures for seed {seed}; available seeds: '
                         + ', '.join(index['variants']))
    path = store / f'seed-{seed}'
    _verify_bundle(path, seed, entry['manifest_sha256'])
    return path


def copy_saved(store, seed, destination):
    source = validate_saved(store, seed)
    destination = Path(destination)
    shutil.copytree(source, destination)
    manifest_sha256 = hashlib.sha256((source / 'manifest.json').read_bytes()).hexdigest()
    _verify_bundle(destination, seed, manifest_sha256)
    return {'seed': seed, 'directory': source.name, 'manifest_sha256': manifest_sha256}
