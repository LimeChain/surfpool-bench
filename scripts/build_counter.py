"""Build the counter fixture locally, accepting only the pinned program bytes."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import tempfile
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
VERSION = 'v1.58'
ARCHIVES = {
    ('Darwin', 'arm64'): ('osx-aarch64', '17a89dae89936f045789d484140fd19a7bd992d4522d4ab0e9adeae565e35d12'),
    ('Linux', 'x86_64'): ('linux-x86_64', '7b82eb420b5aebd1e5590db0ae25c523eca06724d4238ae02139690535636c37'),
    ('Linux', 'aarch64'): ('linux-aarch64', '9732174e2217ccfa489dfd644cf9bd86c46226be83354c03b832f1b421596870'),
}


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def expected_digest():
    return json.loads((ROOT/'fixtures/PROVENANCE.json').read_text())['counter']['sha256']


def toolchain():
    if configured := os.environ.get('SURFBENCH_SBF_TOOLCHAIN'):
        return Path(configured).expanduser().resolve()
    host = (platform.system(), platform.machine())
    if host not in ARCHIVES:
        raise RuntimeError(f'No pinned SBF toolchain for {host}; set SURFBENCH_SBF_TOOLCHAIN to an Anza platform-tools {VERSION} directory containing llvm/bin')
    name, sha = ARCHIVES[host]
    cache = ROOT/'.cache'
    cache.mkdir(exist_ok=True)
    destination = cache/f'platform-tools-{VERSION}-{name}'
    if destination.is_dir():
        return destination
    url = f'https://github.com/anza-xyz/platform-tools/releases/download/{VERSION}/platform-tools-{name}.tar.bz2'
    print(f'Downloading pinned SBF toolchain ({name}); this is a one-time 430–530 MB download.', flush=True)
    with tempfile.TemporaryDirectory(dir=cache) as directory:
        temporary = Path(directory)
        archive = temporary/'toolchain.tar.bz2'
        with urlopen(url, timeout=60) as response, archive.open('wb') as target:
            shutil.copyfileobj(response, target)
        if digest(archive) != sha:
            raise RuntimeError('SBF toolchain download checksum mismatch')
        extracted = temporary/'extracted'
        with tarfile.open(archive) as bundle:
            bundle.extractall(extracted, filter='data')
        if not (extracted/'llvm/bin/clang').is_file():
            raise RuntimeError('SBF toolchain archive is missing llvm/bin/clang')
        extracted.rename(destination)
    return destination


def compile_counter(toolchain_root, output):
    binaries = toolchain_root/'llvm/bin'
    with tempfile.TemporaryDirectory() as directory:
        obj = Path(directory)/'counter.o'
        subprocess.run([str(binaries/'clang'), '-target', 'sbf', '-mcpu=v1', '-O2', '-fPIC', '-fno-stack-protector', '-c', str(ROOT/'fixtures/counter.c'), '-o', str(obj)], check=True)
        subprocess.run([str(binaries/'ld.lld'), '-z', 'notext', '-shared', '--entry', 'entrypoint', '-T', str(ROOT/'fixtures/counter.ld'), '-o', str(output), str(obj)], check=True)
    actual = digest(output)
    if actual != expected_digest():
        raise RuntimeError(f'Counter build checksum mismatch: {actual}; expected {expected_digest()}')


def ensure_counter():
    output = ROOT/'fixtures/counter.so'
    if output.exists():
        if digest(output) != expected_digest():
            raise RuntimeError('Cached counter checksum mismatch; remove fixtures/counter.so and rebuild')
        return output
    compiler = toolchain()
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        temporary = Path(directory)/'counter.so'
        compile_counter(compiler, temporary)
        temporary.replace(output)
    print(f'Built and verified counter: {expected_digest()}')
    return output


if __name__ == '__main__':
    ensure_counter()
