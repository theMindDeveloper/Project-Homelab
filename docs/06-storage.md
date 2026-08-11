# Storage

Proxmox storage types, what each one can and cannot do, thin provisioning and
the way it fails, RAID and why it is not a backup.

---

## Proxmox storage types

Proxmox does not have one filesystem. It has *storages*, each with a type, and
the type decides what is possible. The snapshot button being greyed out is
almost always the type, not a bug.

| Type | Stores | Snapshots | Thin | Notes |
|---|---|---|:---:|---|
| **Directory** (`dir`) | files on a normal filesystem | qcow2 only | qcow2 only | the default `local`. Holds ISOs, templates, backups. |
| **LVM** | block devices | no | no | fast, no snapshots for VMs |
| **LVM-thin** | block devices | **yes** | **yes** | the default `local-lvm`. What most single-disk installs use. |
| **ZFS** | datasets and zvols | **yes** | **yes** | checksums, compression, send/receive. Wants RAM. |
| **Btrfs** | subvolumes | yes | yes | supported, less common in practice |
| **NFS / CIFS** | files, over the network | qcow2 only | qcow2 only | shared between nodes, so migration works |
| **Ceph RBD** | distributed block | yes | yes | real shared storage, wants ≥3 nodes and a fast network |

### What this lab uses

| Node | Storage | Type | Holds |
|---|---|---|---|
| P1 | `local` | directory | ISOs, LXC templates, backups |
| P1 | `local-lvm` | LVM-thin | guest root filesystems |
| P2 | `local`, `local-lvm`, `hdd-1tb` | dir / LVM-thin / dir | as above, plus bulk |
| P3 | `local`, `local-lvm` | dir / LVM-thin | as above |
| NAS | 2 × 6 TB RAID 1 | — | media, photos, backup target |

**There is no shared storage between the nodes.** That is worth stating because
it explains a limitation people expect not to exist: with local-only storage, a
migration copies the entire disk over the network. It works, it is just not
instant, and the cluster cannot do HA failover of a stopped node's guests
because the disks are on that node.

---

## Commands

```bash
pvesm status                    # every storage: type, size, used, available
pvesm list local                # contents of one storage
pvesm alloc local-lvm 110 vm-110-disk-0 8G

df -h                           # filesystem usage - the OBVIOUS answer
lsblk                           # block devices as a tree
vgs ; lvs                       # LVM volume groups and logical volumes
lvs -o +data_percent,metadata_percent   # thin pool usage - the REAL answer
```

`df -h` on a Proxmox host does not show you the thin pool. `lvs` does. This
distinction is the subject of the next section and it is the most useful thing
on this page.

### ZFS

```bash
zpool status                    # health. run this weekly.
zpool list
zfs list -o name,used,avail,refer,compressratio
zpool scrub rpool               # verify every block against its checksum
zfs get compression rpool
zfs snapshot rpool/data@manual
zfs list -t snapshot
```

`zpool status` belongs in a weekly routine. **A degraded mirror behaves
perfectly and gives no visible symptom** until the second disk dies. There is no
warning light. The only signal is that command.

---

## Thin provisioning, and the way it kills you

LVM-thin and ZFS both let you allocate more space than exists. Five containers
with 16 GB disks on a 60 GB pool is fine, because each one only consumes what it
has actually written.

Until they write it.

**When a thin pool fills, every guest on it goes read-only at once.** Not
gradually, not with a warning: all of them, immediately, mid-write. Databases
corrupt. The host itself may become unstable if root is on the same pool.

The trap is that `df -h` inside a container shows plenty of free space, because
the container genuinely has free space in *its* 16 GB. The pool underneath is
what ran out.

```bash
# The command that tells the truth
lvs -o lv_name,lv_size,data_percent,metadata_percent

  LV       LSize   Data%  Meta%
  data     60.00g  91.44  4.21     <- this is the number that matters
```

**Watch metadata percentage too.** The metadata volume is small and separate,
and a full metadata volume breaks the pool just as completely as full data,
while `Data%` still reads 60.

### Preventing it

1. **Alert on the pool, not the guest.** `node_exporter` on the host exposes it;
   there is a panel for it in the Grafana dashboard.
2. **`discard`/TRIM matters.** Deleting a file inside a guest does not free the
   block in the pool unless the guest tells the layer below. Enable
   `discard=on` on the disk and run `fstrim -av` inside guests, or enable the
   `fstrim.timer`.
3. **Delete snapshots.** A snapshot keeps every block it references. A forgotten
   snapshot on a busy guest grows without bound and is the classic cause of a
   pool that filled for no apparent reason.

```bash
pct listsnapshot 102
qm listsnapshot 100
```

---

## Growing a disk

```bash
pct resize 102 rootfs +8G        # LXC: online, filesystem grown automatically
qm resize 100 scsi0 +20G         # VM: grows the BLOCK DEVICE only
```

For a VM, that command is half the job. The partition table and the filesystem
inside the guest still think the disk is the old size:

```bash
# inside the guest
lsblk                            # confirm the disk is bigger
growpart /dev/sda 1              # extend partition 1 to fill the disk
resize2fs /dev/sda1              # ext4
# or
xfs_growfs /                     # xfs
```

**Shrinking is not supported.** Not for LXC, not for VMs, not safely. Growing is
one command; shrinking means create a smaller disk, copy, swap. Size
conservatively.

---

## Bind mounts into an unprivileged LXC

The single most common reason people give up on unprivileged containers.

An unprivileged container maps its root (UID 0) to a high host UID, usually
100000. A file owned by `root` on the host appears inside the container as owned
by `nobody`, and a file the container creates as root is owned by `100000` on
the host. Both directions look broken.

```bash
# on the host
pct set 102 --mp0 /srv/media,mp=/media
```

Then fix the ownership so both sides agree. The simple approach: create a group
on the host with a GID that maps cleanly, and chown the data to it.

```bash
# host: give the container's UID range ownership
chown -R 100000:100000 /srv/media
```

The neater approach, when several containers share data, is an explicit id map
in `/etc/pve/lxc/102.conf`:

```
lxc.idmap: u 0 100000 1000
lxc.idmap: g 0 100000 1000
lxc.idmap: u 1000 1000 1        # container UID 1000 == host UID 1000
lxc.idmap: g 1000 1000 1
lxc.idmap: u 1001 101001 64535
lxc.idmap: g 1001 101001 64535
```

This says: map everything to the 100000 range as usual, **except** UID/GID 1000,
which maps to host 1000 directly. Now a file owned by host user 1000 is owned by
container user 1000. The ranges must tile the whole 0–65535 space with no gaps
and no overlaps, and `/etc/subuid` and `/etc/subgid` on the host must permit the
ranges you use.

It is a ten-minute job and it is worth doing rather than switching the container
to privileged.

---

## RAID is not a backup

The NAS runs two 6 TB disks in RAID 1. That protects against exactly one thing:
**one disk failing.**

It does not protect against:

| Event | What RAID 1 does |
|---|---|
| you delete the wrong directory | mirrors the deletion, instantly, to both disks |
| ransomware encrypts the share | mirrors the encryption |
| the controller writes garbage | mirrors the garbage |
| a filesystem bug corrupts data | mirrors the corruption |
| fire, theft, flood, power surge | nothing |
| both disks fail (same batch, same age, same load) | nothing |

RAID is an **availability** mechanism. It keeps a service running through a disk
failure. Backup is a **recovery** mechanism. They solve different problems and
one does not substitute for the other.

The rule is **3-2-1**: three copies, on two different media, one offsite. This
lab currently has copies on the guests and copies on the NAS. It has **no
offsite copy**, which is written down as a known limitation in the README rather
than quietly omitted.

---

## Where the disk went

In order of how often each is the answer.

```bash
# 1. the obvious
df -h
du -xh --max-depth=1 / | sort -h | tail -20

# 2. Docker, which is usually the answer
docker system df
docker system df -v            # per image, per volume, per container

# 3. logs
journalctl --disk-usage
journalctl --vacuum-size=200M
du -sh /var/log/*

# 4. the thin pool, which df will not tell you
lvs -o +data_percent,metadata_percent

# 5. old backups
pvesm list local | grep vzdump

# 6. deleted files still held open by a running process
lsof +L1
```

Number 6 is the one that looks like magic: `du` says 20 GB, `df` says 80 GB
used. A process has a deleted file open, so the space is not reclaimed until the
process is restarted. Rotated logs and a service that was not signalled are the
usual cause.

---

**Next:** [Backup and recovery](07-backup-and-recovery.md) — including the part
where you actually restore something.
