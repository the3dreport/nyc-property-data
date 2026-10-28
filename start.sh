#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r backend/requirements.txt
fi
export PYTHONPATH="$PWD"
exec .venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8787
