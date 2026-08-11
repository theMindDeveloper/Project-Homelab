#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  backup-all.sh - vzdump every guest on this node, with a readable summary
#
#  Run on a Proxmox node, as root. Intended for cron:
#      15 3 * * *  /root/backup-all.sh --storage backup >> /var/log/backup.log 2>&1
#
#  Snapshot mode means no downtime. It is "crash consistent": the guest does
#  not know a backup happened, so a database mid-transaction is captured
#  mid-transaction. For the databases in this lab that is acceptable, because
#  they replay their write-ahead log on start. For anything where it is not,
#  dump the database separately before the snapshot runs.
# ---------------------------------------------------------------------------

set -euo pipefail

STORAGE="backup"
KEEP=7
EXCLUDE=""
MODE="snapshot"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --storage) STORAGE="$2"; shift 2 ;;
    --keep)    KEEP="$2"; shift 2 ;;
    --exclude) EXCLUDE="$2"; shift 2 ;;
    --mode)    MODE="$2"; shift 2 ;;
    -h|--help) sed -n '2,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

command -v vzdump >/dev/null || { echo "run this on a Proxmox node" >&2; exit 1; }

pvesm status | awk -v s="$STORAGE" '$1==s{found=1} END{exit !found}' \
  || { echo "storage '$STORAGE' does not exist - check: pvesm status" >&2; exit 1; }

START=$(date +%s)
echo "=== backup started $(date -Is) - storage=$STORAGE mode=$MODE keep=$KEEP"

ARGS=(--all 1 --storage "$STORAGE" --mode "$MODE" --compress zstd
      --prune-backups "keep-last=$KEEP" --notes-template '{{guestname}} {{node}}')
[[ -n "$EXCLUDE" ]] && ARGS+=(--exclude "$EXCLUDE")

vzdump "${ARGS[@]}"

END=$(date +%s)
echo "=== backup finished $(date -Is) in $(( (END - START) / 60 )) min"
echo
echo "--- what is on the storage now ---"
pvesm list "$STORAGE" | tail -20
echo
echo "--- free space ---"
pvesm status | awk 'NR==1 || $1=="'"$STORAGE"'"'
echo
echo "REMINDER: a backup you have never restored is not a backup."
echo "See runbooks/09-backup-restore-drill.md"
