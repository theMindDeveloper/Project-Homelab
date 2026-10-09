<div align="center">

# theminddev-homelab

**A three-node Proxmox VE cluster, a Raspberry Pi ingress layer and a NAS —
documented so the whole thing can be rebuilt from this repository alone.**

<img src="assets/photos/rack-front-v2.2.jpg" alt="The rack: TP-Link Omada ES210X-M2 switch, Raspberry Pi 5, and three Lenovo ThinkCentre M710q nodes" width="380">

![Proxmox VE](https://img.shields.io/badge/Proxmox_VE-E57000?style=flat-square&logo=proxmox&logoColor=white)
![Debian](https://img.shields.io/badge/Debian_12-A81D33?style=flat-square&logo=debian&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat-square&logo=docker&logoColor=white)
![LXC](https://img.shields.io/badge/LXC-333333?style=flat-square&logo=linuxcontainers&logoColor=white)
![Cloudflare](https://img.shields.io/badge/Cloudflare_Tunnel-F38020?style=flat-square&logo=cloudflare&logoColor=white)
![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?style=flat-square&logo=prometheus&logoColor=white)
![Grafana](https://img.shields.io/badge/Grafana-F46800?style=flat-square&logo=grafana&logoColor=white)
![Loki](https://img.shields.io/badge/Grafana_Loki-F46800?style=flat-square&logo=grafana&logoColor=white)
![CrowdSec](https://img.shields.io/badge/CrowdSec-1E1E3F?style=flat-square)
![Telegram](https://img.shields.io/badge/Alerts-Telegram-26A5E4?style=flat-square&logo=telegram&logoColor=white)
![Nginx](https://img.shields.io/badge/Nginx_Proxy_Manager-009639?style=flat-square&logo=nginx&logoColor=white)

**3 nodes · 12 CPU cores · 64 GB RAM · 6 LXC guests + 1 VM · 2 networks · 16 proxied hostnames · 33 W**

[Architecture](#architecture) · [Hardware](#the-hardware) ·
[Services](#services) · [Monitoring](#monitoring) · [AI agent](#operations-an-ai-agent-with-least-privilege) · [Wiki](docs/) · [Runbooks](runbooks/) ·
[Limitations](#known-limitations)

</div>

---

## What this repository contains

Complete operational documentation for the infrastructure described below.
The design goal is that the lab could be rebuilt from this repository alone.

| | Contents |
|---|---|
| **[`docs/`](docs/)** | A 26-page technical reference: Docker, Docker Compose, LXC versus VM, Proxmox, storage and thin provisioning, networking, DNS and TLS, backup and recovery, Linux administration, troubleshooting, hardening, a nine-page sequence on network segmentation, bridges, NAT, firewalls, OPNsense and FreeBSD, a four-page sequence on monitoring, security logs, alerting and dashboards as code, and the architecture of the AI agent that operates the lab. |
| **[`docs/reports/`](docs/reports/)** | Dated write-ups of changes large enough to have a story, including what broke. |
| **[`runbooks/`](runbooks/)** | 25 step-by-step procedures, each with prerequisites, verification and rollback: creating containers, deploying services, cluster operations, building and sealing the DMZ, monitoring every machine, collecting logs, alerting to Telegram, giving an AI agent least-privilege access, backup restore drills and full disaster recovery. |
| **[`compose/`](compose/)** | 14 Docker Compose stacks covering every containerised service, published as templates with credentials externalised, including the full monitoring, logging and alerting configuration. |
| **[`scripts/`](scripts/)** | Operational tooling: container provisioning, Docker installation, backup automation, health checking, a secret scanner that runs pre-commit and in CI, and the generators and checker for the Grafana dashboards and alert rules. |
| **[`diagrams/`](diagrams/)** | The full architecture diagram, with editable draw.io source. |
| **[`inventory/`](inventory/inventory.yml)** | A machine-readable inventory of every host, guest, service and address — the single source of truth from which the tables in this README are derived. |

---

## Architecture

![Architecture diagram](diagrams/homelab-4.png)

*Editable source: [`diagrams/homelab.drawio`](diagrams/homelab.drawio)*

The lab is built in five layers, each with a defined responsibility.

### 1 · Compute — a three-node Proxmox VE cluster

Three ThinkCentre M710q nodes form `HomelabCluster`: 12 cores and 64 GB of RAM
under a single management plane, with corosync providing three votes and a
quorum of two. One node can fail or be taken down for maintenance without the
cluster losing its configuration filesystem.

Every workload runs in an **unprivileged LXC container** rather than a virtual
machine, with exactly one deliberate exception: the firewall, which is FreeBSD
and therefore cannot be a container on a Linux host. Containers share the host
kernel, which gives sub-second start times and memory consumption proportional
to actual use instead of allocation. The
cost is that they cannot be live-migrated, and that trade-off is documented
rather than omitted.

Docker runs *inside* those containers, giving two distinct layers: the LXC
container is the machine, with an address and a lifetime measured in years; the
Docker containers inside it are the applications, replaced whenever a new image
is published.

### 2 · Ingress — a single point of entry

A Raspberry Pi 5 runs Nginx Proxy Manager, which terminates TLS for all 16
internal hostnames using one Let's Encrypt wildcard certificate and routes each
request to the correct backend by `Host` header. Every service is therefore
reachable by name and over HTTPS, without any service needing to implement TLS
itself.

Certificates are issued over the **DNS-01 challenge**, which proves domain
ownership through a DNS record rather than an HTTP request. As a result, no
inbound port is open for issuance or renewal.

### 3 · Storage — a NAS beside the data

A UGREEN DH4300 Plus holds media, photographs and backup archives across two
volumes: a 1 TB Basic/Btrfs disk kept separate and detachable, and a 2 × 6 TB
RAID 1/EXT4 array (~6 TB usable). Jellyfin and Syncthing run on the
NAS rather than in the cluster, placing the applications next to the data they
serve and removing both a network share and a hardware-passthrough problem.

### 4 · Isolation — a software DMZ for anything internet-facing

Everything reachable from the internet lives in `10.10.10.0/24`, a Proxmox
bridge created with `bridge-ports none`: a switch with **no physical uplink**.
An OPNsense VM straddles that bridge and the house network and is the only route
between them. A block rule refuses every packet from the segment aimed at
`192.168.178.0/24`.

The design has two halves and needs both. **Separation**, so the exposed machine
has no road to the trusted network, and **a chokepoint**, so the one road it
does have is watched. Two earlier attempts to solve this with firewall rules on
a flat network failed, because rules cannot substitute for a missing path.

OPNsense is not *in* the path of anything else. It hangs off the switch rather
than sitting in line, so the PC, the Pi, the NAS and all three Proxmox nodes
route exactly as they did before, and the migration caused no downtime outside
the game stack.

![OPNsense firewall rules: the block rule above the two default allows](assets/screenshots/opnsense-lan-rules.png)

*The whole thing in one screen. The floating rule lets the house reach the
segment; on the LAN interface the block rule sits above the default allows,
which is the only reason it does anything.*

Reasoning: [`docs/12-network-segmentation.md`](docs/12-network-segmentation.md).
Procedures: [runbooks 12 to 18](runbooks/). The full story, including everything
that broke:
[`docs/reports/2026-08-13-dmz-migration.md`](docs/reports/2026-08-13-dmz-migration.md).

### 5 · External services

Cloudflare provides authoritative DNS for the domain and the tunnel through
which exactly one service is published to the internet. AdGuard Home, also on
the Raspberry Pi, is the resolver for every device on the network.

Since September 2026 AdGuard forwards to **Quad9 over DoH and DoT**, so the ISP
sees that the house uses Quad9 but not which names it looks up. On the NAS,
qBittorrent runs inside a **gluetun** container and can only reach the internet
through a Mullvad WireGuard tunnel: if the tunnel is down, it has no network at
all. What that does and does not protect:
[`docs/reports/2026-09-11-privacy-update.md`](docs/reports/2026-09-11-privacy-update.md).

---

### The security property this produces

Internal hostnames resolve **publicly** to an RFC1918 address. Anyone on the
internet can look up `grafana.theminddev.com` and receive `192.168.178.178` —
an address that is not routable across the internet. The name resolves
worldwide and the service is reachable only from the LAN.

Exactly one hostname is published externally, through a Cloudflare tunnel in
which the connector establishes an **outbound** connection and receives requests
over it. There is no inbound firewall rule for it, and no port forward.

The game servers are the honest exception: they use conventional port forwards,
because players come from the internet and always will. **What changed in August
2026 is where those forwards land.** They used to point at a container that was
a peer of the NAS, the password vault and the Proxmox API. They now point at a
firewall, which forwards them into a network segment with no route back.

Verified rather than asserted: an `nmap` sweep of the house from inside the
segment finds nothing, and every reachability probe returns a timeout.

![OPNsense live log showing blocked traffic from the DMZ](assets/screenshots/opnsense-blocked-live-log.png)

*A game container reaching for AdGuard, the NAS and the Proxmox API. Every row
is `block`.*

Full request paths, the proxy headers that commonly break applications, and the
diagnostic procedure are in
[`docs/05-networking-dns-tls.md`](docs/05-networking-dns-tls.md).

---

## The hardware

| | Role | Address | Specification |
|---|---|---|---|
| **P1** `pve` | Proxmox node — general workload | `192.168.178.20:8006` | ThinkCentre M710q · i5-7500T (4C) · 16 GB · 94 GB ext4 |
| **P2** `pve2` | Proxmox node — the whole game stack and the firewall | `192.168.178.77:8006` | M710q · i5-7400T (4C) · 32 GB · 238 GB NVMe · plus `hdd-1tb` |
| **P3** `pve3` | Proxmox node | `192.168.178.50:8006` | M710q · i5-7500T (4C) · 16 GB · no guests, quorum vote |
| **Firewall** | The only door into the game segment | `192.168.178.60` | OPNsense VM 200 on P2 · 2 GB · 2 cores · 20 GB UFS |
| **Pi** | Ingress and LAN DNS | `192.168.178.178` | Raspberry Pi 5 · 8 GB · DietPi · Docker |
| **NAS** | Storage, media, backup target | `192.168.178.49` | UGREEN DH4300 Plus · UGOS Pro · 1 TB Btrfs + 2 × 6 TB RAID 1/EXT4 |
| **Router** | Gateway, DHCP, DynDNS | `192.168.178.1` | FRITZ!Box 7590 |
| **Switch** | | | TP-Link TL-SG108 v3 · 8-port gigabit · unmanaged |

**Two networks.** The house is a flat `192.168.178.0/24` with no VLANs and
static addressing throughout, and AdGuard Home resolves for every device on it.
The game segment is `10.10.10.0/24` on `vmbr1`, a bridge with no physical
uplink, and it resolves against a public resolver because AdGuard sits on the
other side of the block rule.

| | House LAN | Game segment |
|---|---|---|
| Subnet | `192.168.178.0/24` | `10.10.10.0/24` |
| Bridge | `vmbr0`, real NIC attached | `vmbr1`, `bridge-ports none` |
| Gateway | FRITZ!Box `.1` | OPNsense `10.10.10.1` |
| DNS | AdGuard `.178` | `1.1.1.1` |
| Reaches the other side? | **yes**, stateful, admin only | **no** |

### The cluster

<img src="assets/screenshots/proxmox-cluster-tree-dmz.png" alt="Proxmox cluster tree: HomelabCluster with pve, pve2 and pve3, the game stack and VM 200 opnsense on pve2" width="330" align="right">

`HomelabCluster`, three corosync votes, two needed for quorum. One node can fail
or be taken down for maintenance without the cluster losing `/etc/pve`.

Every guest is an unprivileged LXC container except VM 200, the OPNsense
firewall. That exception is not a compromise: OPNsense is FreeBSD, a container
shares the host's Linux kernel, and a firewall guarding against a compromised
guest should not borrow the kernel it is protecting. The selection criteria are
in [`docs/04-lxc-vs-vm.md`](docs/04-lxc-vs-vm.md).

<br clear="right">

---

## Services

<img src="assets/screenshots/glance-dashboard.png" alt="Glance dashboard showing health checks for every service, the three cluster nodes, and service addresses">

*The dashboard at [`compose/glance/glance.example.yml`](compose/glance/glance.example.yml).
It answers one question — is anything red — which is why it gets looked at
*

### Ingress

![Nginx Proxy Manager proxy host list: 16 hostnames, all Let's Encrypt, all online](assets/screenshots/npm-proxy-hosts.png)

*Sixteen hostnames, every one on a Let's Encrypt certificate, every one online.
The destinations are all RFC1918 addresses. Nothing in this list is reachable
from the internet — the certificates were issued over the DNS-01 challenge, so
not one of them required an open inbound port.*

<img src="assets/screenshots/tls-padlock-internal-service.png" alt="Browser address bar showing a padlock on glance.theminddev.com" align="right">

That padlock is on a service that lives entirely inside the LAN, on a name that
resolves publicly to an address nobody outside can route to. It is the whole
DNS-01 argument in one screenshot.

<br clear="right">

### Raspberry Pi 5 · DietPi · Docker

![Portainer on the Raspberry Pi: adguard, npm, portainer](assets/screenshots/portainer-pi-containers.png)

| Service | Port | Hostname | Role |
|---|---:|---|---|
| Nginx Proxy Manager | 81 admin, 80/443 | `npm.` | reverse proxy, TLS termination, Let's Encrypt DNS-01 |
| AdGuard Home | 53 DNS, 8000 UI | `adguard.` | DNS resolver and filter for the whole LAN |
| Portainer 0 | 9442 | `port0.` | container management |

### P1 `pve` · LXC 102 `docker` · `192.168.178.87`

Unprivileged container with `nesting=1`. The Docker host that carries most of
the lab.

![Portainer showing the containers in LXC 102](assets/screenshots/portainer-lxc102-containers.png)

| Service | Port | Hostname | Exposure |
|---|---:|---|---|
| Glance | 8080 | `glance.` | LAN |
| Vaultwarden | 8081 | `vault.` | LAN |
| Portainer 1 | 9443 | `port1.` | LAN |
| Grafana | 3000 | `grafana.` | LAN |
| Prometheus | 9090 | `prom.` | LAN |
| Loki, Alloy, CrowdSec | 1514/udp (firewall log in) | — | LAN / Docker network |
| pve-, fritz-, game-, adguard-exporter | — | — | Docker network only |
| n8n | — | — | LAN |
| pure-ftpd | — | — | LAN |
| Apache | 80 | `apache.` | **internet, via tunnel** |
| cloudflared | — | — | outbound only |


### DNS

![AdGuard Home dashboard: 123,095 queries in 24 hours, 38,598 blocked](assets/screenshots/adguard-dashboard.png)

*123,095 DNS queries in 24 hours, **38,598 blocked (31.4%)**, 15 ms average
processing time. Every device on the network resolves through this instance,
which delivers network-wide filtering with no client-side configuration —
including for devices that cannot run filtering software themselves.*

*The same figure describes the primary single point of failure: all 123,095
queries were served by one container on one Raspberry Pi.*

Upstream is Quad9, encrypted (DoH and DoT), with a conditional upstream that
sends `*.fritz.box` to the router. Setup in
[runbook 03](runbooks/03-adguard-home-dns.md#upstream-resolvers), background in
[`docs/21-encrypted-dns.md`](docs/21-encrypted-dns.md).

### P2 `pve2` · game hosting, inside the DMZ

Since August 2026 the entire game stack lives in `10.10.10.0/24`, behind
OPNsense, with no route to the house network.

| Guest | IP | Port | |
|---|---|---:|---|
| VM 200 `opnsense` | `10.10.10.1` / `192.168.178.60` | 80 | the firewall, one leg in each network |
| LXC 106 `panel` | `10.10.10.22` | 80 | Pterodactyl panel |
| LXC 105 `wings` | `10.10.10.20` | 9090 | Pterodactyl daemon — runs each server as its own container |
| LXC 107 `amp-server` | `10.10.10.21` | 8080 | CubeCoders AMP |

The panel was moved **into** the segment rather than allowed through it, so no
game-hosting service has any route into the house at all. LXC 101 `casaos`
(`.59`) stays on the house network; it is not internet-facing.

<img src="assets/screenshots/pterodactyl-servers.png" alt="Pterodactyl panel showing the zomboid and minecraft servers">

<img src="assets/screenshots/amp-game-instances.png" alt="AMP instances: Terraria offline, Space Engineers running">

*Two managers, four servers: Project Zomboid and Minecraft under Pterodactyl,
Terraria and Space Engineers under AMP. Pterodactyl runs each server as its own
Docker container, so a compromise of one is contained to that container.*

*Both screenshots predate the migration and show the old `192.168.178.x`
addresses. They are kept as they are; a dated screenshot of a past state is not
a leak.*

**Port numbers are redacted in both screenshots.** These are the only services
behind a WAN port forward, and the publication policy in
[`docs/99-security-notes.md`](docs/99-security-notes.md) excludes any
information about which ports are externally reachable.

### NAS · UGOS Pro · Docker

| Service | Purpose |
|---|---|
| Jellyfin (`jelly.`) | media server — runs next to the library at `192.168.178.49`, so no network share and no passthrough problem |
| UGOS Photos | photo library, the NAS's built-in app |
| Syncthing | file sync between devices |
| qBittorrent + gluetun | torrents, **only** through Mullvad. qBittorrent lives in gluetun's network namespace, web UI on `:8085` is published on gluetun. [compose](compose/torrent-vpn/docker-compose.example.yml) · [runbook 20](runbooks/20-qbittorrent-behind-gluetun.md) |

All hostnames are under `theminddev.com`. The machine-readable version of every
table on this page is [`inventory/inventory.yml`](inventory/inventory.yml).

---

## Monitoring

Every machine, the internet line and the game servers are watched; the firewall
and the website are logged with the visitor's location; and the lab **tells me
when something breaks**, on Telegram. Built in October 2026; the story,
including the sixteen things that broke on the way, is in
[the October report](docs/reports/2026-10-08-monitoring-security-alerting.md).

```mermaid
flowchart LR
    A["node_exporter<br/>3 nodes · Pi · NAS"] --> P[("Prometheus")]
    B["Proxmox API · FRITZ!Box<br/>game panels · AdGuard"] -- "exporters" --> P
    C["firewall log · SSH ·<br/>containers · website"] -- "Alloy + GeoIP" --> L[("Loki")]
    L --> CS["CrowdSec<br/>watch only"] --> P
    P --> G["Grafana<br/>4 dashboards · 19 alert rules"]
    L --> G
    G -- "alerts" --> T["Telegram"]
```

| What | How |
|---|---|
| **Machines** | node_exporter on all three nodes, the Pi and the NAS: CPU, RAM, disks, network, every temperature sensor |
| **Cluster** | pve-exporter with a read-only (`PVEAuditor`) token: every node, VM, LXC and storage, backup status |
| **Internet line** | the FRITZ!Box over TR-064, with a router user that has one right: link, DSL speed and quality, new devices, remote access, firmware |
| **Game servers** | a 158-line read-only exporter for AMP and Pterodactyl: state, players, load, uptime |
| **Logs** | Loki + Alloy: SSH, every container, the OPNsense firewall log and the website (with the real visitor IP behind the tunnel), each with country and city |
| **Attacks** | CrowdSec reads those logs and recognises brute force, scans and web exploits, **watch only**: nothing is blocked |
| **Dashboards** | four, generated by a Python script: Overview, Hosts (a switch per machine), Games, Security (dark world map) |
| **Alerts** | 19 rules to my own Telegram bot: 🔴 any time, 🟠 not at night, 🎮 when a game server stops. Switched-off nodes are not an incident |

Prometheus **pulls**: it reaches out to each target on an interval, so adding a
host means editing `prometheus.yml` and installing an exporter, and never
configuring the new host to know about Prometheus. Everything Grafana knows
(data sources, dashboards, alert rules, Telegram, quiet hours) comes from files,
so a rebuilt Grafana needs no clicking.

| Read | for |
|---|---|
| [docs/08 · Monitoring](docs/08-monitoring.md) | the stack, Prometheus, PromQL, what is and is not monitored |
| [docs/23 · Logs and security monitoring](docs/23-logs-and-security-monitoring.md) | Loki, Alloy, the firewall log, GeoIP, CrowdSec |
| [docs/24 · Alerting](docs/24-alerting.md) | the rules, routing, quiet hours, and seven ways an alert can lie |
| [docs/25 · Dashboards as code](docs/25-dashboards-as-code.md) | why generated, and the Grafana traps |
| [runbooks 10, 21-26](runbooks/) | how to build all of it, step by step |

![Grafana Node Exporter Full dashboard for P1, seven days of history](assets/screenshots/grafana-node-exporter-p1.png)

*Where it started: the community dashboard 1860 on P1 (25.6% CPU, 27.7% of
31 GiB RAM, seven days). The per-interface network panel shows `veth101i0`
through `veth107i0`, one virtual interface per LXC guest, and `docker0`, the
containers inside LXC 102. It has since been replaced by the lab's own
generated dashboards.*

![Grafana hardware temperature panel: nvme and coretemp, seven days](assets/screenshots/grafana-temperatures.png)

*NVMe and per-core package temperatures over a week: mean 39-44 °C, peaks to
64 °C, against an 80 °C line. Three fanless mini PCs stacked in a rack is
exactly the arrangement where you want this graph to exist rather than to
assume, and there is now an alert above 85 °C.*

---

## Operations: an AI agent with least privilege

Most of the editing work in this lab (configs, dashboards, alert rules, checks,
these docs) is done by an **AI agent**, [OpenClaw](https://docs.openclaw.ai) on
VM 103. It **proposes, a human decides**: every change is a pull request with a
written plan, nothing touches a machine before it is merged, and findings are
written down instead of "fixed".

```mermaid
flowchart LR
    H["Owner<br/>Telegram · browser"] <--> A["AI agent<br/>VM 103"]
    A -- "PR + change note" --> G["GitHub<br/>private config repo"]
    H -- "reads diff, merges" --> G
    W["merge-watcher<br/>script, every 2 min"] -- "merged? wake" --> A
    A -- "own SSH user, sudo" --> M["LXC 102 · Pi · 3 DMZ containers"]
    A -- "narrow API role" --> P["Proxmox API"]
    A -- "own accounts" --> APPS["game panels · proxy"]
    A -. "no access" .-> X["node shells · OPNsense · NAS<br/>router admin · Vaultwarden"]
```

| | |
|---|---|
| **Identity** | its own everywhere: user `openclaw` with one SSH key valid only from VM 103; Proxmox role `OpenClaw` (see, power, snapshots; no create/delete/config); own non-admin app accounts |
| **Never** | a Proxmox node shell, OPNsense, the NAS, the router's admin, Vaultwarden, Cloudflare |
| **Workflow** | PR + change note (*what, where, apply, verify, undo, result*) → owner merges → a watcher script wakes the agent → it backs up, applies exactly the note, verifies, reports |
| **Rules** | never change what was not asked; ask before anything big; never merge; never commit, print or ask for secrets in chat; every commit authored by the owner |
| **Cost** | the watcher and the alerts run without the AI; it only wakes for a message or a merge |
| **Weak spots** | written down, not hidden: the agent VM holds every key, `main` is not yet branch-protected, prompt injection through logs |

Full architecture, access table, data flow and incidents:
[docs/26 · The AI agent](docs/26-ai-agent-devops.md). Set it up yourself:
[runbook 27](runbooks/27-ai-agent-with-least-privilege.md).

---

## Power

<div align="center">
<img src="assets/screenshots/power-consumption.jpg" alt="Power draw over seven days, averaging around 33 W" width="290">
<img src="assets/screenshots/power-energy-used.jpg" alt="Energy used: 5.725 kWh this month, 1.71 EUR" width="290">
</div>

Measured at a TP-Link Tapo smart plug: **around 33 W** under normal load,
peaking above 50 W, **5.7 kWh** over the month to date, **€1.71**.

Worth measuring for two reasons. It is the running cost of the lab, which is a
real number a homelab should know rather than guess. And it is a crude health
signal: a machine suddenly drawing 20 W more than usual is doing work nobody
asked for.

---

## Documentation

### The wiki — [`docs/`](docs/)

*Reference material: what each component is, and why it was chosen.*

| | Page | What it answers |
|---|---|---|
| 00 | [Glossary](docs/00-glossary.md) | every term used here, defined once |
| 01 | [Docker](docs/01-docker.md) | what a container actually is, the mental model, every command by intent |
| 02 | [Docker Compose](docs/02-docker-compose.md) | the file format, `up` vs `restart`, healthchecks, `.env` |
| 03 | [Proxmox cheat sheet](docs/03-proxmox-cheatsheet.md) | the commands, grouped by intent, with the traps |
| 04 | [LXC or VM](docs/04-lxc-vs-vm.md) | the decision rule, and what it costs to get it wrong |
| 05 | [Networking, DNS and TLS](docs/05-networking-dns-tls.md) | the request path, DNS-01, proxy headers, diagnostic order |
| 06 | [Storage](docs/06-storage.md) | thin provisioning, UID mapping, why RAID is not a backup |
| 07 | [Backup and recovery](docs/07-backup-and-recovery.md) | `vzdump` modes, restoring, and the drill nobody runs |
| 08 | [Monitoring](docs/08-monitoring.md) | the stack in one picture, Prometheus, the PromQL that gets used, what is monitored |
| 09 | [Linux administration](docs/09-linux-admin.md) | systemd, journald, disks, network, SSH, permissions |
| 10 | [Troubleshooting](docs/10-troubleshooting.md) | organised by **symptom**, because that is what you have |
| 11 | [Hardening](docs/11-hardening.md) | the threat model, what is done, what deliberately is not |
| 21 | [Encrypted DNS](docs/21-encrypted-dns.md) | DoH vs DoT, who encrypts what, and what it still does not hide |
| 22 | [VPNs and kill switches](docs/22-vpns-and-kill-switches.md) | where a VPN can live in this network, and why torrents go through gluetun |
| 23 | [Logs and security monitoring](docs/23-logs-and-security-monitoring.md) | Loki, Alloy, the firewall log, GeoIP, CrowdSec watch-only, no country blocking |
| 24 | [Alerting](docs/24-alerting.md) | Grafana rules to Telegram, quiet hours, and seven ways an alert can lie |
| 25 | [Dashboards as code](docs/25-dashboards-as-code.md) | generated Grafana dashboards, and the Grafana traps |
| 26 | [The AI agent](docs/26-ai-agent-devops.md) | where it runs, what it can and cannot reach, how a change travels, the weak spots |
| 99 | [Security notes](docs/99-security-notes.md) | what this repository publishes, and what it never will |

### The runbooks — [`runbooks/`](runbooks/)

*How to do it, step by step, while tired.*

| | Runbook | Time |
|---|---|---|
| 01 | [Create an LXC container](runbooks/01-create-an-lxc-container.md) | 3 min |
| 02 | [**Docker and Portainer on a new LXC**](runbooks/02-portainer-on-a-new-lxc.md) — the full walkthrough | 20 min |
| 03 | [AdGuard Home as the LAN resolver](runbooks/03-adguard-home-dns.md) | 20 min |
| 04 | [Put a service behind Nginx Proxy Manager](runbooks/04-nginx-proxy-manager-vhost.md) | 3 min |
| 05 | [Glance dashboard](runbooks/05-glance-dashboard.md) | 15 min |
| 06 | [Publish one service with a Cloudflare Tunnel](runbooks/06-cloudflare-tunnel.md) | 15 min |
| 07 | [Nextcloud](runbooks/07-nextcloud.md) — *planned, not yet deployed* | 60 min |
| 08 | [Add a node to the Proxmox cluster](runbooks/08-add-a-node-to-the-cluster.md) | 15 min |
| 09 | [The backup restore drill](runbooks/09-backup-restore-drill.md) — quarterly | 30 min |
| 10 | [Prometheus, Grafana and the exporters](runbooks/10-monitoring-stack.md) | 60-90 min |
| 11 | [Rebuild the lab from zero](runbooks/11-rebuild-from-zero.md) | a weekend |
| 20 | [qBittorrent behind gluetun on the NAS](runbooks/20-qbittorrent-behind-gluetun.md) | 30 min |
| 21 | [Logs: Loki, Alloy, the firewall log and CrowdSec](runbooks/21-logs-and-crowdsec.md) | 45-60 min |
| 22 | [The real visitor IP behind a Cloudflare tunnel](runbooks/22-real-visitor-ip-behind-a-tunnel.md) | 15 min |
| 23 | [Alerts to Telegram](runbooks/23-alerts-to-telegram.md) | 30 min |
| 24 | [FRITZ!Box monitoring](runbooks/24-fritzbox-monitoring.md) | 15 min |
| 25 | [Game server monitoring](runbooks/25-game-server-monitoring.md) | 30 min |
| 26 | [Test dashboard and alert changes safely](runbooks/26-test-grafana-changes-safely.md) | 5-15 min |
| 27 | [An AI agent with least privilege](runbooks/27-ai-agent-with-least-privilege.md) | an evening |

**Start with [Runbook 02](runbooks/02-portainer-on-a-new-lxc.md)** if you read
one thing. It goes from an empty Proxmox node to a service in a browser with a
real certificate, and every other service here is the same six steps with a
different compose file.

---

## Repository layout

```text
inventory/
  inventory.yml              hosts, guests, services, addressing - the source of truth
diagrams/
  homelab.drawio             editable architecture diagram, 2 pages:
                             the lab, and the DMZ in detail
  homelab-2.png              exported for this README
  homelab.png                the previous export, pre-DMZ
docs/                        the wiki: what things are and why
  12-network-segmentation.md   why a flat network cannot be fixed with rules
  13 .. 20                     addressing, bridges, NAT, firewalls, OPNsense, FreeBSD
  21, 22                       encrypted DNS, VPNs and kill switches
  08, 23 .. 25                 monitoring, security logs, alerting, dashboards as code
  26                           the AI agent: access, workflow, weak spots
  reports/                     dated write-ups of large changes, including what broke
runbooks/                    step-by-step procedures
  12 .. 18                     build the DMZ, seal it, and recover it
  10, 21 .. 26                 monitoring, logs, alerts, router, game servers, testing
  27                           give an AI agent least-privilege access
compose/
  <service>/
    docker-compose.example.yml
    .env.example             the real .env is gitignored
  monitoring/                Prometheus, Grafana, exporters; grafana/provisioning holds
                             data sources, dashboard provider and all alerting
  security/                  Loki, Alloy, CrowdSec, adguard-exporter
scripts/
  check-secrets.sh           pre-commit guard against leaking anything private
  new-lxc.sh                 create a container consistently
  install-docker.sh          Docker + Compose plugin, with log rotation
  backup-all.sh              vzdump wrapper with retention
  health-check.sh            is everything in the inventory answering
  grafana/                   dashboard + alert-rule generators, and a checker that
                             runs every query against the live data
assets/
  photos/  screenshots/
```

---

## Planned

Marked with a dashed border in the diagram. None of this is running yet.

| What | Where | Why |
|---|---|---|
| **k3s** server + 2 agents | all three nodes | Proxmox schedules containers per node; k3s adds declarative manifests, self-healing and rescheduling across nodes |
| **Nextcloud** | P2 | files and sync — [runbook already written](runbooks/07-nextcloud.md) |
| **Jenkins** | P2 | CI/CD for other repositories |
| **OpenStack** | P3 | private cloud lab |
| **Apache CloudStack** | P3 | IaaS orchestration lab |
| **Login logs from every machine** | nodes, Pi, NAS | only LXC 102's SSH log is collected; a Proxmox web-UI brute force would go unseen |
| **CrowdSec bouncer** | OPNsense or the proxy | after weeks of watch-only data show how often a ban would be wrong |
| **cAdvisor** | LXC 102 | per-container CPU and RAM |
| **VPN lane** | OPNsense + Omada switch | WireGuard to Mullvad on OPNsense and a VLAN whose traffic can only leave through it, so chosen devices get a VPN without an app |
| **Egress filtering** | OPNsense | the game segment can currently reach anything outbound |
| **A subnet per service** | OPNsense | wings, AMP and the panel are currently neighbours |
| **Omada ES210X-M2** | rack | 802.1Q, so `vmbr1` becomes a real tagged VLAN and the firewall stops depending on the host it protects |

Two constraints apply to that list.

**k3s inside an unprivileged LXC needs extra work.** cgroup delegation, kernel
modules and the storage driver all have to be dealt with. A VM would be the
straightforward route, which conflicts with the LXC-only rule above. That
trade-off has to be made before this gets built.

**OpenStack and CloudStack on a 16 GB i5-7500T are a learning exercise, not a
deployment.** A realistic OpenStack controller wants more RAM than the whole
node has, and running it on Proxmox means nested virtualisation. It goes on P3
as a lab and it is labelled that way on purpose.

**WireGuard has been dropped from this list.** It was here to replace the game
port forwards, which made sense when the forwards were the whole problem.
Making players join the network is the right model for a private server and the
wrong one for a public one; the DMZ addresses the actual risk, for no recurring
cost and no friction for players. The reasoning is in
[`docs/11-hardening.md`](docs/11-hardening.md).

---

## Known limitations

Documented deliberately. A system's weak points are operational knowledge, and
a repository that lists only strengths is not documentation.

- **Alerts depend on the things they watch.** Grafana and Prometheus run in
  LXC 102 on P1, and the messages leave through the same internet line. If P1
  dies, nothing says so; if the internet is down, the alert arrives when it is
  back. A tiny external "is it alive" check would close the first gap.
- **Logins are only collected from LXC 102.** SSH and web-UI logins on the
  Proxmox nodes, the Pi and the NAS are not in Loki.
- **The containers are not scraped individually.** All three Proxmox nodes, the
  Proxmox API, the Raspberry Pi, the NAS, the router and the game servers are
  monitored; cAdvisor for per-container numbers in LXC 102 is not deployed.
- **Prometheus keeps 15 days**, its default. The compose example sets 90; the lab
  has not been switched yet. The location database for the logs is refreshed by
  hand, monthly.
- **The game-server alert cannot tell "I stopped it" from "it crashed".** The
  panels' activity logs would, but the monitoring user may not read them yet.
- **The game segment has no internal walls.** wings, AMP and the panel share
  `10.10.10.0/24` and are neighbours on one bridge, so traffic between them
  never reaches the firewall. Compromise a game server and you can reach the
  panel; panel admin means code execution on wings. A subnet per service is the
  fix.
- **Egress from the game segment is unrestricted.** The block rule stops it
  reaching the house; nothing stops it reaching the internet. A compromised
  server could mine, join a botnet, or attack third parties from this address.
- **The firewall runs on the machine it protects against.** OPNsense is a VM on
  pve2 and both bridges live on pve2, so root on that host defeats the whole
  arrangement. Only enforcement in hardware the compromised guest does not
  control closes this, which is what a managed switch would buy.
- **A leftover IPv6 allow rule sits under the block rule.** The block is IPv4
  only. Harmless while the segment has no IPv6 address, and an open door around
  it the moment it gets one. Visible in the rules screenshot above.
- **The Raspberry Pi is a single point of failure.** Ingress and LAN-wide DNS
  both run on it. If it dies, name resolution stops for every device on the
  network.
- **No offsite backup.** RAID 1 on the NAS protects against a dead disk, not
  against fire, theft or a mistaken `rm`. The backups are also unencrypted at
  rest.
- **P2 now carries everything that matters.** The whole game stack plus the
  firewall live on one node, so pve2 is a single point of failure for anything
  internet-facing, and P3 still holds no workload. That is what the k3s plan is
  meant to fix.
- **The house network is still flat.** Segmentation exists for the game servers
  and only for them. The switch is unmanaged, so there are no VLANs, and a
  compromised IoT device is still on the same network as the Proxmox API.
- **No 2FA on Proxmox.** The Proxmox API is root over every guest in the lab.
  This is the least defensible item on the list.
- **Provisioning is manual.** Containers are created by hand or by a shell
  script. Ansible or Terraform with the Proxmox provider is the obvious next
  step, and the scripts here are *consistency*, not infrastructure as code.
- **The AI agent's VM holds every key it uses.** Root inside five machines,
  power and snapshot rollback on every guest, write access to the repositories.
  It is LAN-only and its SSH key only works from its own address, but whoever
  owns VM 103 owns all of that. And `main` is not branch-protected yet, so
  "the agent never merges" is a rule, not a lock. See [docs/26](docs/26-ai-agent-devops.md#the-weak-spots-honestly).
- **No UPS.** A power cut is an unclean shutdown for all four machines at once.

The threat model that determines which of these matter, and the order in which
they are prioritised, is in [`docs/11-hardening.md`](docs/11-hardening.md).

---

## Security

Private addresses, internal ports and hostnames are published on purpose: they
are RFC1918, not routable from the internet, and worthless to anyone who is not
already inside the network. The hostnames are already in public Certificate
Transparency logs, so hiding them here would be theatre.

The same holds for `10.10.10.0/24`. It is RFC1918, it exists on one bridge
inside one node, and publishing it is what makes the firewall rules legible.
The rules are the interesting part.

The public IP, the IPv6 host addresses, MAC addresses, the DuckDNS hostname, the
WAN port forwards and every credential are not in this repository and never will
be. In the DMZ material that means exactly two things are held back: the public
address, and the **external** port numbers of the game forwards. Every internal
address, every firewall rule, the rule order, the NAT logic and the static route
are published in full, and screenshots have their MAC addresses and the
firewall's exact patch level blanked.

The rule is in [`docs/99-security-notes.md`](docs/99-security-notes.md). It is
enforced mechanically rather than by discipline:

```bash
./scripts/check-secrets.sh --install   # once
./scripts/check-secrets.sh --all       # scan everything
```

Every commit is then scanned for public IPv4 addresses, global IPv6 addresses,
MAC addresses, tunnel UUIDs, private keys, token-shaped strings and files named
like key material, and a commit containing one is refused.

A pre-commit hook is opt-in per clone, so the same scan also runs in CI
([`.github/workflows/checks.yml`](.github/workflows/checks.yml)) alongside a
shell syntax check, a YAML parse of every file, and a check that every relative
link and image resolves. A hook can be forgotten; CI cannot.

`shellcheck` runs there too, but **advisory only**. The split is deliberate: a
failing build should mean something is wrong, not that a linter has an opinion
about quoting. The scan that gates a merge is the secret scan, because a leak in
a public repository cannot be taken back.

---

<div align="center">

**[Wiki](docs/) · [Runbooks](runbooks/) · [Reports](docs/reports/) ·
[Compose files](compose/) · [Scripts](scripts/) ·
[Inventory](inventory/inventory.yml)**

MIT · [LICENSE](LICENSE)

</div>
