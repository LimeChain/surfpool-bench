#!/bin/sh
set -eu
python - <<'PYCODE'
import json
import shutil,subprocess
from pathlib import Path
from surfbench.rpc import RPC
keys=json.loads(Path('/fixtures/accounts.json').read_text())
r=RPC()
from surfbench.client import transfer
from surfbench.rpc import RpcError
try:transfer(r,'/fixtures')
except RpcError as error:print(error)
r.call('surfnet_setTokenAccount',keys['alice'],keys['mint'],{'state':'initialized'},None)
print(transfer(r,'/fixtures'))
Path('/app/diagnosis.json').write_text(json.dumps({'cause':'Alice source token account was frozen','affected_account':keys['alice_token'],'correction':'Thawed source account'}))
Path('/app/report.json').write_text(json.dumps({'rpc_url':r.url,'summary':'Reference solution completed', **(json.loads(Path('/app/diagnosis.json').read_text()) if Path('/app/diagnosis.json').exists() else {})}))
PYCODE
