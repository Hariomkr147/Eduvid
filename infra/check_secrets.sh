#!/bin/bash
# GPU engines run third-party model code (some with trust_remote_code). They get only HF_TOKEN from .env, never
# database, storage or API credentials. Exit 1 if any engine container would see a secret.
set -u
cd "$(dirname "$0")/.."
docker compose --profile bench config --format json | python3 infra/check_secrets.py
