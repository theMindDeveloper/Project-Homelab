#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  new-lxc.sh - create an unprivileged Debian LXC on Proxmox, consistently
#
#  Every container in this lab is created the same way. Doing that by hand in
#  the web UI produces containers that differ in ways you only discover months
#  later: one has nesting off, one has no static IP, one boots on host start
#  and one does not. This script is the single definition of "normal".
#
#  Run it ON a Proxmox node, as root.
#
#  USAGE
#      ./new-lxc.sh --id 110 --name svc-example --ip 192.168.178.90
#
#  OPTIONS
#      --id       <int>    container ID                       (required)
#      --name     <str>    hostname                           (required)
#      --ip       <addr>   IPv4 without prefix                (required)
#      --cores    <int>    default 2
#      --memory   <MB>     default 2048
#      --swap     <MB>     default 512
#      --disk     <GB>     default 16
#      --storage  <str>    default local-lvm
#      --bridge   <str>    default vmbr0
#      --docker            add keyctl=1 as well, for running Docker inside
#      --dry-run           print the pct command and exit
# ---------------------------------------------------------------------------

set -euo pipefail

GATEWAY="192.168.178.1"
NAMESERVER="192.168.178.178"      # AdGuard Home
PREFIX="24"
TEMPLATE_STORAGE="local"
TEMPLATE="debian-12-standard_12.7-1_amd64.tar.zst"

CTID=""; NAME=""; IP=""
CORES=2; MEMORY=2048; SWAP=512; DISK=16
STORAGE="local-lvm"; BRIDGE="vmbr0"
DOCKER=0; DRYRUN=0

die() { echo "error: $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --id)      CTID="$2"; shift 2 ;;
    --name)    NAME="$2"; shift 2 ;;
    --ip)      IP="$2"; shift 2 ;;
    --cores)   CORES="$2"; shift 2 ;;
    --memory)  MEMORY="$2"; shift 2 ;;
    --swap)    SWAP="$2"; shift 2 ;;
    --disk)    DISK="$2"; shift 2 ;;
    --storage) STORAGE="$2"; shift 2 ;;
    --bridge)  BRIDGE="$2"; shift 2 ;;
    --docker)  DOCKER=1; shift ;;
    --dry-run) DRYRUN=1; shift ;;
    -h|--help) sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *)         die "unknown option: $1" ;;
  esac
done

[[ -n "$CTID" && -n "$NAME" && -n "$IP" ]] || die "--id, --name and --ip are required"
[[ "$CTID" =~ ^[0-9]+$ ]] || die "--id must be numeric"
[[ "$IP" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || die "--ip must be a bare IPv4 address"

command -v pct >/dev/null || die "pct not found - run this on a Proxmox node"
pct status "$CTID" >/dev/null 2>&1 && die "container $CTID already exists"

# Fail early rather than half way through: a used address is the single most
# common cause of a container that creates fine and is then unreachable.
if ping -c1 -W1 "$IP" >/dev/null 2>&1; then
  die "$IP already answers ping - pick another address"
fi

FEATURES="nesting=1"
(( DOCKER )) && FEATURES="nesting=1,keyctl=1"

if ! pveam list "$TEMPLATE_STORAGE" 2>/dev/null | grep -q "$TEMPLATE"; then
  echo "template $TEMPLATE not present, downloading ..."
  (( DRYRUN )) || { pveam update; pveam download "$TEMPLATE_STORAGE" "$TEMPLATE"; }
fi

CMD=(pct create "$CTID" "${TEMPLATE_STORAGE}:vztmpl/${TEMPLATE}"
  --hostname     "$NAME"
  --cores        "$CORES"
  --memory       "$MEMORY"
  --swap         "$SWAP"
  --rootfs       "${STORAGE}:${DISK}"
  --net0         "name=eth0,bridge=${BRIDGE},ip=${IP}/${PREFIX},gw=${GATEWAY}"
  --nameserver   "$NAMESERVER"
  --onboot       1
  --unprivileged 1
  --features     "$FEATURES"
  --start        0)

if (( DRYRUN )); then
  printf '%q ' "${CMD[@]}"; echo
  exit 0
fi

"${CMD[@]}"
pct start "$CTID"

echo
echo "container $CTID ($NAME) is up at $IP"
echo "next:  pct enter $CTID"
(( DOCKER )) && echo "then:  bash scripts/install-docker.sh   # copy it in first"
echo
echo "Remember to add it to inventory/inventory.yml. The inventory is the"
echo "source of truth; a container that is not in it does not officially exist."
