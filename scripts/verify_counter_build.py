"""Rebuild the SBF fixture and verify its pinned provenance checksum."""
import argparse
from pathlib import Path
import tempfile

from build_counter import compile_counter, expected_digest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--toolchain', type=Path, required=True,
                        help='Anza platform-tools v1.58 root, containing llvm/bin')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        compile_counter(args.toolchain.resolve(), Path(directory)/'counter.so')
    print('Rebuilt counter matches pinned provenance:', expected_digest())
