#!/bin/sh
set -eu
test -f /protected/collection.complete
python - <<'PY'
import json
import os
from pathlib import Path
assert json.loads(Path('/protected/evidence.json').read_text())['case'] == os.environ['SURFBENCH_CASE']
PY
if [ "$SURFBENCH_CASE" = SP012 ]; then
    test -s /records/remote.jsonl
    cp /records/remote.jsonl /protected/remote.jsonl
fi
python -m surfbench.grade /protected /logs/verifier
