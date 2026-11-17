#!/bin/bash
# Disk alarm (spec §10): run from cron every 15 min. Above the threshold, alerts (infra/alert.sh: syslog tag eduvid,
# /srv/eduvid/data/alerts.log, and ALERT_WEBHOOK_URL if set) at most once every 6 h while it stays over.
# Prints the usage either way. Exit 1 when over.
#   */15 * * * * /srv/eduvid/app/infra/disk_alarm.sh >/dev/null 2>&1
set -u
cd "$(dirname "$0")" || exit 1
ALERT_LOG="${DISK_ALARM_LOG:-/srv/eduvid/data/alerts.log}"
. ./alert.sh
LIMIT="${DISK_ALARM_PCT:-80}"
PATH_CHECK="${DISK_ALARM_PATH:-/srv/eduvid/data}"
STAMP="${DISK_ALARM_STAMP:-/srv/eduvid/data/.disk_alarm_last}"
pct=$(df --output=pcent "$PATH_CHECK" | tail -1 | tr -dc '0-9')
echo "disk ${pct}% used on $PATH_CHECK (alarm at ${LIMIT}%)"
if [ "$pct" -gt "$LIMIT" ]; then
  last=$(cat "$STAMP" 2>/dev/null || echo 0)
  if [ $(( $(date +%s) - last )) -ge $((6 * 3600)) ]; then
    alert "WARN disk > ${LIMIT}%: ${pct}% used on $PATH_CHECK"
    date +%s > "$STAMP"
  fi
  exit 1
fi
rm -f "$STAMP"
