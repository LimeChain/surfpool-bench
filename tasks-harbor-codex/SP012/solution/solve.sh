#!/bin/sh
set -eu
python - <<'PYCODE'
import json
import shutil,subprocess
from pathlib import Path
from surfbench.rpc import RPC
keys=json.loads(Path('/fixtures/accounts.json').read_text())
r=RPC()
remote=json.loads(Path('/fixtures/remote.json').read_text())
log=open('/app/surfpool.log','w')
subprocess.Popen(['surfpool','start','--rpc-url',remote['datasource'],'--no-deploy','--no-tui','--no-studio'],stdout=log,stderr=log,start_new_session=True)
r.ready(45)
print(r.account(remote['mint']))
print(r.account(remote['token_account']))
Path('/app/report.json').write_text(json.dumps({'rpc_url':r.url,'summary':'Reference solution completed', **(json.loads(Path('/app/diagnosis.json').read_text()) if Path('/app/diagnosis.json').exists() else {})}))
PYCODE
