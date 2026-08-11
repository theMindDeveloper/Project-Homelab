#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  health-check.sh - is everything in the inventory actually answering?
#
#  Glance already shows this in a browser. This is the version you can run
#  over SSH from a phone, pipe into a log, or call from cron.
#
#  USAGE
#      ./health-check.sh              check everything
#      ./health-check.sh --quiet      print only failures (good for cron)
#
#  Exits non-zero if anything is down, so cron will mail you.
# ---------------------------------------------------------------------------

set -uo pipefail

QUIET=0
[[ "${1:-}" == "--quiet" ]] && QUIET=1

GRN=$'\033[0;32m'; RED=$'\033[0;31m'; DIM=$'\033[2m'; OFF=$'\033[0m'
[[ -t 1 ]] || { GRN=""; RED=""; DIM=""; OFF=""; }

FAILED=0

# name | target | kind
# kind: http  = expect any HTTP response
#       tcp   = expect the port to accept a connection
#       ping  = expect an ICMP reply
TARGETS=(
  "P1 pve                | 192.168.178.20:8006  | tcp"
  "P2 pve2               | 192.168.178.50:8006  | tcp"
  "P3 pve3               | 192.168.178.77:8006  | tcp"
  "Raspberry Pi          | 192.168.178.178      | ping"
  "Nginx Proxy Manager   | 192.168.178.178:81   | http"
  "AdGuard Home UI       | 192.168.178.178:8000 | http"
  "AdGuard Home DNS      | 192.168.178.178:53   | dns"
  "Portainer 0           | 192.168.178.178:9442 | tcp"
  "LXC 102 docker        | 192.168.178.87       | ping"
  "Glance                | 192.168.178.87:8080  | http"
  "Vaultwarden           | 192.168.178.87:8081  | http"
  "Portainer 1           | 192.168.178.87:9443  | tcp"
  "Grafana               | 192.168.178.87:3000  | http"
  "Prometheus            | 192.168.178.87:9090  | http"
  "Apache                | 192.168.178.87:80    | http"
  "LXC 101 casaos        | 192.168.178.59:90    | http"
  "LXC 106 panel         | 192.168.178.84:80    | http"
  "LXC 105 wings         | 192.168.178.36       | ping"
  "LXC 107 amp-server    | 192.168.178.32:8080  | http"
)

check_tcp()  { timeout 3 bash -c "exec 3<>/dev/tcp/${1%%:*}/${1##*:}" 2>/dev/null; }
check_http() { curl -ksS -o /dev/null -m 5 "http://$1" 2>/dev/null; }
check_ping() { ping -c1 -W2 "$1" >/dev/null 2>&1; }
check_dns()  { command -v dig >/dev/null && dig +short +time=2 +tries=1 @"${1%%:*}" example.com >/dev/null 2>&1; }

printf '%s%s%s\n' "$DIM" "$(date -Is)" "$OFF"

for row in "${TARGETS[@]}"; do
  IFS='|' read -r name target kind <<<"$row"
  name="${name%"${name##*[![:space:]]}"}"
  target="$(echo "$target" | xargs)"
  kind="$(echo "$kind" | xargs)"

  start=$(date +%s%N)
  case "$kind" in
    tcp)  check_tcp  "$target" ;;
    http) check_http "$target" ;;
    ping) check_ping "$target" ;;
    dns)  check_dns  "$target" ;;
  esac
  ok=$?
  ms=$(( ($(date +%s%N) - start) / 1000000 ))

  if [[ $ok -eq 0 ]]; then
    (( QUIET )) || printf '  %sOK  %s %-22s %s%4s ms%s\n' "$GRN" "$OFF" "$name" "$DIM" "$ms" "$OFF"
  else
    printf '  %sDOWN%s %-22s %s(%s)%s\n' "$RED" "$OFF" "$name" "$DIM" "$target" "$OFF"
    FAILED=$((FAILED + 1))
  fi
done

echo
if (( FAILED )); then
  printf '%s%d service(s) down%s\n' "$RED" "$FAILED" "$OFF"
  exit 1
fi
printf '%sall services responding%s\n' "$GRN" "$OFF"
