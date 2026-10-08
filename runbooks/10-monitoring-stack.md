# Runbook 10 · Prometheus, Grafana and the exporters

**Goal** Metrics from all three nodes, the Pi and every container, stored for 90
days and drawn in Grafana.

**Time** 45 minutes.
**Prerequisites** Docker on LXC 102. root on each node.
**Reverses cleanly?** Yes.

Concepts and PromQL: [`docs/08-monitoring.md`](../docs/08-monitoring.md).

![Node Exporter Full on P1](../assets/screenshots/grafana-node-exporter-p1.png)

*The finished state: dashboard 1860 against P1, seven days of history.*

---

## 1 · Exporters first

Prometheus **pulls**. Nothing works until there is something to pull from.

### On each Proxmox node

Installed on the host with apt, not in a container, because it reports on the
machine and needs the machine's view of `/proc` and `/sys`.

```bash
apt install -y prometheus-node-exporter
systemctl enable --now prometheus-node-exporter
curl -s localhost:9100/metrics | head
```

Repeat on P1, P2 and P3.

### Cluster metrics

`prometheus-pve-exporter` reads the Proxmox API and exposes guest states,
storage usage and cluster health.

It runs as a container next to Prometheus (the `pve-exporter` service in
[`compose/monitoring/docker-compose.example.yml`](../compose/monitoring/docker-compose.example.yml)).
Its port is not published: only Prometheus talks to it, by service name.

It needs an API token. Create one with the **minimum** rights it can work with:

```bash
# on a Proxmox node
pveum user add prometheus@pve
pveum acl modify / --users prometheus@pve --roles PVEAuditor
pveum user token add prometheus@pve exporter --privsep 0
```

`PVEAuditor` is read-only. A monitoring credential that can start and stop
guests is a monitoring credential that can take the lab down.

The token goes in the exporter's own env file with `chmod 600`, never in this
repository:

```bash
# in /opt/monitoring, next to docker-compose.yml
printf 'PVE_USER=prometheus@pve\nPVE_TOKEN_NAME=exporter\nPVE_TOKEN_VALUE=<value>\nPVE_VERIFY_SSL=false\n' > pve-exporter.env
chmod 600 pve-exporter.env
```

---

## 2 · Prometheus and Grafana

```bash
mkdir -p /opt/monitoring && cd /opt/monitoring
cp /path/to/compose/monitoring/docker-compose.example.yml docker-compose.yml
cp /path/to/compose/monitoring/prometheus.yml .
cp /path/to/compose/monitoring/.env.example .env
$EDITOR .env                 # Grafana admin credentials
chmod 600 .env
docker compose config
docker compose up -d
```

Files:
[`compose/monitoring/`](../compose/monitoring/)

---

## 3 · Check every target is up

```
http://192.168.178.87:9090/targets
```

![Prometheus target health](../assets/screenshots/prometheus-targets.png)

*The screenshot is from before P2, P3 and pve-exporter were added. Current state
of this lab: three scrape pools, all UP — Prometheus itself, `node_exporter` on
all three nodes, and pve-exporter asking the Proxmox API once per node. The Pi
and cAdvisor are still not scraped. A page of red targets you have learned to
ignore is worse than a short page of green ones.*

Every target should be **UP**. A target that is DOWN, in order of likelihood:

| Cause | Check |
|---|---|
| the exporter is not installed or not running | `systemctl status prometheus-node-exporter` on that host |
| a firewall or the exporter bound to localhost | `ss -tlnp \| grep 9100` on that host |
| **`localhost` used as a target address** | `localhost` means the Prometheus container, not the host |

That last one is the classic. `localhost:9100` in `prometheus.yml` points
Prometheus at itself.

Reload the configuration without restarting:

```bash
curl -X POST http://localhost:9090/-/reload
```

which works because the compose file passes `--web.enable-lifecycle`.

---

## 4 · Grafana

```
http://192.168.178.87:3000
```

Log in with the credentials from `.env`.

**Provision the data source in a file, not by clicking.** A Grafana whose
configuration exists only in its own volume is a Grafana you reconfigure by hand
after every rebuild.

```yaml
# /opt/monitoring/provisioning/datasources/prometheus.yml
apiVersion: 1
datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
```

Note the URL: the **service name** on the compose network. Not an IP, and not
`localhost`.

```bash
docker compose restart grafana
```

### Dashboards

Provisioned from files too. A dashboard provider loads every JSON file in
`/var/lib/grafana/dashboards` into a "Homelab" folder:

```yaml
# /opt/monitoring/provisioning/dashboards/homelab.yml
apiVersion: 1
providers:
  - name: homelab
    folder: Homelab
    type: file
    disableDeletion: true
    allowUiUpdates: false
    options:
      path: /var/lib/grafana/dashboards
```

Download each dashboard's JSON from grafana.com, replace its `${DS_PROMETHEUS}`
input with the data source's `uid`, and drop it in `dashboards/`. This lab
provisions 1860 and 10347. For a one-off, **Dashboards → New → Import** by ID
works too:

| ID | Dashboard | Needs |
|---|---|---|
| **1860** | Node Exporter Full | node_exporter |
| **193** | Docker monitoring | cAdvisor |
| **10347** | Proxmox | pve-exporter |

Start with 1860. It is overwhelming, and reading through it is a good way to
learn what node_exporter actually exposes.

---

## 5 · Verify with real queries

In **Explore**, run each of these. If one returns nothing, that exporter is not
being scraped.

```promql
up
100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)
100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)
100 * (1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})
container_memory_usage_bytes{name!=""}
```

`up` first. It lists every target with a 1 or a 0 and immediately shows what is
missing.

---

## 6 · Put it behind the proxy

Per [Runbook 04](04-nginx-proxy-manager-vhost.md):
`grafana.theminddev.com` → `192.168.178.87:3000`, scheme `http`, WebSockets on
(Grafana Live uses them).

Set `GF_SERVER_ROOT_URL` in `.env` to the external URL. Grafana builds absolute
URLs from it, and getting it wrong sends login redirects to the wrong host.

---

## 7 · What is deliberately not done here

**Alerting.** Prometheus collects, Grafana draws, and **nothing tells you when
something breaks**. Alertmanager is not deployed. This is the largest gap in the
lab and it is in the README's known limitations rather than quietly omitted.

The rules that would matter, ready to deploy, are in
[`docs/08-monitoring.md`](../docs/08-monitoring.md#the-gap-nothing-alerts).

---

## If it goes wrong

| Symptom | Cause |
|---|---|
| target DOWN | exporter not running, or `localhost` used as the address |
| Grafana shows "no data" | wrong data source URL — use `http://prometheus:9090` |
| Prometheus memory grows without bound | cardinality: a label with unbounded values |
| gaps in graphs | scrapes timing out — raise `scrape_timeout` |
| cAdvisor shows no disk stats | expected inside an unprivileged LXC |
| data lost on restart | no named volume for `/prometheus` |
