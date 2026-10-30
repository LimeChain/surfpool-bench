#!/bin/sh
set -eu
python - <<'PYCODE'
import json
import shutil,subprocess
from pathlib import Path
from surfbench.rpc import RPC
keys=json.loads(Path('/fixtures/accounts.json').read_text())
r=RPC()
log=open('/app/surfpool.log','w')
subprocess.Popen(['surfpool','start','--offline','--no-deploy','--no-tui','--no-studio'],stdout=log,stderr=log,start_new_session=True)
r.ready()
for label,amount in [('alice',2_000_000_000),('bob',125_000_000)]:
 r.call('surfnet_setAccount',keys[label],{'lamports':amount})
Path('/app/report.json').write_text(json.dumps({'rpc_url':r.url,'summary':'Reference solution completed', **(json.loads(Path('/app/diagnosis.json').read_text()) if Path('/app/diagnosis.json').exists() else {})}))
PYCODE
