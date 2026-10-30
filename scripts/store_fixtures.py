"""Author the six fixed fixture variants once; never overwrite an existing store."""
import hashlib
import json
from pathlib import Path
from surfbench.fixtures import create

ROOT = Path(__file__).resolve().parents[1]


def main():
    store = ROOT / 'fixtures/variants'
    store.mkdir(exist_ok=False)
    variants = {}
    for seed in range(6):
        directory = store / f'seed-{seed}'
        create(directory, seed)
        variants[str(seed)] = {
            'manifest_sha256': hashlib.sha256((directory / 'manifest.json').read_bytes()).hexdigest()
        }
    index = {'fixture_version': '0.1.0', 'provenance': 'Synthetic local-only test keys; fixed seeds 0–5',
             'generator_sha256': hashlib.sha256((ROOT / 'src/surfbench/fixtures.py').read_bytes()).hexdigest(),
             'variants': variants}
    (store / 'index.json').write_text(json.dumps(index, indent=2) + '\n')
    print(f'Stored {len(variants)} fixture variants in {store}')


if __name__ == '__main__':
    main()
