"""Rebuild the small SBF fixture and compare it with the supplied artifact."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True,help='Anza platform-tools v1.58 root, containing llvm/bin')
    a=p.parse_args();bin=a.toolchain.resolve()/'llvm/bin'
    with tempfile.TemporaryDirectory() as temporary:
        obj=Path(temporary)/'counter.o';so=Path(temporary)/'counter.so'
        subprocess.run([str(bin/'clang'),'-target','sbf','-mcpu=v1','-O2','-fPIC','-fno-stack-protector','-c',str(ROOT/'fixtures/counter.c'),'-o',str(obj)],check=True)
        subprocess.run([str(bin/'ld.lld'),'-z','notext','-shared','--entry','entrypoint','-T',str(ROOT/'fixtures/counter.ld'),'-o',str(so),str(obj)],check=True)
        actual=hashlib.sha256(so.read_bytes()).hexdigest();expected=hashlib.sha256((ROOT/'fixtures/counter.so').read_bytes()).hexdigest()
        assert actual==expected,(actual,expected)
        print('Rebuilt counter matches supplied artifact:',actual)
