#!/bin/bash
# Disk alarm (spec §10): run from cron every 15 min. Above the threshold, writes "WARN disk > 80% …" to syslog
# (tag eduvid) and /srv/eduvid/data/alerts.log. Prints the usage either way. Exit 1 when over.
#   */15 * * * * /srv/eduvid/app/infra/disk_alarm.sh >/dev/null 2>&1
set -u
LIMIT="${DISK_ALARM_PCT:-80}"
PATH_CHECK="${DISK_ALARM_PATH:-/srv/eduvid/data}"
LOG="${DISK_ALARM_LOG:-/srv/eduvid/data/alerts.log}"
pct=$(df --output=pcent "$PATH_CHECK" | tail -1 | tr -dc '0-9')
echo "disk ${pct}% used on $PATH_CHECK (alarm at ${LIMIT}%)"
if [ "$pct" -gt "$LIMIT" ]; then
  msg="WARN disk > ${LIMIT}%: ${pct}% used on $PATH_CHECK"
  logger -t eduvid "$msg"
  echo "$(date -Is) $msg" >> "$LOG"
  exit 1
fi
