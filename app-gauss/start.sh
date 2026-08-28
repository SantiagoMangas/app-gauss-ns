#!/usr/bin/env bash
# Arranque para Railway (y compatible con Render si se usa este script).
# Si existe STREAMLIT_SECRETS_TOML, se escribe a .streamlit/secrets.toml.
# Si no, se deja el secrets.toml que ya esté (Secret File de Render / archivo local).
set -euo pipefail
cd "$(dirname "$0")"

python -c '
import os
from pathlib import Path

raw = os.environ.get("STREAMLIT_SECRETS_TOML") or ""
if raw.strip():
    dest = Path(".streamlit") / "secrets.toml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not raw.endswith("\n"):
        raw += "\n"
    dest.write_text(raw, encoding="utf-8")
'

port="${PORT:-8501}"
exec python -m streamlit run app.py \
  --server.port="$port" \
  --server.address=0.0.0.0 \
  --server.headless=true
