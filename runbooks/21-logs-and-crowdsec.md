# Runbook 21 · Logs: Loki, Alloy, the firewall log and CrowdSec (watch only)

**Goal** SSH logins, every container's output and the OPNsense firewall log
collected in Loki with country and city, CrowdSec recognising attacks without
blocking anything, and the Security dashboard filled.

**Time** 45-60 minutes.
**Prerequisites** [Runbook 10](10-monitoring-stack.md) done (Prometheus and
Grafana running in compose project `stacks` on LXC 102). OPNsense web UI access.
**Reverses cleanly?** Yes. Nothing here blocks or changes traffic; OPNsense only
gets an extra log destination.

Concepts: [docs/23](../docs/23-logs-and-security-monitoring.md). Files:
[`compose/security/`](../compose/security/).

---

## 0 · The plan

```
 LXC 102 journal (SSH + all containers)  ─┐
                                          ├─> Alloy ──> Loki ──> Grafana
 OPNsense firewall log  (UDP 1514) ───────┘     (adds         └──> CrowdSec ──> Prometheus
                                                 country/city)        (watch only)
 AdGuard on the Pi ──> adguard-exporter ──> Prometheus
```

Memory: Loki 512 MB, Alloy 320 MB, CrowdSec 256 MB, adguard-exporter 64 MB at
most. On a quiet day the four use about 190 MB together.

---

## 1 · Check that container logs go to the journal

Alloy reads the **systemd journal** of LXC 102. Container output is only in the
journal if Docker's logging driver is `journald`:

```bash
docker info --format '{{.LoggingDriver}}'
```

- `journald`: good, go on.
- `json-file` (the Docker default): container output is in files under
  `/var/lib/docker/containers/` instead. Either switch Docker to journald
  (`/etc/docker/daemon.json`: `{"log-driver": "journald"}`, then
  `systemctl restart docker`, which restarts **every** container) or add a
  `loki.source.docker` block to Alloy instead. SSH is in the journal either way.

---

## 2 · Folders and config files

```bash
# on LXC 102, as root
mkdir -p /opt/security/{loki,alloy,crowdsec,geoip}
cd /path/to/repo/compose/security
cp loki.yml      /opt/security/loki/loki.yml
cp config.alloy  /opt/security/alloy/config.alloy
cp acquis.yaml   /opt/security/crowdsec/acquis.yaml
cp docker-compose.example.yml /opt/security/docker-compose.yml
cp adguard-exporter.env.example /opt/security/adguard-exporter.env
$EDITOR /opt/security/adguard-exporter.env && chmod 600 /opt/security/adguard-exporter.env

# Loki runs as user 10001 inside its container and must be able to read its config
chmod 644 /opt/security/loki/loki.yml
```

What each file does, in one line:

| File | Job |
|---|---|
| `loki.yml` | store on disk, keep 30 days (`retention_period: 720h`, compactor on), sane limits |
| `config.alloy` | read the journal and UDP 1514, split firewall and Apache lines into fields, add location, send to Loki |
| `acquis.yaml` | tell CrowdSec which Loki queries to read, and which parser each needs |

Open `config.alloy` once and read it top to bottom. It is commented, and it is the
heart of the whole setup.

---

## 3 · The location database (GeoIP)

```bash
cd /opt/security/geoip
curl -fsSL https://download.db-ip.com/free/dbip-city-lite-$(date +%Y-%m).mmdb.gz \
  | gunzip > dbip-city-lite.mmdb.new && mv dbip-city-lite.mmdb.new dbip-city-lite.mmdb
ls -lh dbip-city-lite.mmdb        # about 125 MB
```

DB-IP "IP to City Lite", free, CC BY 4.0, no account. Early in a month the new
file may not exist yet; use last month's (`$(date -d 'last month' +%Y-%m)`).

---

## 4 · Start the four containers

```bash
cd /opt/security
docker compose -p stacks -f docker-compose.yml config -q && echo OK
docker compose -p stacks -f docker-compose.yml up -d
docker ps --format '{{.Names}}\t{{.Status}}' | grep -E 'loki|alloy|crowdsec|adguard'
```

**Same project name (`-p stacks`) as the monitoring stack.** That puts all
containers on one Docker network, so Grafana reaches `loki:3100` and Prometheus
reaches `crowdsec:6060` by name. **Never add `--remove-orphans`**: for compose,
the monitoring containers are "orphans" of this file and would be deleted.

Then reload Prometheus (its config already has the `crowdsec` and `adguard` jobs)
and restart Grafana once, so it loads the Loki data source:

```bash
docker kill -s HUP stacks-prometheus-1
docker restart stacks-grafana-1
```

---

## 5 · OPNsense: send the firewall log to LXC 102

In the OPNsense web UI:

1. **System → Settings → Logging**, tab **Remote** (direct link:
   `http://<opnsense>/ui/syslog`). If you only see *Log Files* under System, that
   is the viewer; *Settings* is a few lines above it.
2. Click **+** and fill in:

   | Field | Value |
   |---|---|
   | Enabled | ✅ |
   | Transport | **UDP(4)** |
   | Applications | **filter (filterlog)** only, to keep it small |
   | Levels | empty (= all) |
   | Facilities | empty |
   | Hostname | `192.168.178.87` (LXC 102) |
   | Port | `1514` |
   | RFC5424 | ✅ (the format Alloy expects) |
   | Description | `LXC102 security logs` |

3. **Save**, then **Apply**.

That is all. **Do not tick "Log" on the WAN pass rules for the game forwards.**
OPNsense already logs each internet game connection where it leaves towards the
DMZ (interface `vtnet1`, direction out). Logging WAN too counts everything twice.
Why it shows up there: [docs/23](../docs/23-logs-and-security-monitoring.md#2--the-opnsense-firewall-log).

Before LXC 102 listens on 1514, OPNsense's packets are simply dropped. Harmless.

---

## 6 · Verify

**Logs arrive** (Grafana → *Explore* → data source *Loki (homelab)*):

```logql
{host="lxc102"}                                  # anything from LXC 102
{host="lxc102", unit="ssh.service"}              # SSH lines (log in once to make one)
{job="opnsense"}                                 # firewall lines
{job="opnsense"} | country != ""                 # firewall lines with a location
```

Open one firewall line's details: it must show `src_ip`, `dst_ip`, `dst_port`,
`country`, `city`. No `country` on internet addresses = the GeoIP file is
missing or in the wrong folder (`docker logs stacks-alloy-1`).

**CrowdSec reads** (on LXC 102):

```bash
docker exec stacks-crowdsec-1 cscli metrics show acquisition parsers
docker exec stacks-crowdsec-1 cscli alerts list
```

The acquisition table must show `loki:http://loki:3100` with lines read. "Lines
unparsed" is normal (not every SSH line is a login). No alerts is the good case.

**Prometheus** → *Status → Targets*: `crowdsec` and `adguard` **UP**.

**Grafana** → *Homelab · Security*: numbers on top, dots on the map once the
first internet connections were logged, "Log pipeline health" (bottom, folded)
green.

---

## 7 · Once a month: refresh the location database

```bash
cd /opt/security/geoip && \
curl -fsSL https://download.db-ip.com/free/dbip-city-lite-$(date +%Y-%m).mmdb.gz \
  | gunzip > dbip-city-lite.mmdb.new && mv dbip-city-lite.mmdb.new dbip-city-lite.mmdb && \
docker restart stacks-alloy-1
```

Forgetting it is not dangerous; locations just slowly get less exact. The
"GeoIP hit rate" stat in *Details · Log pipeline health* drops when it gets old.

---

## If it goes wrong

| Symptom | Cause / fix |
|---|---|
| Loki restarts, "permission denied" on `loki.yml` | the file must be readable by uid 10001: `chmod 644` |
| `{host="lxc102"}` empty | Alloy can't read the journal: check the `/var/log/journal` and `/etc/machine-id` mounts, `docker logs stacks-alloy-1` |
| container logs missing, SSH present | Docker logging driver is not journald (step 1) |
| `{job="opnsense"}` empty | OPNsense remote target not applied, wrong port, RFC5424 not ticked, or the application filter is not `filterlog`. Test: `tcpdump -ni any udp port 1514` on LXC 102 |
| firewall lines but no game connections | games are off, or you are looking at WAN lines; game traffic is `iface="vtnet1", dir="out"` |
| "blocked" full of your own devices | that is house-LAN broadcast noise; filter private sources (the dashboards do) |
| CrowdSec: no Loki source in metrics | `acquis.yaml` not mounted, or Loki was not ready: `docker restart stacks-crowdsec-1` |
| CrowdSec never alerts on the website | Apache logs cloudflared's private IP: do [runbook 22](22-real-visitor-ip-behind-a-tunnel.md) |
| Grafana has no Loki data source | Grafana not restarted after adding `datasources/loki.yml` |

---

## Undo

```bash
cd /opt/security && docker compose -p stacks -f docker-compose.yml rm -s -f loki alloy crowdsec adguard-exporter
docker volume rm stacks_loki-data stacks_alloy-data stacks_crowdsec-config stacks_crowdsec-data   # deletes the logs
```

OPNsense: **System → Settings → Logging → Remote**, delete the destination, Apply.
