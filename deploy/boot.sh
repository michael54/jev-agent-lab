#!/usr/bin/env bash
set -euo pipefail
# Keep the official image's SSH and environment initialization.
bash /start.sh > /workspace/jev/base-startup.log 2>&1 &
exec bash /workspace/jev/start.sh >> /workspace/jev/service.log 2>&1
