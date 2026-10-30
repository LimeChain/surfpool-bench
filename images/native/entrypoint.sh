#!/bin/sh
set -eu
python /protected/setup.py > /protected/setup.log 2>&1
exec "$@"
