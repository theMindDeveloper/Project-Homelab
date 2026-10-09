# Runbook 26 · Test dashboard and alert changes before they go live

**Goal** Know that a changed dashboard or alert rule works **before** it reaches
the real Grafana: every query valid, no false alarm on deploy, Grafana still
starts, the message reads right.

**Time** 5 minutes for a dashboard change, 15 for an alert change.
**Prerequisites** The generators in [`scripts/grafana/`](../scripts/grafana/),
Python 3. For step 4, any Linux machine with ~1.5 GB free in `/tmp`.
**Reverses cleanly?** Nothing here touches the real Grafana.

Why this matters: [docs/24 · Testing alerts](../docs/24-alerting.md#testing-alerts-before-they-reach-the-phone).
Every step below caught a real mistake when this lab was built.

---

## 1 · Regenerate

```bash
python3 scripts/grafana/gen_all.py       # dashboards -> compose/monitoring/grafana/dashboards/
python3 scripts/grafana/gen_alerts.py    # alert rules -> .../provisioning/alerting/rules.yml
```

---

## 2 · Run every query against the live data

[`check_dashboards.py`](../scripts/grafana/check_dashboards.py) runs every panel
query and every alert-rule query against Prometheus and Loki (read-only, GET
only), tries the Hosts dashboard once per host, and checks that no panels
overlap.

Loki usually has no published port, so run the check on the monitoring Docker
network (`stacks_monitoring` here: compose project `stacks` + network
`monitoring`), from the folder with this repository:

```bash
docker run --rm --network stacks_monitoring -v "$PWD":/w:ro python:3.13-alpine \
  python -I /w/scripts/grafana/check_dashboards.py --quiet \
    --prom http://prometheus:9090 --loki http://loki:3100 \
    /w/compose/monitoring/grafana/dashboards/*.json \
    --rules /w/compose/monitoring/grafana/provisioning/alerting/rules.yml
```

(Prometheus only, from any machine: `--prom http://192.168.178.87:9090`,
without `--loki`.)

| Result | Do |
|---|---|
| `ERR` | the query is broken. Fix it. Exit code is 1 |
| `EMPTY` | valid but no data right now. Each one needs a reason you can say out loud ("no game is running", "the Pi has no pressure data") |
| `ok` | fine |

**For alert rules, look at the values too.** Every rule here returns 1 for
"problem", so run the rule queries in Grafana → *Explore* and make sure none is
1 right now, unless something really is broken. A rule that is 1 today pages you
the minute it is deployed.

---

## 3 · Unit-test tricky alert logic with promtool

For rules with time logic ("was running, now stopped"), make up the data and
assert the answer. `promtool` comes in the Prometheus release tarball.

```yaml
# rules.yml - the expression as a recording rule
groups:
  - name: t
    rules:
      - record: game_stopped
        expr: max by (platform, server) ((max_over_time(game_server_up[10m]) == bool 1) * (game_server_up == bool 0))
```

```yaml
# test.yml
rule_files: [rules.yml]
evaluation_interval: 1m
tests:
  - interval: 1m
    input_series:
      - series: 'game_server_up{platform="amp",server="Minecraft"}'
        values: '1x5 0x20'           # runs 5 minutes, then stops
      - series: 'game_server_up{platform="pterodactyl",server="zomboid"}'
        values: '0x25'               # never ran
      - series: 'game_server_up{platform="pterodactyl",server="minecraft"}'
        values: '1x3 _x20'           # panel unreachable after 3 min (node switched off)
    promql_expr_test:
      - expr: game_stopped
        eval_time: 7m                # 2 min after the stop
        exp_samples:
          - {labels: 'game_stopped{platform="amp",server="Minecraft"}', value: 1}
          - {labels: 'game_stopped{platform="pterodactyl",server="minecraft"}', value: 0}
          - {labels: 'game_stopped{platform="pterodactyl",server="zomboid"}', value: 0}
      - expr: game_stopped
        eval_time: 20m               # >10 min later: ended by itself
        exp_samples:
          - {labels: 'game_stopped{platform="amp",server="Minecraft"}', value: 0}
          - {labels: 'game_stopped{platform="pterodactyl",server="zomboid"}', value: 0}
```

```bash
promtool test rules test.yml       # SUCCESS
promtool check config compose/monitoring/prometheus/prometheus.yml
```

---

## 4 · Load everything into a throwaway Grafana

A broken provisioning file can stop the real Grafana from starting. So start a
second, temporary Grafana of the **same version** with the new files and look.

```bash
mkdir -p /tmp/gf && cd /tmp/gf
curl -sL https://dl.grafana.com/oss/release/grafana-13.1.3.linux-amd64.tar.gz | tar xz
cp -r /path/to/repo/compose/monitoring/grafana/provisioning prov
mkdir -p data logs dash && cp /path/to/repo/compose/monitoring/grafana/dashboards/*.json dash/
sed -i 's#/var/lib/grafana/dashboards#/tmp/gf/dash#' prov/dashboards/homelab.yml
cat > test.ini <<'EOF'
[server]
http_addr = 127.0.0.1
http_port = 13000
[paths]
data = /tmp/gf/data
logs = /tmp/gf/logs
provisioning = /tmp/gf/prov
[analytics]
reporting_enabled = false
check_for_updates = false
EOF
TELEGRAM_BOT_TOKEN=123:TEST TELEGRAM_CHAT_ID=1 setsid ./grafana-13.1.3/bin/grafana server \
  --homepath /tmp/gf/grafana-13.1.3 --config /tmp/gf/test.ini > /tmp/gf/stdout.log 2>&1 < /dev/null &
until curl -s http://127.0.0.1:13000/api/health | grep -q '"ok"'; do sleep 2; done; echo up
```

Then ask it what it loaded (default login of a fresh Grafana: admin / admin):

```bash
G="curl -s -u admin:admin http://127.0.0.1:13000"
$G/api/v1/provisioning/alert-rules    | python3 -c "import json,sys; print(len(json.load(sys.stdin)), 'rules')"
$G/api/v1/provisioning/contact-points | python3 -m json.tool | grep -E '"name"|chatid'
$G/api/v1/provisioning/policies       | python3 -m json.tool | head -30
$G/api/v1/provisioning/mute-timings   | python3 -m json.tool
$G/api/search?type=dash-db            | python3 -m json.tool | grep title
grep -iE "level=error" logs/grafana.log | grep -iE "provision|alert" | grep -v plugins
```

What to look for:

- the number of rules is right, and each math expression shows `$A`, **not**
  `$$A` (alert-rule files are not variable-expanded; contact points are: the
  `chatid` must show `1`, the test value, not `${TELEGRAM_CHAT_ID}`)
- no provisioning errors in the log
- after a minute, *Alerting → Alert rules* (on port 13000) shows errors like
  "lookup prometheus ... server misbehaving": **expected**, this Grafana cannot
  reach your data. A **parse** error is a real bug.

**Stop it by its port**, not with `pkill -f grafana` (that pattern can match the
shell running the command and kill it instead):

```bash
kill $(ss -ltnpH 'sport = :13000' | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u)
```

---

## 5 · Read the message before your phone does

The same throwaway Grafana renders the Telegram template with fake alerts.
A resolved alert needs an `endsAt` in the past; the `status` field is ignored.

```bash
python3 - <<'EOF'
import json, urllib.request, base64
tpl = open('/tmp/gf/prov/alerting/templates.yml').read().split('template: |\n', 1)[1]
tpl = "\n".join(l[6:] for l in tpl.splitlines())
body = {"name": "homelab", "template": tpl, "alerts": [
  {"labels": {"alertname": "Host down", "severity": "critical", "node": "pve3"},
   "annotations": {"summary": "pve3 is DOWN", "description": "Prometheus can't reach pve3 for 2 minutes."},
   "startsAt": "2026-10-08T20:00:00Z"},
  {"labels": {"alertname": "Disk over 80%", "severity": "warning"},
   "annotations": {"summary": "pi / is over 80% full"},
   "startsAt": "2026-10-08T18:00:00Z", "endsAt": "2026-10-08T19:00:00Z"}]}
req = urllib.request.Request("http://127.0.0.1:13000/api/alertmanager/grafana/config/api/v1/templates/test",
    data=json.dumps(body).encode(), method="POST",
    headers={"Content-Type": "application/json", "Authorization": "Basic " + base64.b64encode(b"admin:admin").decode()})
for r in json.load(urllib.request.urlopen(req)).get("results") or []:
    print(r["text"])
EOF
```

---

## 6 · Deploy, then one real test

Copy the files to the real Grafana host, restart Grafana if alerting files
changed (dashboards reload by themselves), check its log for
`finished to provision alerting`, and press **Contact points → telegram → Test**.

---

## If it goes wrong

| Symptom | Cause |
|---|---|
| `check_dashboards.py`: everything Loki is "skipped" | no `--loki`, or Loki not reachable from where it runs (use the Docker-network command) |
| `ERR ... parse error` in a Loki query | LogQL is stricter than it looks: label filters need quotes, regexes double backslashes inside JSON |
| throwaway Grafana never answers | port 13000 taken, or `/tmp` full (`df -h /tmp`, the tarball unpacks to ~1 GB) |
| `rules: 0` | wrong path in `test.ini`, or a YAML error: `grep -i error logs/grafana.log` |
| your shell vanished when stopping it | `pkill -f` matched the shell itself; stop by port |
