<div align="center">

# The wiki

**Reference material for the concepts and commands behind this lab.**

</div>

---

Two kinds of page live in this repository, and keeping them separate is what
stops both from rotting:

| | [`docs/`](.) — this directory | [`runbooks/`](../runbooks/) | [`docs/reports/`](reports/) |
|---|---|---|---|
| Answers | *what is this and why* | *how do I do it, step by step* | *what happened, and what it cost* |
| Read when | learning, or deciding | executing, usually under pressure | understanding why the lab looks like this |
| Shape | explanation, tables, trade-offs | numbered steps with verification | dated narrative, dated and never rewritten |
| Example | why Docker inside LXC needs `nesting=1` | create the LXC, install Docker, start Portainer | the August 2026 DMZ migration |

Written for me, six months from now, having forgotten all of it.

---

## Pages

### Concepts

| | Page | What it answers |
|---|---|---|
| 00 | [Glossary](00-glossary.md) | every term used in this repository, defined once |
| 01 | [Docker](01-docker.md) | what a container actually is, the mental model, every command grouped by intent |
| 02 | [Docker Compose](02-docker-compose.md) | the file format, `up` vs `restart`, healthchecks, `.env` |
| 04 | [LXC or VM](04-lxc-vs-vm.md) | the decision rule, and what it costs to get it wrong |
| 13 | [Addressing and the OSI layers](13-addressing-and-osi-layers.md) | what a `/24` is, switch vs router vs firewall, why layer 2 cannot route |

### The platform

| | Page | What it answers |
|---|---|---|
| 03 | [Proxmox cheat sheet](03-proxmox-cheatsheet.md) | the commands, grouped by intent, with the traps |
| 05 | [Networking, DNS and TLS](05-networking-dns-tls.md) | how a request reaches a service, DNS-01, reverse proxy headers |
| 06 | [Storage](06-storage.md) | storage types, thin provisioning, bind mounts into unprivileged LXC, RAID is not backup |
| 07 | [Backup and recovery](07-backup-and-recovery.md) | `vzdump` modes, restoring, and the drill nobody runs |
| 08 | [Monitoring](08-monitoring.md) | the stack, PromQL that gets used, and the alerting gap |

### The network, after the DMZ migration

Written after the August 2026 rebuild. Read in order; each assumes the one
before it.

| | Page | What it answers |
|---|---|---|
| 12 | [Network segmentation](12-network-segmentation.md) | **start here.** why rules on a flat network never worked, and what a DMZ actually is |
| 13 | [Addressing and the OSI layers](13-addressing-and-osi-layers.md) | the vocabulary everything else assumes |
| 14 | [Proxmox bridges, NICs and VirtIO](14-proxmox-bridges-and-nics.md) | `vmbr0` vs `vmbr1`, `bridge-ports none`, why "no cable" is not "no connection" |
| 15 | [NAT and port forwarding](15-nat-and-port-forwarding.md) | SNAT vs DNAT, double NAT, reflection, and why a route is not a permission |
| 16 | [Firewalls and `pf`](16-firewalls-and-pf.md) | stateful filtering, rule order, and the rule that looks like a hole and is not |
| 17 | [OPNsense concepts](17-opnsense-concepts.md) | why a VM, why not pfSense, and the WAN/LAN naming trap |
| 18 | [FreeBSD basics](18-freebsd-basics.md) | the commands that differ, for someone who only knows Linux |
| 19 | [LXC migration and resources](19-lxc-migration-and-resources.md) | offline migration, memory caps vs reservations, thin provisioning |
| 20 | [Game server hosting](20-game-server-hosting.md) | the four places Pterodactyl stores an address, and AMP's machine-bound licence |

### Operating it

| | Page | What it answers |
|---|---|---|
| 09 | [Linux administration](09-linux-admin.md) | systemd, journald, disks, network, SSH, permissions |
| 10 | [Troubleshooting](10-troubleshooting.md) | organised by **symptom**, because that is what you have |
| 11 | [Hardening](11-hardening.md) | the threat model, what is done, and what is deliberately not |
| 99 | [Security notes](99-security-notes.md) | what this **repository** publishes, and what it never will |

### Reports

| Date | Report | What it covers |
|---|---|---|
| 2026-08-13 | [DMZ migration](reports/2026-08-13-dmz-migration.md) | the full narrative: options rejected, every step, every problem hit, and an honest security grade |

The [reports index](reports/) explains why these are a third kind of page.

---

## Where to start

**Never touched any of this:**
[Glossary](00-glossary.md) → [Docker](01-docker.md) →
[LXC or VM](04-lxc-vs-vm.md) → [Docker Compose](02-docker-compose.md)

**Never touched networking, and the DMZ pages look like noise:**
[Addressing and the OSI layers](13-addressing-and-osi-layers.md) →
[Network segmentation](12-network-segmentation.md) →
[Proxmox bridges](14-proxmox-bridges-and-nics.md) →
[NAT](15-nat-and-port-forwarding.md) → [Firewalls](16-firewalls-and-pf.md)

**Here for the DMZ specifically:**
[Network segmentation](12-network-segmentation.md) →
[the migration report](reports/2026-08-13-dmz-migration.md) →
[runbooks 12 to 18](../runbooks/)

**Know Docker, new to Proxmox:**
[LXC or VM](04-lxc-vs-vm.md) → [Proxmox cheat sheet](03-proxmox-cheatsheet.md) →
[Storage](06-storage.md)

**Something is broken right now:**
[Troubleshooting](10-troubleshooting.md), and nothing else.

**Here to judge whether the lab is competently run:**
[Hardening](11-hardening.md) and [Security notes](99-security-notes.md). Both
contain the parts that are missing as well as the parts that are done.

---

## A note on the writing

Every page tries to answer *why*, not just *how*, and to say what a choice
costs. A cheat sheet that lists `pct enter 102` without explaining that there is
no `qm enter`, and why, teaches you to type a command. Knowing that a VM is
opaque to the host because it runs its own kernel means you never need to look
that up again.

Where something in this lab is wrong, missing or a compromise, it is written
down as such. The limitations sections are not modesty; they are the parts that
are load-bearing when something breaks.

---

**Back to:** [repository root](../README.md)
