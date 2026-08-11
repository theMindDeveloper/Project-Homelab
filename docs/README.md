<div align="center">

# The wiki

**Reference material for the concepts and commands behind this lab.**

</div>

---

Two kinds of page live in this repository, and keeping them separate is what
stops both from rotting:

| | [`docs/`](.) — this directory | [`runbooks/`](../runbooks/) |
|---|---|---|
| Answers | *what is this and why* | *how do I do it, step by step* |
| Read when | learning, or deciding | executing, usually under pressure |
| Shape | explanation, tables, trade-offs | numbered steps with verification |
| Example | why Docker inside LXC needs `nesting=1` | create the LXC, install Docker, start Portainer |

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

### The platform

| | Page | What it answers |
|---|---|---|
| 03 | [Proxmox cheat sheet](03-proxmox-cheatsheet.md) | the commands, grouped by intent, with the traps |
| 05 | [Networking, DNS and TLS](05-networking-dns-tls.md) | how a request reaches a service, DNS-01, reverse proxy headers |
| 06 | [Storage](06-storage.md) | storage types, thin provisioning, bind mounts into unprivileged LXC, RAID is not backup |
| 07 | [Backup and recovery](07-backup-and-recovery.md) | `vzdump` modes, restoring, and the drill nobody runs |
| 08 | [Monitoring](08-monitoring.md) | the stack, PromQL that gets used, and the alerting gap |

### Operating it

| | Page | What it answers |
|---|---|---|
| 09 | [Linux administration](09-linux-admin.md) | systemd, journald, disks, network, SSH, permissions |
| 10 | [Troubleshooting](10-troubleshooting.md) | organised by **symptom**, because that is what you have |
| 11 | [Hardening](11-hardening.md) | the threat model, what is done, and what is deliberately not |
| 99 | [Security notes](99-security-notes.md) | what this **repository** publishes, and what it never will |

---

## Where to start

**Never touched any of this:**
[Glossary](00-glossary.md) → [Docker](01-docker.md) →
[LXC or VM](04-lxc-vs-vm.md) → [Docker Compose](02-docker-compose.md)

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
