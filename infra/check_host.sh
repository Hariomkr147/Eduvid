#!/usr/bin/env bash
# M0 host check. Prints "HOST OK" and exits 0 only when every check passes;
# otherwise prints the first failing check and exits 1.
set -uo pipefail

ROOT=/srv/eduvid
OWNER=${EDUVID_OWNER:-hariom}
MIN_FREE_TB=2

fail() { echo "FAIL: $*"; exit 1; }

command -v docker >/dev/null 2>&1 || fail "docker is not installed"
docker info >/dev/null 2>&1 || fail "docker daemon not reachable by $(id -un) (docker group? newgrp docker)"
docker compose version >/dev/null 2>&1 || fail "docker compose v2 plugin missing"

n=$(docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi -L 2>/dev/null | grep -c "NVIDIA L4")
[ "$n" = "4" ] || fail "expected 4 NVIDIA L4 GPUs inside a container, saw ${n:-0}"

for d in app data/postgres data/minio data/backups data/scratch; do
  [ -d "$ROOT/$d" ] || fail "missing dir $ROOT/$d"
  if [ "$(id -un)" = "$OWNER" ]; then
    [ -w "$ROOT/$d" ] || fail "$ROOT/$d is not writable by $OWNER"
  else
    sudo -n -u "$OWNER" test -w "$ROOT/$d" || fail "$ROOT/$d is not writable by $OWNER"
  fi
done

free_kb=$(df -Pk / | awk 'NR==2{print $4}')
min_kb=$((MIN_FREE_TB * 1000 * 1000 * 1000))   # decimal TB, as df -h/-H reports disks
[ "$free_kb" -ge "$min_kb" ] || fail "less than ${MIN_FREE_TB} TB free on / ($((free_kb / 1000 / 1000)) GB)"

echo "HOST OK"
