#!/usr/bin/env bash
set -e
export MOCK_BROKER_URL=${MOCK_BROKER_URL:-http://127.0.0.1:9001}
exec python -m uvicorn backend.api:create_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers
