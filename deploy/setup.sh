#!/usr/bin/env bash
set -euo pipefail
cd /workspace/jev
export UV_CACHE_DIR=/workspace/jev/.uv-cache
export HF_HOME=/workspace/jev/hf-cache
export CUDA_VISIBLE_DEVICES=0
if ! command -v uv >/dev/null; then python3 -m pip install uv; fi
uv venv --python python3 .venv
uv pip install --python .venv/bin/python 'torch==2.10.0' --index-url https://download.pytorch.org/whl/cu128
uv pip install --python .venv/bin/python -e './SemIf[test]' fastapi uvicorn
cd SemIf
../.venv/bin/python -m pytest -q > /workspace/jev/upstream-tests.log 2>&1
(cd results/raw && sha256sum -c SHA256SUMS) > /workspace/jev/checksums.log
../.venv/bin/python benchmarks/verify_published.py > /workspace/jev/published-verification.log
cd ..
.venv/bin/python -m pip --version >/dev/null 2>&1 && .venv/bin/python -m pip freeze > installed.txt || uv pip freeze --python .venv/bin/python > installed.txt
exec bash start.sh
