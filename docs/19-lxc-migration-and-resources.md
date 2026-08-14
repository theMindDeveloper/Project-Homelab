# LXC migration between nodes, and what "allocated" actually means

Moving three containers onto one node was the prerequisite for the DMZ, because
a software bridge exists on exactly one host and everything attached to it must
live there too. That forced a second question immediately: does the target node
have the resources, and what do the numbers in the Proxmox UI actually promise?

---

## Migration in a cluster

`pct migrate` moves a container to another node. Because these are containers
and not VMs, the migration is **offline**: the container stops, the disk is
copied, the container starts on the other side.

```bash
pct migrate 105 pve2 --restart --target-storage local-lvm
```

| Flag | Meaning |
|---|---|
| `--restart` | stop it, move it, start it again. Without this the migration refuses if the container is running. |
| `--target-storage` | which storage on the destination receives the disk |
| `--online` | **VMs only.** There is no live migration for LXC. |

Real timings from this lab, on gigabit, NVMe to NVMe:

| Container | Disk | Time |
|---|---|---|
| 105 wings (game data) | large | 8m 12s |
| 107 amp (game data) | large | 8m 48s |
| 106 panel (web app) | small | 52s |

**That is the downtime.** For an offline migration the copy time *is* the
outage, so measure the disk before promising anyone a maintenance window.

### Why `--target-storage` was needed

Container 105's disk lived on a storage named `pve`; 107's lived on
`local-lvm`. Both storages exist on pve2, but a migration fails if the named
source storage does not exist on the destination. Naming the target explicitly
standardises everything on arrival and removes a whole class of failure.

### Before migrating

```bash
pct list                       # what is where
pct config 105                 # memory, cores, disk, features
pvesm status                   # storage names and free space on every node
```

The discovery pass is not optional. It is where I found that 105 had 12 GB
allocated and 107 had 8 GB, against a target node that at the time had 15.5 GB
of RAM in total. Both would not fit alongside a 2 GB firewall VM.

### After migrating

The container keeps its VMID, hostname, disk contents and configuration. What
does **not** follow it:

- anything keyed to the physical machine, such as a licence bound to a machine
  fingerprint (see [20](20-game-server-hosting.md#amp-and-machine-bound-licences))
- host-level bind mounts that do not exist on the destination
- assumptions elsewhere in your infrastructure about which node it is on

---

## Memory: a cap, not a reservation

This is the single most useful thing to understand before sizing anything.

| | LXC | VM |
|---|---|---|
| `--memory 6144` means | "may use **up to** 6 GB" | "the guest is given 6 GB to manage" |
| Unused memory is | available to everything else on the host | generally not returned once touched |
| Hitting the limit | the OOM killer runs **inside that container** | the guest's own OOM killer runs |

An LXC container with 6 GB allocated and 400 MB in use is consuming 400 MB of
the host's RAM. You can allocate far more in total than the machine has, and it
works fine, right up until several guests are busy at once.

A VM's memory behaves differently because the guest kernel manages it: as the
guest touches pages, the hypervisor backs them, and it does not generally give
them back. Plan a VM's allocation as though it were reserved.

```bash
pct set 105 --memory 6144      # trim a running container's cap
```

### The trap this creates

Container 105 was trimmed from 12 GB to 6 GB. The Pterodactyl panel, however,
still had a per-server memory limit of 12 GiB configured for the Zomboid server.
The game grew past 6 GB, the container's cgroup limit fired, and the process was
killed with **exit code 137**.

> **Whenever a container's memory cap changes, every application-level memory
> limit inside it has to change to match.** Two independent limits that disagree
> means the lower one wins, silently and violently.

---

## CPU: cores are not reserved either

```bash
pct set 105 --cores 2
```

That gives the container two vCPUs, scheduled onto whatever physical cores are
free at the time. It does not pin, reserve or dedicate anything.

Handing out a total of nine cores across guests on a four-core CPU is normal and
is called **overcommitting**. It works because guests are idle most of the time.

**Watch load average, not the sum of allocations.**

```bash
uptime                         # 1, 5 and 15 minute load average
```

On a 4-core box, sustained load under 4.0 is healthy. The sum of allocated cores
tells you nothing useful.

**Do not over-allocate cores "to be safe."** The hypervisor tries to schedule a
guest's vCPUs together, so a guest with more vCPUs than it needs is slightly
harder to schedule and can perform marginally worse than the same guest with
fewer.

---

## Storage, and thin provisioning

| Storage | Type | Behaviour |
|---|---|---|
| `local` | directory | ISOs, templates, backups. Files on `/`. |
| `local-lvm` (or `pve`) | LVM-thin | guest disks. **Space consumed as written, not as allocated.** |
| `hdd-1tb` | directory | a separate spinning disk, mounted at `/mnt/pve/hdd-1tb` |

Thin provisioning means a 48 GB guest disk does not reserve 48 GB. You can
promise more than the pool physically has, which is useful and is also the
mechanism by which you can quietly destroy everything.

> **If a thin pool fills, guests do not get a clean "disk full". They get I/O
> errors and filesystem corruption.**

Watch it:

```bash
lvs -o lv_name,lv_size,data_percent,metadata_percent pve
df -h /
```

Act at **80%** on `data_percent`. Note that `metadata_percent` can fill
independently and is just as fatal.

On these nodes `local` and `local-lvm` share the same NVMe, so a full root
breaks Proxmox itself, not merely a guest.

### Confirming guests are on the fast disk

```bash
lsblk -o NAME,SIZE,ROTA,MOUNTPOINT     # ROTA 0 = SSD/NVMe, 1 = spinning
pvs                                     # which physical volume backs the VG
```

Worth checking after a migration, because `--target-storage` decides this and it
is easy to send a game server onto the 1 TB spinner by accident.

---

## Backups before a migration

The honest note: the intended backup to the NAS was skipped during this
migration because the NAS had no drives installed at the time.

```bash
vzdump 105 --storage local --mode snapshot --compress zstd
```

`--mode snapshot` keeps the container running during the dump. For anything
where the data matters, this is not optional, and "the migration is offline
anyway" is not a substitute: a migration that fails halfway leaves you needing
the backup you did not take.

---

## Checklist for moving a container to another node

1. `pct config <id>` and `pvesm status` on the destination. Does it fit?
2. Trim the memory cap if it does not, and note every application-level limit
   that now has to change too.
3. Back up, to somewhere that is not either node.
4. `pct migrate <id> <node> --restart --target-storage <storage>`
5. `pct list` on the destination, and `lsblk` to confirm the disk landed on the
   intended storage.
6. Reactivate anything licensed to a machine fingerprint.
7. Update `inventory/inventory.yml`, which is the whole point of having one.

---

**Next:** [20 · Game server hosting internals](20-game-server-hosting.md)
