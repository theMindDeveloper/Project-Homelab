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

### Services

| | Runbook | Time |
|---|---|---|
| 05 | [Glance dashboard](05-glance-dashboard.md) | 15 min |
| 07 | [Nextcloud](07-nextcloud.md) — *planned, not yet deployed* | 60 min |
| 10 | [Prometheus, Grafana and the exporters](10-monitoring-stack.md) | 45 min |

### Operations

| | Runbook | Time |
|---|---|---|
| 09 | [The backup restore drill](09-backup-restore-drill.md) — **quarterly** | 30 min |
| 11 | [Rebuild the lab from zero](11-rebuild-from-zero.md) | a weekend |

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
