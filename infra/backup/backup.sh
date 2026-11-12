#!/usr/bin/env bash
# Nightly backup: pg_dump -Fc -> data/backups (keep newest 14), then copy dumps + MinIO data to GCS.
# Env (from /srv/eduvid/app/.env): BACKUP_GCS_BUCKET=gs://<project>-eduvid-backup
# Set BACKUP_SKIP_GCS=1 for a local-only run. Exit codes: 0 ok, 1 dump failed, 2 GCS copy failed.
set -euo pipefail

APP=/srv/eduvid/app
DATA=/srv/eduvid/data
BACKUPS=$DATA/backups
KEEP=14

cd "$APP"
# read single keys from .env (it is a compose env file, not a shell script)
env_get() { sed -n "s/^$1=\([^ #]*\).*/\1/p" .env | tail -1; }
POSTGRES_USER=$(env_get POSTGRES_USER)
POSTGRES_DB=$(env_get POSTGRES_DB)
BACKUP_GCS_BUCKET=${BACKUP_GCS_BUCKET:-$(env_get BACKUP_GCS_BUCKET)}

ts=$(date -u +%Y%m%d-%H%M)
out="$BACKUPS/eduvid-$ts.dump"
tmp="$out.partial"

echo "$(date -Is) dump -> $out"
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$tmp"
[ -s "$tmp" ] || { echo "pg_dump produced an empty file"; exit 1; }
mv "$tmp" "$out"

# keep the newest $KEEP dumps
ls -1t "$BACKUPS"/eduvid-*.dump | tail -n +$((KEEP + 1)) | while read -r old; do
  echo "pruning $(basename "$old")"; unlink "$old"
done

if [ "${BACKUP_SKIP_GCS:-0}" = 1 ]; then
  echo "BACKUP OK (local only)"; exit 0
fi
bucket=${BACKUP_GCS_BUCKET:-}
case "$bucket" in
  gs://*'<'*|"") echo "BACKUP_GCS_BUCKET not set in .env; local dump kept"; exit 2 ;;
esac

rc=0
gsutil -q -m rsync -r "$BACKUPS" "$bucket/postgres" || rc=2
gsutil -q -m rsync -r "$DATA/minio" "$bucket/minio" || rc=2
[ $rc = 0 ] && echo "BACKUP OK -> $bucket" || echo "BACKUP: GCS copy FAILED (local dump kept at $out)"
exit $rc
