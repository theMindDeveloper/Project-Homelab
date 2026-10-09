<div align="center">

# Runbooks

**Step-by-step procedures. Written to be followed, not read.**

</div>

---

A runbook is what [`docs/`](../docs/) is not. The wiki explains *what something
is and why*; a runbook is a numbered sequence you execute, ideally while tired
and slightly stressed.

Every page here follows the same shape:

| | |
|---|---|
| **Goal** | one sentence, in terms of the finished state |
| **Time** | realistic, not optimistic |
| **Prerequisites** | what must already exist |
| **Reverses cleanly?** | can this be undone, and how |
| **Steps** | numbered, with the reasoning for the non-obvious ones |
| **Verify** | ordered so a failure identifies its own cause |
| **If it goes wrong** | symptom → cause → fix |
| **Undo** | the commands to remove it |

---

## The runbooks

### Building blocks

| | Runbook | Time |
|---|---|---|
| 01 | [Create an LXC container](01-create-an-lxc-container.md) | 3 min |
| 02 | [Docker and Portainer on a new LXC](02-portainer-on-a-new-lxc.md) — **the full walkthrough** | 20 min |
| 04 | [Put a service behind Nginx Proxy Manager](04-nginx-proxy-manager-vhost.md) | 3 min |

### Infrastructure

| | Runbook | Time |
|---|---|---|
| 03 | [AdGuard Home as the LAN resolver](03-adguard-home-dns.md) | 20 min |
| 06 | [Publish one service with a Cloudflare Tunnel](06-cloudflare-tunnel.md) | 15 min |
| 08 | [Add a node to the Proxmox cluster](08-add-a-node-to-the-cluster.md) | 15 min |

### The DMZ

Run these **in order**. Each assumes the one before it. The reasoning behind all
of them is [`docs/12-network-segmentation.md`](../docs/12-network-segmentation.md),
and the story of doing it for real is
[the migration report](../docs/reports/2026-08-13-dmz-migration.md).

| | Runbook | Time |
|---|---|---|
| 12 | [Create an isolated bridge](12-create-an-isolated-bridge.md) | 5 min |
| 13 | [Install the OPNsense VM](13-install-the-opnsense-vm.md) | 45 min |
| 14 | [Write the DMZ firewall rules](14-opnsense-dmz-firewall-rules.md) — **the one that matters** | 20 min |
| 15 | [Move an LXC into the DMZ](15-move-an-lxc-into-the-dmz.md) | 10 min + copy time |
| 16 | [Publish a game server port](16-publish-a-game-server-port.md) | 2 min per game |
| 17 | [Recover from an OPNsense lockout](17-recover-from-an-opnsense-lockout.md) — **read before you need it** | 5 min |
| 18 | [Reconfigure Pterodactyl after a move](18-reconfigure-pterodactyl-after-a-move.md) | 20 min |

### Services

| | Runbook | Time |
|---|---|---|
| 05 | [Glance dashboard](05-glance-dashboard.md) | 15 min |
| 07 | [Nextcloud](07-nextcloud.md) — *planned, not yet deployed* | 60 min |
| 20 | [qBittorrent behind gluetun on the NAS](20-qbittorrent-behind-gluetun.md) | 30 min |

### Monitoring, logs and alerts

Run these **in order**; each builds on the one before. The concepts are in
[`docs/08`](../docs/08-monitoring.md), [`docs/23`](../docs/23-logs-and-security-monitoring.md)
and [`docs/24`](../docs/24-alerting.md), and the story of building it is
[the October report](../docs/reports/2026-10-08-monitoring-security-alerting.md).

| | Runbook | Time |
|---|---|---|
| 10 | [Prometheus, Grafana and the exporters](10-monitoring-stack.md) — every node, the Pi, the NAS, the Proxmox API | 60-90 min |
| 21 | [Logs: Loki, Alloy, the firewall log and CrowdSec](21-logs-and-crowdsec.md) | 45-60 min |
| 22 | [The real visitor IP behind a Cloudflare tunnel](22-real-visitor-ip-behind-a-tunnel.md) | 15 min |
| 23 | [Alerts to Telegram](23-alerts-to-telegram.md) | 30 min |
| 24 | [FRITZ!Box monitoring](24-fritzbox-monitoring.md) | 15 min |
| 25 | [Game server monitoring (AMP + Pterodactyl)](25-game-server-monitoring.md) | 30 min |
| 26 | [Test dashboard and alert changes before they go live](26-test-grafana-changes-safely.md) — **before every change** | 5-15 min |

### The AI agent

| | Runbook | Time |
|---|---|---|
| 27 | [An AI agent with least privilege](27-ai-agent-with-least-privilege.md) — own accounts, PRs, merge = apply | an evening |

Why it is built this way: [`docs/26`](../docs/26-ai-agent-devops.md).

### Operations

| | Runbook | Time |
|---|---|---|
| 09 | [The backup restore drill](09-backup-restore-drill.md) — **quarterly** | 30 min |
| 11 | [Rebuild the lab from zero](11-rebuild-from-zero.md) | a weekend |

---

## If something in the DMZ is broken right now

[Runbook 17](17-recover-from-an-opnsense-lockout.md) if you cannot reach the
firewall GUI. [Runbook 18](18-reconfigure-pterodactyl-after-a-move.md) if the
game console will not connect. The symptom index in
[`docs/20`](../docs/20-game-server-hosting.md#symptom-index) maps most of the
rest.

---

## If you only read one

**[Runbook 02](02-portainer-on-a-new-lxc.md).** It goes from an empty Proxmox
node to a service in a browser with a real certificate, and every other service
in this lab is the same six steps with a different compose file:

1. create an unprivileged LXC with `nesting=1`
2. install Docker from Docker's own repository
3. start the service with Compose
4. add a proxy host in NPM against the wildcard certificate
5. verify, working up the stack
6. record it in the inventory, in Glance and in the health check

---

## Conventions

**Every command is meant to be run as written.** Where a value has to change, it
is a placeholder in the same shape as the real thing, not a description.

**The reasoning for a non-obvious step is next to it**, not in a separate
document. `--unprivileged 1` has two sentences under it explaining what it maps
and that it cannot be changed later, because that is the moment you need to know.

**Verification is a step, not an afterthought**, and it is ordered from the
bottom of the stack upward so that where it fails tells you what is at fault.

**Undo is documented.** A procedure you cannot reverse is a procedure you will
hesitate to start.

**Failure modes come from experience**, not from imagination. Every "if it goes
wrong" table entry is something that happened.

---

**See also:** [the wiki](../docs/) · [compose files](../compose/) ·
[scripts](../scripts/) · [repository root](../README.md)
