# Runbook 15 · Move an LXC into the DMZ

**Goal** An existing container ends up on pve2, attached to `vmbr1`, with a
`10.10.10.x` address, reaching the internet and nothing in the house.

**Time** 10 minutes plus the migration copy, which is dominated by disk size.
Budget 10 minutes per 50 GB on gigabit.
**Prerequisites** [Runbooks 12](12-create-an-isolated-bridge.md),
[13](13-install-the-opnsense-vm.md) and
[14](14-opnsense-dmz-firewall-rules.md) done.
**Reverses cleanly?** Yes, but not instantly: reversing means another offline
migration if the container came from a different node.

Background on migration mechanics and what "allocated" memory means is in
[`docs/19-lxc-migration-and-resources.md`](../docs/19-lxc-migration-and-resources.md).

---

## 0 · Discovery, before you touch anything

```bash
pct list                       # what is where
pct config 105                 # memory, cores, disk, features, current net
pvesm status                   # storage names and free space on every node
```

Answer three questions:

| Question | Command | If the answer is bad |
|---|---|---|
| Does it fit on the target node? | `pct config` memory vs `free -h` on the target | trim the cap, step 1 |
| Does the source storage name exist on the target? | `pvesm status` | name `--target-storage` explicitly |
| Is anything licensed to this physical machine? | you have to know | plan to reactivate, step 6 |

This pass is where I found 105 at 12 GB and 107 at 8 GB against a target node
that then had 15.5 GB total. Both would not fit alongside a 2 GB firewall VM.

---

## 1 · Trim memory if needed

```bash
pct set 105 --memory 6144
pct set 107 --memory 6144
```

An LXC memory value is a **cap, not a reservation**. Setting 6144 means "may use
up to 6 GB"; unused memory stays available to everything else.

> **If you change a container's cap, change every application-level memory limit
> inside it to match.** Container 105 was trimmed to 6 GB while the Pterodactyl
> panel still allocated 12 GiB to the Zomboid server. The game grew past 6 GB,
> the cgroup limit fired, and the process died with **exit code 137**. Two
> limits that disagree means the lower one wins, silently.

---

## 2 · Back up

```bash
vzdump 105 --storage <somewhere-not-either-node> --mode snapshot --compress zstd
```

`--mode snapshot` keeps the container running during the dump.

"The migration is offline anyway" is not a substitute. A migration that fails
halfway leaves you needing the backup you did not take.

---

## 3 · Migrate to the node that owns the bridge

```bash
pct migrate 105 pve2 --restart --target-storage local-lvm
```

| Flag | Meaning |
|---|---|
| `--restart` | stop, move, start. Without it the migration refuses on a running container. |
| `--target-storage` | which storage receives the disk. Name it explicitly. |

**This is the downtime.** LXC has no live migration; the copy time is the
outage.

Real timings from this lab: 105 took 8m 12s, 107 took 8m 48s, 106 took 52s.

Confirm the disk landed on the fast storage:

```bash
lsblk -o NAME,SIZE,ROTA,MOUNTPOINT      # ROTA 0 = NVMe/SSD
pvs
```

---

## 4 · Attach to the sealed bridge

One command changes the bridge, the address and the gateway together.

```bash
pct set 105 --net0 name=eth0,bridge=vmbr1,ip=10.10.10.20/24,gw=10.10.10.1
```

`gw=10.10.10.1` tells the container "when you want anything outside your own
network, hand it to OPNsense". Without a gateway it can talk to its neighbours
on `vmbr1` and nothing else.

---

## 5 · Fix DNS

```bash
pct set 105 --nameserver 1.1.1.1
pct reboot 105
```

**This step is not optional and is easy to forget.** The LAN resolver
(AdGuard at `192.168.178.178`) sits inside the range the block rule refuses. The
container will reach the internet fine and resolve nothing, which presents as
"the network is broken" and is not.

**Cost:** these containers lose ad blocking. Irrelevant for game servers.

**The cleaner fix, for later:** enable Dnsmasq on the OPNsense LAN leg and point
the containers at `10.10.10.1`. Then the firewall resolves on their behalf and
nothing in the DMZ talks to a public resolver directly.

---

## 6 · Reactivate anything licensed to the hardware

A licence bound to a **machine fingerprint** breaks when the container lands on
a different physical host.

```bash
pct exec 107 -- su - amp -c "ampinstmgr reactivate <InstanceName>"
```

Symptom if you skip it:

```
[Licencing Error/6] : Unable to load licence - NoMatchingMachineId
[Core Warning/10]   : Expected licence feature RunAMP is not present.
```

Rule out DNS and outbound HTTPS first, and confirm no other instance is running
and holding a concurrency slot, before concluding it is the fingerprint.

---

## 7 · Fix anything that stored the old address

Applications that bind to `0.0.0.0` need nothing: they follow the interface.
Applications that store addresses need every copy updated.

For Pterodactyl that is four places, and they were all wrong at once. Full
detail in [runbook 18](18-reconfigure-pterodactyl-after-a-move.md) and
[`docs/20`](../docs/20-game-server-hosting.md).

---

## 8 · Update the inventory

```
inventory/inventory.yml
```

Change the node, the network, the address, the gateway, the nameserver and the
memory. This file is the single source of truth every diagram and README table
derives from, and a migration that is not recorded there is a migration that
will confuse you in six months.

---

## Verify

Work upward.

```bash
# 1 · the container is where you think and has the address you think
pct list
pct exec 105 -- ip -br a

# 2 · it can reach its own gateway
pct exec 105 -- ping -c2 10.10.10.1

# 3 · it can reach the internet
pct exec 105 -- timeout 5 curl -s -o /dev/null -w 'steam=%{http_code}\n' https://store.steampowered.com

# 4 · it CANNOT reach the house
for target in 192.168.178.77:8006 192.168.178.49 192.168.178.178; do
  echo -n "$target -> "
  pct exec 105 -- timeout 4 curl -sk -o /dev/null "https://$target" 2>/dev/null \
    && echo REACHABLE || echo blocked
done

# 5 · it can reach its neighbours in the segment
pct exec 105 -- timeout 5 curl -s -o /dev/null -w 'panel=%{http_code}\n' http://10.10.10.22

# 6 · the service itself is listening
pct exec 107 -- ss -tulnp
```

Step 4 must print `blocked` on every line. **Exit code 124 is success here.**

---

## If it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Migration refuses to start | container is running | add `--restart` |
| Migration fails on storage | source storage name absent on the target | `--target-storage <name that exists there>` |
| Container has no network at all | no gateway set | re-run the `pct set --net0` line with `gw=` |
| Internet works, names do not resolve | DNS server is behind the block rule | `pct set <id> --nameserver 1.1.1.1` |
| Game killed, exit code 137 | container cap below the application's limit | reconcile both, see step 1 |
| `NoMatchingMachineId` | licence bound to the old host | step 6 |
| Service unreachable after the move | it binds to a specific address, not `0.0.0.0` | update its config |
| Disk ended up on the spinning drive | wrong `--target-storage` | `pct move-volume` to the right storage |

---

## Undo

```bash
pct set 105 --net0 name=eth0,bridge=vmbr0,ip=192.168.178.36/24,gw=192.168.178.1
pct set 105 --nameserver 192.168.178.178
pct reboot 105
# and, if it needs to go back to another node:
pct migrate 105 pve --restart --target-storage local-lvm
```

Reverting the network takes seconds. Reverting the node is another offline
migration.

---

**Next:** [Runbook 16 · Publish a game server port](16-publish-a-game-server-port.md)
