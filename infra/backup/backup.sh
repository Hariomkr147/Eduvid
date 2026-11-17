#!/usr/bin/env bash
# Nightly backup: pg_dump -Fc -> data/backups (keep newest 14), a tar of the MinIO data (videos, narration) ->
# data/backups/minio (keep newest 7), then copy dumps + MinIO data to GCS.
# The local copies guard against mistakes (a deleted video, a bad migration), not against losing the disk: only the
# GCS copy does that. Restore MinIO: stop minio, extract the tar over /srv/eduvid/data/minio, start minio.
# Env (from /srv/eduvid/app/.env): BACKUP_GCS_BUCKET=gs://<project>-eduvid-backup
# Set BACKUP_SKIP_GCS=1 for a local-only run. Exit codes: 0 ok, 1 dump failed, 2 GCS copy failed.
set -euo pipefail

APP=/srv/eduvid/app
DATA=/srv/eduvid/data
BACKUPS=$DATA/backups
KEEP=14
KEEP_MINIO=7

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

# MinIO objects (plain tar: the videos are already compressed)
mkdir -p "$BACKUPS/minio"
mtar="$BACKUPS/minio/minio-$ts.tar"
tar -cf "$mtar.partial" -C "$DATA" minio && mv "$mtar.partial" "$mtar" \
  || { echo "MinIO tar failed"; rm -f "$mtar.partial"; exit 1; }
echo "minio -> $mtar ($(du -h "$mtar" | cut -f1))"
ls -1t "$BACKUPS"/minio/minio-*.tar | tail -n +$((KEEP_MINIO + 1)) | while read -r old; do
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
gsutil -q -m rsync -r -x '^minio/' "$BACKUPS" "$bucket/postgres" || rc=2
gsutil -q -m rsync -r "$DATA/minio" "$bucket/minio" || rc=2
[ $rc = 0 ] && echo "BACKUP OK -> $bucket" || echo "BACKUP: GCS copy FAILED (local dump kept at $out)"
exit $rc
