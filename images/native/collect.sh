#!/bin/sh
set -eu
python - <<'PY'
from pathlib import Path
pid = int(Path('/protected/observer.pid').read_text())
assert Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0] != 'Z', 'Observer exited before handoff'
PY
python /protected/capture.py
touch /protected/collection.complete
