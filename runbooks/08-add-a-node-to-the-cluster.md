# Runbook 08 · Add a node to the Proxmox cluster

**Goal** A third node joins `HomelabCluster`, giving three votes and a quorum
of two.

**Time** 15 minutes.
**Prerequisites** A fresh Proxmox install. Same major version as the cluster.
**Reverses cleanly?** **No.** Read the warning.

---

## Read this first

**Joining a cluster erases the new node's existing guests.** The join replaces
`/etc/pve` with the cluster's copy. Any VM or container on the joining node is
gone. Migrate them off, or back them up and restore afterwards, before you
start.

**`pvecm delnode` is not reversible.** A removed node must never rejoin under
the same name without a full reinstall. Its keys and its entry in the corosync
configuration are stale, and forcing it back produces a cluster that appears to
work and disagrees with itself.

---

## 1 · Before joining

On the **new** node:

```bash
pveversion                    # major version must match the cluster
hostname                      # unique, and it becomes the node name FOREVER
cat /etc/hosts                # must map its own name to its own IP
timedatectl                   # NTP synced - corosync is latency sensitive
qm list ; pct list            # expect empty
```

**The hostname is permanent.** Renaming a node in a Proxmox cluster is a
documented but unpleasant procedure. Get it right now.

**Clock synchronisation is not optional.** Corosync exchanges tokens with tight
timing. A node whose clock drifts drops out of the cluster intermittently, which
looks like a network fault and is not.

Every node must resolve every other node's name. On a small cluster,
`/etc/hosts` on each node is simpler and more reliable than depending on DNS:

```
192.168.178.20  pve
192.168.178.50  pve2
192.168.178.77  pve3
```

---

## 2 · Join

On the **new** node:

```bash
pvecm add 192.168.178.20
```

It asks for the root password of the existing node, copies the cluster
configuration, and restarts `pve-cluster` and `corosync`. **The web UI on the
joining node will disconnect.** That is expected; reconnect after a minute.

---

## 3 · Verify, from every node

```bash
pvecm status
pvecm nodes
```

What to look for:

```
Nodes:            3
Expected votes:   3
Highest expected: 3
Total votes:      3
Quorum:           2
Flags:            Quorate
```

`Quorate` and `Quorum: 2` is the state you want. Run it on **all three** nodes:
a cluster where the nodes disagree about membership is worse than no cluster.

```bash
pvesh get /cluster/resources --type vm      # every guest, from any node
ls -l /etc/pve/nodes/                       # a directory per node
```

---

## 4 · Understand what quorum means for you

Three votes, two needed.

| State | Result |
|---|---|
| 3 nodes up | fully operational |
| 2 nodes up | **quorate** — everything works, one node down |
| 1 node up | **not quorate** — `/etc/pve` goes read-only |

A node in the minority makes `/etc/pve` read-only rather than risk two halves of
a split cluster both editing configuration. That read-only state is what the
grey question marks in the web UI mean. The guests keep running the whole time.

**Two-node clusters are a trap.** Two votes, quorum of two, so *either* node
going down loses quorum on the other. Three is the smallest sensible cluster.
Alternatives, if a third machine is not available: a QDevice (a tiny external
tiebreaker, a Raspberry Pi will do) or `two_node: 1` in corosync.conf.

### The emergency override

```bash
pvecm expected 1
```

Tells corosync to expect one vote, making a lone node writable. **Temporary
only.** Leaving it set while other nodes come back is how you get two halves of
a cluster both convinced they are authoritative.

---

## 5 · After joining

```bash
# migrate a guest onto the new node
pct migrate 102 pve3 --restart          # LXC: restart required, no live migration
qm  migrate 100 pve3 --online           # VM: live migration works

# node-local things the cluster does NOT synchronise
apt install prometheus-node-exporter
```

**LXC containers cannot live-migrate.** They are processes on the host's kernel,
and a process cannot move between kernels. `--restart` stops the container,
copies it and starts it on the target. With local storage, the disk is copied
over the network, so it is not instant.

`/etc/pve` **is** synchronised: guest configs, users, ACLs, storage definitions,
firewall rules. `/etc/network/interfaces`, installed packages and node-local
services are **not**. New nodes need their exporters and their repository
configuration set up individually.

---

## Removing a node

```bash
# migrate everything off it first, then power it OFF, then from a REMAINING node:
pvecm delnode pve3
```

Order matters. Removing a node that is still running leaves it convinced it is
still a member, and it will keep trying to talk to the cluster.

After removal, clean up the stale directory on a remaining node:

```bash
rm -rf /etc/pve/nodes/pve3
```

**That node must be reinstalled before it can join anything again.**

---

## If it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| join hangs | no route, or the name does not resolve | `/etc/hosts` on both, `ping` both ways |
| "cluster not ready - no quorum" | the existing cluster already lacks quorum | fix that first |
| node joins then drops out | clock drift, or a flaky link | `timedatectl`, then `journalctl -u corosync` |
| grey question marks everywhere | quorum lost | `pvecm status` |
| "authentication key already exists" | a previous failed join | `systemctl stop pve-cluster corosync`, `rm /etc/corosync/*`, reinstall is safest |
