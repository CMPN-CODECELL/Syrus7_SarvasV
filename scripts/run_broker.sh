#!/usr/bin/env bash
set -e
mkdir -p data
export MOCK_BROKER_STORAGE_PATH=data/mock_broker.json
exec python -m uvicorn backend.broker.mock_api:app --host 127.0.0.1 --port 9001
