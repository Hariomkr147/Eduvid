#!/usr/bin/env bash
# Restore the newest dump into a throwaway postgres:16 container and count the tables.
# Prints "RESTORE OK tables=<n>"; exits 1 if there is no dump or fewer than MIN_TABLES come back.
set -euo pipefail

BACKUPS=${BACKUP_DIR:-/srv/eduvid/data/backups}
MIN_TABLES=${MIN_TABLES:-14}
NAME="eduvid-restore-test-$$"

dump=$(ls -1t "$BACKUPS"/eduvid-*.dump 2>/dev/null | head -1 || true)
[ -n "$dump" ] || { echo "RESTORE FAIL: no dump in $BACKUPS"; exit 1; }

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT

docker run -d --name "$NAME" -e POSTGRES_PASSWORD=restore -e POSTGRES_DB=restore postgres:16 >/dev/null
for _ in $(seq 1 60); do
  # pg_isready is true briefly during init; wait for the final server (it logs "ready" twice).
  if docker exec "$NAME" pg_isready -U postgres -d restore >/dev/null 2>&1 \
     && [ "$(docker logs "$NAME" 2>&1 | grep -c 'database system is ready to accept connections')" -ge 2 ]; then
    break
  fi
  sleep 1
done

docker cp "$dump" "$NAME:/tmp/restore.dump"
docker exec "$NAME" pg_restore -U postgres -d restore --no-owner --no-privileges --exit-on-error /tmp/restore.dump

n=$(docker exec "$NAME" psql -U postgres -d restore -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")
if [ "$n" -ge "$MIN_TABLES" ]; then
  echo "RESTORE OK tables=$n ($(basename "$dump"))"
else
  echo "RESTORE FAIL tables=$n < $MIN_TABLES ($(basename "$dump"))"
  exit 1
fi
