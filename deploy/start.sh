#!/usr/bin/env bash
set -euo pipefail
cd /workspace/jev
export HF_HOME=/workspace/jev/hf-cache CUDA_VISIBLE_DEVICES=0
export SEMIF_KEY_FILE=/workspace/jev/api-key
exec .venv/bin/python -m uvicorn server:app --host 0.0.0.0 --port 8000 --workers 1 --no-access-log
