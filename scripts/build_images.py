"""Fetch verified releases and build the suite images; never runs a trial."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.request import urlopen

ROOT=Path(__file__).resolve().parents[1]
SURFPOOL_URL='https://github.com/solana-foundation/surfpool/releases/download/v1.7.0/surfpool-linux-x64.tar.gz'
SURFPOOL_SHA='5bef2b0b186a74622508f104b6d2e4e2db040932b6d8f3a811172e241f802a63'


def main():
    archive=ROOT/'images/surfpool-linux-x64.tar.gz'
    if not archive.exists():
        temporary=archive.with_suffix('.download')
        with urlopen(SURFPOOL_URL,timeout=60) as response:temporary.write_bytes(response.read())
        if hashlib.sha256(temporary.read_bytes()).hexdigest()!=SURFPOOL_SHA:
            temporary.unlink();raise RuntimeError('Surfpool download checksum mismatch')
        temporary.replace(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=SURFPOOL_SHA:raise RuntimeError('Cached Surfpool archive checksum mismatch')
    images=[('Dockerfile','surfbench-base:1.7.0'),('Dockerfile.runtime','surfbench-runtime:0.1.1'),
            ('Dockerfile.verifier','surfbench-verifier:0.1.1'),('Dockerfile.proxy','surfbench-proxy:0.1.1')]
    for dockerfile,tag in images:
        subprocess.run(['docker','build','--platform','linux/amd64','-f',str(ROOT/'images'/dockerfile),'-t',tag,str(ROOT)],check=True)
    subprocess.run(['docker','build','-t','surfbench-egress:0.1.1',str(ROOT/'images/egress-sidecar')],check=True)
    names=[tag for _,tag in images]+['surfbench-egress:0.1.1']
    inspected=json.loads(subprocess.check_output(['docker','image','inspect',*names],text=True))
    result={'surfpool_archive_url':SURFPOOL_URL,'surfpool_archive_sha256':SURFPOOL_SHA,
            'images':{name:{k:item[k] for k in ('Id','Architecture','Os','Created')} for name,item in zip(names,inspected)}}
    (ROOT/'reports/build-manifest.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
