#!/bin/sh
# Assemble the docker build context in data/deploy_ctx (git-ignored). Demo patients only, no lab Observations.
set -e
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
CTX="$ROOT/data/deploy_ctx"
rm -rf "$CTX"; mkdir -p "$CTX/data/raw/fhir" "$CTX/frontend" "$CTX/iris"
cp "$ROOT/deploy/azure/Dockerfile" "$ROOT/deploy/azure/entrypoint.sh" "$ROOT/deploy/azure/boot.py" "$CTX/"
(cd "$ROOT" && tar --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache --exclude=.ruff_cache --exclude=tests -cf - backend) | tar -xf - -C "$CTX"
cp -r "$ROOT/config" "$CTX/config"
cp -r "$ROOT/iris/src" "$CTX/iris/src"
(cd "$ROOT/frontend" && tar --exclude=node_modules --exclude=dist -cf - .) | tar -xf - -C "$CTX/frontend"
LIST="$ROOT/data/cloud_patients.json"; [ -f "$LIST" ] || LIST="$ROOT/data/demo_patients.json"
python "$ROOT/deploy/azure/stage_data.py" "$LIST" "$ROOT/data/raw/fhir" "$CTX/data"
echo "context ready: $CTX"
