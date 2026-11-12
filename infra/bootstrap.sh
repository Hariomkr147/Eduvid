#!/usr/bin/env bash
# Host setup for EduVid (M0). Safe to re-run. Run as root: sudo bash infra/bootstrap.sh
#  - Docker Engine + Compose v2 from Docker's official apt repo (chosen by /etc/os-release ID)
#  - NVIDIA Container Toolkit from NVIDIA's apt repo (never touches the driver packages)
#  - adds $EDUVID_OWNER (default hariom) to the docker group
#  - creates /srv/eduvid/{app,data/{postgres,minio,backups,scratch,models}}
# It never runs apt upgrade / full-upgrade.
set -euo pipefail

OWNER=${EDUVID_OWNER:-hariom}
ROOT=/srv/eduvid

[ "$(id -u)" = 0 ] || { echo "run as root (sudo bash $0)"; exit 1; }

. /etc/os-release
case "$ID" in
  debian) case "$VERSION_ID" in 12|13) ;; *) echo "unsupported Debian $VERSION_ID"; exit 1;; esac ;;
  ubuntu) case "$VERSION_ID" in 22.04|24.04) ;; *) echo "unsupported Ubuntu $VERSION_ID"; exit 1;; esac ;;
  *) echo "unsupported OS: $ID"; exit 1 ;;
esac

export DEBIAN_FRONTEND=noninteractive
apt_install() { apt-get install -y -q --no-upgrade "$@"; }

echo "== base packages"
apt-get update -q
apt_install ca-certificates curl gnupg git make jq

echo "== docker apt repo ($ID $VERSION_CODENAME)"
install -m 0755 -d /etc/apt/keyrings
if [ ! -s /etc/apt/keyrings/docker.asc ]; then
  curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
fi
cat > /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/$ID
Suites: $VERSION_CODENAME
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

echo "== nvidia container toolkit apt repo"
if [ ! -s /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg ]; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
fi
curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
  > /etc/apt/sources.list.d/nvidia-container-toolkit.list

apt-get update -q

echo "== docker engine"
apt_install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "== nvidia container toolkit (driver packages untouched)"
# Refuse to continue if apt would change any installed NVIDIA driver package.
if apt-get install -s --no-upgrade nvidia-container-toolkit \
    | grep -E '^(Inst|Remv) (nvidia-driver|nvidia-kernel|libcuda1|libnvidia-(gl|egl|ml|encode|cfg))' ; then
  echo "ABORT: installing the toolkit would change NVIDIA driver packages"; exit 1
fi
apt_install nvidia-container-toolkit
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker
systemctl enable docker containerd

echo "== docker group"
getent group docker >/dev/null || groupadd docker
id -nG "$OWNER" | tr ' ' '\n' | grep -qx docker || usermod -aG docker "$OWNER"

echo "== data dirs"
mkdir -p "$ROOT/app" "$ROOT"/data/{postgres,minio,backups,scratch,models}
chown "$OWNER:$OWNER" "$ROOT" "$ROOT/app" "$ROOT/data" "$ROOT"/data/{minio,backups,scratch,models}
# postgres data dir is owned by the container's postgres user (uid 999) once initialised;
# only fix ownership while it is still empty.
[ -z "$(ls -A "$ROOT/data/postgres")" ] && chown "$OWNER:$OWNER" "$ROOT/data/postgres"

echo "bootstrap done. Log out and back in (or 'newgrp docker'), then: bash infra/check_host.sh"
