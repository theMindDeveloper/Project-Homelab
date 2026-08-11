#!/usr/bin/env bash
# ---------------------------------------------------------------------------
#  check-secrets.sh - block anything private from reaching a public repository
#
#  This repository publishes a private network on purpose. The rule that makes
#  that safe is in docs/99-security-notes.md:
#
#      Publish the design. Never publish the reachability.
#
#  Discipline enforces that rule badly. This script enforces it mechanically.
#
#  USAGE
#      ./scripts/check-secrets.sh              scan the staged diff (pre-commit)
#      ./scripts/check-secrets.sh --all        scan every tracked file
#      ./scripts/check-secrets.sh --install    install as a git pre-commit hook
#
#  EXIT CODES
#      0   clean
#      1   at least one finding - the commit is blocked
#      2   usage or environment error
#
#  FALSE POSITIVES
#      Add the exact offending string to .secretsallow, one per line.
#      Never weaken a pattern to make a warning go away.
# ---------------------------------------------------------------------------

set -euo pipefail

RED=$'\033[0;31m'; YEL=$'\033[0;33m'; GRN=$'\033[0;32m'; DIM=$'\033[2m'; OFF=$'\033[0m'
[[ -t 1 ]] || { RED=""; YEL=""; GRN=""; DIM=""; OFF=""; }

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALLOWFILE="$REPO_ROOT/.secretsallow"
MODE="staged"
FINDINGS=0

usage() { sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 2; }

# --- patterns ---------------------------------------------------------------
# Each entry: <label>|<extended regex>
# Ordered from "certainly fatal" to "probably a mistake".
# All matching is case-INSENSITIVE. POSTGRES_PASSWORD= and postgres_password=
# are the same mistake, and a scanner that catches only one of them is worse
# than useless because it feels like coverage.
PATTERNS=(
  "private key block|-----BEGIN [A-Z ]*PRIVATE KEY-----"
  "PGP private key|-----BEGIN PGP PRIVATE KEY BLOCK-----"
  "AWS access key id|AKIA[0-9A-Z]{16}"
  "generic API token|(api[_-]?key|apikey|access[_-]?token|auth[_-]?token|bearer)[\"' ]*[:=][\"' ]*[A-Za-z0-9/+_-]{20,}"
  "JWT|eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\."
  "Cloudflare tunnel token|[A-Za-z0-9+/=]{100,}"
  "UUID (tunnel or connector id)|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
  "MAC address|([0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}"
  "DuckDNS hostname|[A-Za-z0-9_-]+\.duckdns\.org"
  "no-ip / dyndns hostname|[A-Za-z0-9_-]+\.(ddns\.net|no-ip\.(org|com)|dynv6\.net)"
  # At least three colon groups, so a port mapping like "2283:2283" is not
  # mistaken for a 2000::/3 global unicast address.
  "global IPv6 address|(^|[^0-9a-fA-F:])2[0-9a-fA-F]{3}:[0-9a-fA-F]{0,4}:[0-9a-fA-F]{0,4}:[0-9a-fA-F:]{2,}"
  "password assignment|(password|passwd|secret|passphrase)[\"' ]*[:=][\"' ]*[^ \"'<\$}]{6,}"
  "Vaultwarden admin token|ADMIN_TOKEN[\"' ]*[:=][\"' ]*\\\$?[A-Za-z0-9]"
)

# Private key material is caught by content ("-----BEGIN ... PRIVATE KEY-----").
# A key committed under its usual NAME is caught here instead. Matching the
# string "id_ed25519" in prose would flag every ssh example in the wiki, which
# is how a scanner trains you to ignore it.
FILENAME_PATTERNS=(
  "SSH private key file|^(id_rsa|id_ed25519|id_ecdsa|id_dsa)$"
  "TLS private key file|\.(key|pem|pfx|p12)$"
  "credentials file|(^|/)(credentials|secrets?|\.env)$"
  "Cloudflare tunnel credentials|^[0-9a-f]{8}-[0-9a-f-]{27}\.json$"
)

# Public IPv4 gets its own pass because it needs logic, not just a regex:
# every dotted quad is extracted, then anything private/reserved is discarded.
IPV4_RE='(^|[^0-9.])([0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})([^0-9.]|$)'

is_private_ipv4() {
  local ip="$1" a b
  IFS=. read -r a b _ _ <<<"$ip"
  [[ "$a" =~ ^[0-9]+$ && "$b" =~ ^[0-9]+$ ]] || return 0
  (( a == 10 ))                                  && return 0   # RFC1918
  (( a == 172 && b >= 16 && b <= 31 ))           && return 0   # RFC1918
  (( a == 192 && b == 168 ))                     && return 0   # RFC1918
  (( a == 127 ))                                 && return 0   # loopback
  (( a == 169 && b == 254 ))                     && return 0   # link-local
  (( a == 100 && b >= 64 && b <= 127 ))          && return 0   # CGNAT
  (( a == 0 ))                                   && return 0   # this network
  (( a >= 224 ))                                 && return 0   # multicast / reserved
  (( a == 192 && b == 0 ))                       && return 0   # documentation
  (( a == 198 && b >= 18 && b <= 19 ))           && return 0   # benchmarking
  (( a == 203 && b == 0 ))                       && return 0   # documentation
  return 1
}

# An example file is SUPPOSED to contain "PASSWORD=change-me". Flagging those
# teaches you to ignore the scanner, which is the only way it can actually fail.
looks_like_placeholder() {
  printf '%s' "$1" | grep -qiE '(change[-_]?me|example|placeholder|your[-_]|redacted|xxx+|hunter2|<[a-z]|\$\{|\.\.\.|=$|:$)'
}

allowed() {
  [[ -f "$ALLOWFILE" ]] || return 1
  grep -qxF -- "$1" <(grep -v -e '^\s*#' -e '^\s*$' "$ALLOWFILE") 2>/dev/null
}

# Files that describe the patterns rather than contain secrets. Scanning them
# means the scanner reports itself, forever.
skip_file() {
  case "${1#./}" in
    scripts/check-secrets.sh|.gitignore|.secretsallow|.git/*) return 0 ;;
  esac
  return 1
}

# draw.io embeds icon artwork as base64 data URIs. Those lines are megabytes of
# legitimate image data and will trip every entropy-shaped pattern.
skip_line() {
  case "$1" in
    *"data:image/"*) return 0 ;;
  esac
  return 1
}

scan_filename() {                                 # path
  local path="${1#./}" base entry label re
  base="$(basename "$path")"
  for entry in "${FILENAME_PATTERNS[@]}"; do
    label="${entry%%|*}"; re="${entry#*|}"
    if printf '%s' "$base" | grep -qiE -- "$re"; then
      allowed "$path" && continue
      report "$label - do not commit this file" "$path" "0" "$path"
    fi
  done
}

report() {                                        # label file line text
  FINDINGS=$((FINDINGS + 1))
  printf '%s  FINDING%s  %s\n' "$RED" "$OFF" "$1"
  printf '  %s%s:%s%s\n' "$DIM" "$2" "$3" "$OFF"
  printf '  %s\n\n' "$(printf '%s' "$4" | cut -c1-160)"
}

# One grep pass per pattern per FILE, not per line. Doing it per line spawns
# tens of thousands of processes on a repository this size and takes minutes.
scan_content() {                                  # file  <content on stdin>
  local file="$1" tmp entry label re n text hit ip
  tmp="$(mktemp)"
  # Drop embedded base64 artwork before scanning; it trips every
  # entropy-shaped pattern and is megabytes long.
  grep -v 'data:image/' > "$tmp" || true

  for entry in "${PATTERNS[@]}"; do
    label="${entry%%|*}"; re="${entry#*|}"
    while IFS= read -r match; do
      [[ -n "$match" ]] || continue
      n="${match%%:*}"
      text="${match#*:}"
      hit="$(printf '%s' "$text" | grep -oiE -- "$re" | head -1)"
      allowed "$hit" && continue
      [[ "$label" == "password assignment" ]] && looks_like_placeholder "$text" && continue
      report "$label" "$file" "$n" "$text"
    done < <(grep -niE -- "$re" "$tmp" 2>/dev/null || true)
  done

  # Public IPv4 needs logic, not just a regex: extract every dotted quad with
  # its line number, then discard anything private or reserved.
  while IFS= read -r match; do
    [[ -n "$match" ]] || continue
    n="${match%%:*}"
    text="${match#*:}"
    while read -r ip; do
      [[ -n "$ip" ]] || continue
      is_private_ipv4 "$ip" && continue
      allowed "$ip" && continue
      report "public IPv4 address ($ip)" "$file" "$n" "$text"
    done < <(printf '%s' "$text" | grep -oE '[0-9]{1,3}(\.[0-9]{1,3}){3}')
  done < <(grep -nE -- "$IPV4_RE" "$tmp" 2>/dev/null || true)

  rm -f "$tmp"
}

# --- entry point ------------------------------------------------------------
case "${1:-}" in
  --all)     MODE="all" ;;
  --install) MODE="install" ;;
  -h|--help) usage ;;
  "")        MODE="staged" ;;
  *)         usage ;;
esac

cd "$REPO_ROOT"

if [[ "$MODE" == "install" ]]; then
  git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repository" >&2; exit 2; }
  hook="$(git rev-parse --git-dir)/hooks/pre-commit"
  printf '#!/usr/bin/env sh\nexec ./scripts/check-secrets.sh\n' > "$hook"
  chmod +x "$hook"
  echo "${GRN}installed${OFF} $hook"
  exit 0
fi

echo "${DIM}scanning ($MODE) ...${OFF}"

if [[ "$MODE" == "all" ]]; then
  mapfile -t files < <(git ls-files 2>/dev/null)
  # A freshly initialised repository with nothing staged lists no files, and a
  # scanner that silently scans nothing is worse than no scanner.
  if (( ${#files[@]} == 0 )); then
    mapfile -t files < <(find . -type f -not -path './.git/*')
  fi
  for f in "${files[@]}"; do
    [[ -f "$f" ]] || continue
    skip_file "$f" && continue
    scan_filename "$f"
    file "$f" 2>/dev/null | grep -qiE 'image|binary|archive|compressed' && continue
    scan_content "$f" < "$f"
  done
else
  git rev-parse --git-dir >/dev/null 2>&1 || { echo "not a git repository - use --all" >&2; exit 2; }
  while IFS= read -r f; do
    [[ -f "$f" ]] || continue
    skip_file "$f" && continue
    scan_filename "$f"
    file "$f" 2>/dev/null | grep -qiE 'image|binary|archive|compressed' && continue
    git diff --cached -U0 -- "$f" | grep '^+' | grep -v '^+++' | sed 's/^+//' | scan_content "$f"
  done < <(git diff --cached --name-only --diff-filter=ACM)
fi

if (( FINDINGS > 0 )); then
  echo "${RED}${FINDINGS} finding(s). Commit blocked.${OFF}"
  echo "${YEL}If a finding is genuinely safe, add the exact string to .secretsallow.${OFF}"
  echo "${YEL}Do not weaken a pattern to silence it.${OFF}"
  exit 1
fi

echo "${GRN}clean${OFF}"
exit 0
