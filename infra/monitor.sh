#!/bin/bash
# Health monitor: run from cron every 5 min. Alerts (infra/alert.sh) once per new problem:
#   - a container that restarted since the last run, is unhealthy, or is not running
#   - render / voice / words jobs and studio videos that failed since the last run
#   - the nightly backup unit failed, or the newest dump is older than 36 h
# State (last run time, restart counts, open problems) lives in /srv/eduvid/data/monitor.state.
#   */5 * * * * /srv/eduvid/app/infra/monitor.sh >/dev/null 2>&1
set -u
cd "$(dirname "$0")/.." || exit 1
. infra/alert.sh

DATA=/srv/eduvid/data
STATE="${MONITOR_STATE:-$DATA/monitor.state}"
now=$(date +%s)
last=$now
declare -A prev_restarts=() prev_open=()
if [ -r "$STATE" ]; then
  while read -r kind key val; do
    case "$kind" in
      last) last=$key ;;
      restarts) prev_restarts[$key]=$val ;;
      open) prev_open[$key]=1 ;;
    esac
  done < "$STATE"
fi

declare -A open=()
new=()
problem() {            # problem <key> <message>: alert once while the problem lasts
  open[$1]=1
  [ -n "${prev_open[$1]:-}" ] || new+=("$2")
}

# ---- containers (long-running services of this compose project; one-off runs excluded) ----
declare -A restarts=()
while read -r name count health status; do
  name=${name#/}
  restarts[$name]=$count
  case "$name" in *minio-init*) continue ;; esac
  if [ -n "${prev_restarts[$name]:-}" ] && [ "$count" -gt "${prev_restarts[$name]}" ]; then
    new+=("$name restarted $((count - prev_restarts[$name])) time(s) in the last check (total $count)")
  fi
  [ "$status" = running ] || problem "down:$name" "$name is $status"
  [ "$health" = unhealthy ] && problem "unhealthy:$name" "$name is unhealthy"
done < <(docker ps -a --filter label=com.docker.compose.project=eduvid --filter label=com.docker.compose.oneoff=False \
           -q | xargs -r docker inspect -f \
           '{{.Name}} {{.RestartCount}} {{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}} {{.State.Status}}')

# ---- failed jobs and videos since the last run ----
sql="SELECT 'job ' || id || ' (' || type || ') failed: ' || left(replace(coalesce(error,''), E'\n', ' '), 200)
       FROM jobs WHERE status = 'failed' AND finished_at > to_timestamp($last)
     UNION ALL
     SELECT 'video \"' || left(title, 60) || '\" failed: ' || left(replace(coalesce(error,''), E'\n', ' '), 200)
       FROM studio_videos WHERE status = 'failed' AND updated_at > to_timestamp($last)"
if out=$(docker compose exec -T postgres sh -c "psql -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Atc \"\$0\"" "$sql" 2>&1); then
  while IFS= read -r line; do [ -n "$line" ] && new+=("$line"); done <<< "$out"
else
  problem "db" "monitor could not query postgres: ${out:0:200}"
fi

# ---- backups ----
systemctl is-failed --quiet eduvid-backup.service && problem "backup-failed" "nightly backup failed: journalctl -u eduvid-backup"
newest=$(ls -1t "$DATA"/backups/eduvid-*.dump 2>/dev/null | head -1)
if [ -z "$newest" ] || [ $((now - $(stat -c %Y "$newest"))) -gt $((36 * 3600)) ]; then
  problem "backup-stale" "no database dump in the last 36 h (newest: ${newest:-none})"
fi

# ---- alert, save state ----
if [ ${#new[@]} -gt 0 ]; then
  msg=$(printf '%s\n' "${new[@]}" | head -20)
  [ ${#new[@]} -gt 20 ] && msg+=$'\n'"… and $(( ${#new[@]} - 20 )) more"
  alert "$msg"
fi
{
  echo "last $now"
  for k in "${!restarts[@]}"; do echo "restarts $k ${restarts[$k]}"; done
  for k in "${!open[@]}"; do echo "open $k 1"; done
} > "$STATE.tmp" && mv "$STATE.tmp" "$STATE"
echo "monitor: ${#new[@]} new alert(s), ${#open[@]} open problem(s)"
