#!/usr/bin/env bash
set -euo pipefail
# Install thousands of small package files on container-local storage.
# Model weights remain cached on /workspace. This environment is ephemeral.
cd /workspace/jev
export UV_CACHE_DIR=/tmp/jev-uv-cache
export HF_HOME=/workspace/jev/hf-cache
export CUDA_VISIBLE_DEVICES=0
export SEMIF_KEY_FILE=/workspace/jev/api-key
command -v uv >/dev/null || python3 -m pip install uv
uv venv --python python3 /tmp/jev-venv
uv pip install --python /tmp/jev-venv/bin/python 'torch==2.10.0' --index-url https://download.pytorch.org/whl/cu128
uv pip install --python /tmp/jev-venv/bin/python -e './SemIf[test]' fastapi uvicorn
uv pip freeze --python /tmp/jev-venv/bin/python > /workspace/jev/benchmark-installed.txt
/tmp/jev-venv/bin/python -m pytest -q SemIf/tests > /workspace/jev/benchmark-tests.log 2>&1
exec /tmp/jev-venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log
