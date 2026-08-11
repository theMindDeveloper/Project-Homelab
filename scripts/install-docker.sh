#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  install-docker.sh - Docker Engine + Compose plugin on a fresh Debian LXC
#
#  Run this INSIDE the container (pct enter <id>), as root.
#
#  This installs from Docker's own apt repository, not from Debian's
#  `docker.io` package. The Debian package lags by a long way and does not
#  ship the `docker compose` plugin, which means you end up with the old
#  standalone `docker-compose` binary and its subtly different behaviour.
# ---------------------------------------------------------------------------

set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }

# --- sanity: is nesting actually on? ---------------------------------------
# Without nesting=1 on the container, the daemon starts and then dies with a
# cgroup error that reads like a kernel problem. Check first, save an hour.
if [[ ! -w /sys/fs/cgroup ]]; then
  echo "WARNING: /sys/fs/cgroup is not writable."
  echo "This container probably lacks nesting=1. On the Proxmox host, run:"
  echo "    pct set <id> --features nesting=1,keyctl=1 && pct reboot <id>"
  echo
fi

apt-get update
apt-get install -y --no-install-recommends ca-certificates curl gnupg

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

cat > /etc/apt/sources.list.d/docker.list <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable
EOF

apt-get update
apt-get install -y \
  docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin

systemctl enable --now docker

# --- log rotation ----------------------------------------------------------
# Docker's default json-file driver has NO size limit. A chatty container will
# quietly fill the container's disk with a single log file. This is the most
# common cause of a homelab running out of space.
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
EOF
systemctl restart docker

docker --version
docker compose version
echo
echo "Docker is ready. Verify with:  docker run --rm hello-world"
