# Sourced by the infra scripts: `alert "message"` writes to syslog (tag eduvid) and /srv/eduvid/data/alerts.log and,
# when ALERT_WEBHOOK_URL is set in /srv/eduvid/app/.env, posts it there:
#   ntfy (https://ntfy.sh/<topic> or a self-hosted ntfy URL): plain text body
#   anything else (Slack / Google Chat / Discord incoming webhook): JSON {"text": …, "content": …}
ALERT_LOG="${ALERT_LOG:-/srv/eduvid/data/alerts.log}"
ALERT_ENV="${ALERT_ENV:-/srv/eduvid/app/.env}"

alert_env_get() { [ -r "$ALERT_ENV" ] && sed -n "s/^$1=\([^ #]*\).*/\1/p" "$ALERT_ENV" | tail -1; }

alert() {
  local msg="[eduvid $(hostname -s)] $*" url
  logger -t eduvid "$msg"
  echo "$(date -Is) $msg" >> "$ALERT_LOG"
  url="${ALERT_WEBHOOK_URL:-$(alert_env_get ALERT_WEBHOOK_URL)}"
  [ -n "$url" ] || return 0
  case "$url" in
    *ntfy*) curl -fsS -m 10 -H "Title: EduVid alert" -d "$msg" "$url" >/dev/null ;;
    *) curl -fsS -m 10 -H 'Content-Type: application/json' \
         --data "$(python3 -c 'import json,sys; print(json.dumps({"text": sys.argv[1], "content": sys.argv[1]}))' "$msg")" \
         "$url" >/dev/null ;;
  esac || logger -t eduvid "alert webhook failed for: $msg"
}
