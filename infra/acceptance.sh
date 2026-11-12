#!/bin/bash
# Plan 1 acceptance: restore test on the host, then the pytest checks in the tools container.
#   bash infra/acceptance.sh                       public path https://$DOMAIN/speech
#   ACCEPTANCE_BASE_URL=http://speech-api:8000 bash infra/acceptance.sh     internal path (443 closed)
set -euo pipefail
cd "$(dirname "$0")/.."
echo "== 5. restore test"
bash infra/backup/restore_test.sh
echo "== 1-4. pytest"
docker compose run --rm -T -e ACCEPTANCE_BASE_URL="${ACCEPTANCE_BASE_URL:-}" tools \
  pytest -q -s tests/integration/test_acceptance_plan1.py
