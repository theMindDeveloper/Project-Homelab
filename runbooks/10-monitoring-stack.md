# Runbook 10 · Prometheus, Grafana and the exporters

**Goal** Numbers from all three Proxmox nodes, the Raspberry Pi, the NAS and the
Proxmox API in Prometheus, drawn on generated Grafana dashboards.

**Time** 60-90 minutes the first time.
**Prerequisites** Docker on LXC 102 ([runbook 02](02-portainer-on-a-new-lxc.md)).
A shell as root on each Proxmox node (web UI → node → *Shell*). SSH to the Pi.
The NAS's web UI. A copy of this repository on LXC 102 (`git clone`).
**Reverses cleanly?** Yes. Everything here only *reads*; nothing it installs can
change a guest, a disk or a setting. See *Undo*.

Concepts: [docs/08](../docs/08-monitoring.md). Next steps after this one:
logs ([21](21-logs-and-crowdsec.md)), alerts ([23](23-alerts-to-telegram.md)),
router ([24](24-fritzbox-monitoring.md)), game servers ([25](25-game-server-monitoring.md)).

---

## 0 · The plan, in one picture

```
 pve  pve2  pve3        Pi            NAS           Proxmox API
  |     |     |          |             |                 |
 node_exporter (apt)   node_exporter (container)    pve-exporter (container on LXC 102)
  \_____\_____\__________/_____________/_________________/
                         |
            Prometheus on LXC 102 asks each one every 15 s  ("scrape")
                         |
                Grafana on LXC 102 draws it
```

Every exporter **only answers questions**. Prometheus is the one that asks.

---

## 1 · node_exporter on each Proxmox node

node_exporter reports CPU, RAM, disks, network and temperatures of the machine
it runs on. On the Proxmox nodes it is installed **on the host** with apt, not in
a container, because it needs the host's own view of `/proc` and `/sys`.

On **pve**, then **pve2**, then **pve3** (web UI → node → *Shell*):

```bash
apt install -y prometheus-node-exporter
systemctl enable --now prometheus-node-exporter
curl -s localhost:9100/metrics | grep ^node_uname_info
```

The last line must print one line starting with `node_uname_info{...}`. If it
prints nothing, `systemctl status prometheus-node-exporter` says why.

Nothing else on the node changes. The package is from Debian's own repository.

---

## 2 · node_exporter on the Raspberry Pi

On the Pi it runs as a small container, read-only, 64 MB cap.

```bash
# on the Pi
sudo mkdir -p /root/docker/node-exporter
sudo cp compose/node-exporter/docker-compose.example.yml /root/docker/node-exporter/docker-compose.yml
cd /root/docker/node-exporter && sudo docker compose up -d
curl -s localhost:9100/metrics | grep -c ^node_
```

The file is [`compose/node-exporter/docker-compose.example.yml`](../compose/node-exporter/docker-compose.example.yml).
`network_mode: host` and `pid: host` let it see the Pi's real network and
processes; `/:/host:ro,rslave` gives it the Pi's file systems **read-only**.

**Do not put a `$` in a compose file** unless you mean a variable. A regex like
`($|/)` in the command makes `docker compose` (and UGOS) reject the whole file.
The default settings already exclude the right mount points.

---

## 3 · node_exporter on the NAS (UGOS)

UGOS has a Docker app, but its compose import **refuses** files that mount the
host's root folder ("Invalid configuration file", nothing more). So the
container is made in the UGOS **Docker → Image** screens instead:

1. **Docker → Image → search** `prom/node-exporter` → **Download** → in
   *Version Number* type `v1.12.1` (not a `master...` tag, those are
   development builds) → **Confirm**.
2. On the image: **Create container**.
3. **Basic information**
   - Container name: `node-exporter`
   - Memory limit: *Custom* → `64` MB
   - **Auto restart: ON** (otherwise it stays off after a NAS reboot)
4. **Volume**: one row **per disk volume**, so the exporter can see how full
   each one is. UGOS only offers shared folders, which is fine:
   - pick an (empty) shared folder **on volume 1**, container path
     `/disks/volume1`, **Read-only**
   - pick a folder **on volume 2** (or 3, ...), container path
     `/disks/volume2`, **Read-only**
   - and so on. The exporter never reads the folders' content; it only asks
     the volume underneath how big and how full it is.
5. **Network**: **bridge** with port mapping NAS `9100` → container `9100` (TCP),
   or **host**. Host mode makes the network graphs show the NAS's real traffic;
   in bridge mode they show only the exporter's own.
6. **Others → Container run command**: leave empty. **Privileged mode**: off.
7. **Confirm**, then check from any machine:

```bash
curl -s http://192.168.178.79:9100/metrics | grep -E '^node_filesystem_size_bytes.*disks'
```

One line per `/disks/...` folder means it worked. If the port is closed, check
the container is *Running* and the NAS firewall (*Control Panel → Security →
Firewall*) allows TCP 9100 from the LAN.

What you get on the NAS: CPU, RAM, CPU temperature, disk activity per HDD and
fill level per volume. HDD temperatures are not exposed this way; UGOS's own
storage page still shows them.

---

## 4 · A read-only Proxmox user for pve-exporter

pve-exporter asks the Proxmox **API** and reports every node, VM, LXC and storage
(states, CPU, RAM, disk, backups, "start at boot"). It needs an API token. Give it
the smallest role that works, **PVEAuditor** (read-only): a monitoring
credential that can stop guests is a monitoring credential that can take the lab
down.

On **one** Proxmox node (the cluster shares users):

```bash
pveum user add prometheus@pve --comment "pve-exporter, read-only"
pveum acl modify / --users prometheus@pve --roles PVEAuditor
pveum user token add prometheus@pve exporter --privsep 0
```

The last command prints a table with a `value`. **That value is shown once.**
Copy it now. `--privsep 0` means the token has exactly the user's rights, which
are read-only.

Check that it really is read-only (from LXC 102, replace `<value>`):

```bash
curl -sk -H "Authorization: PVEAPIToken=prometheus@pve!exporter=<value>" \
  https://192.168.178.20:8006/api2/json/access/permissions | grep -o '"[A-Za-z.]*Audit[A-Za-z.]*":1' | sort -u
```

Only `...Audit` permissions may appear.

---

## 5 · Prometheus, Grafana and pve-exporter on LXC 102

```bash
# on LXC 102, as root
mkdir -p /opt/monitoring && cd /opt/monitoring
cp -r /path/to/repo/compose/monitoring/. .
mv docker-compose.example.yml docker-compose.yml

# secrets: one env file each, never in Git
cp .env.example .env                       && $EDITOR .env                 # Grafana admin
cp pve-exporter.env.example pve-exporter.env && $EDITOR pve-exporter.env   # token from step 4
cp alerting.env.example alerting.env       # fill in later, runbook 23
cp fritz.env.example fritz.env             # fill in later, runbook 24
cp game-exporter.env.example game-exporter.env   # fill in later, runbook 25
chmod 600 *.env
```

The compose file has five services; the router and game exporters come later.
For now start only what this runbook needs:

```bash
docker compose -p stacks config -q && echo OK      # catches typos and stray $
docker compose -p stacks up -d prometheus grafana pve-exporter
```

`-p stacks` is the project name. The log stack ([runbook 21](21-logs-and-crowdsec.md))
uses the same name so all containers share one network. **Never run
`docker compose ... --remove-orphans`** on this project: it deletes the
containers that belong to the *other* compose file.

Look at [`prometheus/prometheus.yml`](../compose/monitoring/prometheus/prometheus.yml):
every job is commented. Jobs for things you have not set up yet
(`fritzbox`, `games`, `crowdsec`, `adguard`) will show DOWN until you do; remove
them if you never will.

---

## 6 · Check every target is UP

```
http://192.168.178.87:9090/targets
```

Every line should say **UP**. A target that is DOWN, in order of likelihood:

| Cause | Check |
|---|---|
| the exporter is not installed or not running | `systemctl status prometheus-node-exporter` on that host |
| a firewall, or the exporter listening on localhost only | `ss -tlnp \| grep 9100` on that host |
| **`localhost` used as a target address** | `localhost` means the Prometheus container, not the host |
| the job is for something not set up yet | expected, see step 5 |

After any edit of `prometheus.yml`, reload without restarting:

```bash
docker kill -s HUP stacks-prometheus-1
```

Then in Prometheus → *Graph*, run `up`: one line per target, 1 or 0.

---

## 7 · Grafana

```
http://192.168.178.87:3000
```

Log in with the user from `.env`. Change the password if asked.

There is nothing to click: the data sources (Prometheus, Loki) and the dashboard
folder come from `grafana/provisioning/`. What is missing is the dashboards
themselves, which are generated:

```bash
# on any machine with Python 3 and this repository
$EDITOR scripts/grafana/queries.py     # GAME_PORTS: your game ports (or leave the examples)
python3 scripts/grafana/gen_all.py     # writes 4 JSON files into compose/monitoring/grafana/dashboards/
# copy them to /opt/monitoring/grafana/dashboards/ on LXC 102
```

Grafana picks them up within about 10 seconds. *Dashboards → Homelab* then has
Overview, Hosts, Games and Security. Panels for parts you have not set up yet
(logs, router, games) stay empty until you do.

Why generated, and how to change them: [docs/25](../docs/25-dashboards-as-code.md).

---

## 8 · Verify with real queries

In Grafana → *Explore* → Prometheus, run each. Nothing returned = that exporter
is not being scraped.

```promql
up
1 - avg by (node) (rate(node_cpu_seconds_total{mode="idle"}[5m]))
1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes
count(pve_up)              # number of nodes + guests + storages Proxmox knows
max by (node) (node_thermal_zone_temp)
```

On the **Overview** dashboard every node tile should be green and every bar
filled.

---

## 9 · Put it behind the proxy

Per [Runbook 04](04-nginx-proxy-manager-vhost.md): `grafana.example.com` →
`192.168.178.87:3000`, scheme `http`, WebSockets on (Grafana Live uses them).

Set `GF_SERVER_ROOT_URL` in the compose file to that address. Grafana builds
absolute URLs from it, including the "Open Grafana" link in every alert.

---

## If it goes wrong

| Symptom | Cause |
|---|---|
| target DOWN | exporter not running, firewall, or `localhost` used as the address |
| Grafana shows "no data" | wrong data source URL: use `http://prometheus:9090`, the service name |
| every Proxmox gauge appears three times | cluster data asked from every node; ask one (`pve` job) as in the example |
| NAS: "Invalid configuration file" | UGOS rejects root mounts in compose; use the Image → Create container screens (step 3) |
| NAS: port 9100 closed but container running | bridge mode without port mapping, or the NAS firewall |
| `docker compose` complains about a variable | a `$` in the file; write `$$` or remove it |
| Prometheus memory grows without bound | cardinality: a label with unbounded values |
| gaps in graphs | scrapes timing out, raise `scrape_timeout` for that job |
| data lost on restart | no named volume for `/prometheus` |

---

## Undo

```bash
# LXC 102
cd /opt/monitoring && docker compose -p stacks rm -s -f prometheus grafana pve-exporter
# each Proxmox node
apt remove prometheus-node-exporter
pveum user delete prometheus@pve
# Pi
cd /root/docker/node-exporter && docker compose down
# NAS: delete the node-exporter container in the UGOS Docker app
```
