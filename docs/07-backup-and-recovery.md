# Backup and recovery

The strategy, the commands, the modes and their trade-offs, and the part
everyone skips: verifying that a restore actually works.

---

## The rule

**A backup you have never restored is not a backup. It is a hope with a
filename.**

Everything below exists to support that one sentence. The commands are easy. The
discipline of testing a restore on a schedule is the entire value.

---

## 3-2-1

| | Meaning | This lab |
|---|---|---|
| **3** copies | the live data plus two more | live guests + `vzdump` archives + NAS |
| **2** media | two different failure domains | node disks + NAS array |
| **1** offsite | one copy that a fire cannot reach | **missing** |

The missing offsite copy is written into the README's known limitations on
purpose. A homelab documentation repository that claims a complete 3-2-1
strategy while running two disks in one room is not documentation, it is
marketing.

---

## What actually needs backing up

Not everything. Deciding this is most of the work.

| Data | Recoverable without a backup? | Priority |
|---|---|---|
| **Vaultwarden vault** | never | critical |
| **Immich photo library** | never | critical |
| **Nextcloud user data** | never | critical |
| **Proxmox `/etc/pve`** | rebuildable, slowly, from memory | high |
| **Container configs and compose files** | in this git repository | low |
| **Databases** (Pterodactyl, Nextcloud, Immich) | no | high |
| **Media library** | re-obtainable, at cost | medium |
| **Docker images** | `docker pull` | none |
| **OS filesystems** | rebuild from the runbooks | low |

**That last row is why runbooks are a backup strategy.** A container whose
rebuild is documented step by step does not need a full image backup; it needs
its data backed up and its recipe written down. That is what
[`runbooks/`](../runbooks/) is.

---

## `vzdump`

Proxmox's built-in backup. One archive per guest, restorable to any node.

```bash
# one guest
vzdump 102 --storage backup --mode snapshot --compress zstd

# everything, minus the noisy ones
vzdump --all --exclude 105,106 --storage backup --mode snapshot --compress zstd

# with retention
vzdump --all --storage backup --mode snapshot --compress zstd \
       --prune-backups keep-last=7,keep-weekly=4,keep-monthly=6
```

The wrapper used here, with a readable summary and free-space report, is
[`scripts/backup-all.sh`](../scripts/backup-all.sh).

### Modes

| Mode | Downtime | Consistency | Requires |
|---|---|---|---|
| `snapshot` | none | **crash consistent** | storage that supports snapshots |
| `suspend` | a short freeze | better | anything |
| `stop` | full stop | perfect | acceptance of downtime |

**"Crash consistent" is the phrase to understand.** A snapshot backup captures
the guest exactly as it was at an instant, without telling it anything happened.
That is identical to yanking the power cable at that instant. A journalling
filesystem replays its journal on boot and is fine. A database replays its
write-ahead log and is usually fine. An application that keeps state in memory
and writes it out lazily is not fine.

For anything where "usually fine" is not good enough, dump the database *before*
the snapshot runs:

```bash
# inside the guest, before the backup window
pg_dump -U nextcloud nextcloud | zstd > /srv/dumps/nextcloud-$(date +%F).sql.zst
mysqldump --single-transaction --all-databases | zstd > /srv/dumps/all-$(date +%F).sql.zst
```

Now the snapshot contains a consistent dump *and* a crash-consistent database,
and you can choose which to restore from.

### Compression

| Option | Speed | Ratio |
|---|---|---|
| `zstd` | fast, multithreaded | good |
| `lzo` | fastest | poor |
| `gzip` | slow | good |
| none | fastest | none |

`zstd` is the right default and has been since Proxmox 6.2.

---

## Restoring

```bash
# list what you have
pvesm list backup
ls -lh /var/lib/vz/dump/

# restore to a NEW id, so the original is untouched
pct restore 199 /var/lib/vz/dump/vzdump-lxc-102-2026_08_11-03_15_01.tar.zst \
    --storage local-lvm

qm restore 199 /var/lib/vz/dump/vzdump-qemu-100-2026_08_11-03_15_01.vma.zst \
    --storage local-lvm

# overwrite the existing guest, when you are sure
pct restore 102 <archive> --storage local-lvm --force
```

**Always restore to a new ID first.** `--force` overwrites the running guest,
which turns a test into an outage if the archive turns out to be bad.

After restoring to a new ID, the clone has the **same IP address** as the
original. Two hosts with one address is its own kind of bad day. Either restore
with the network disabled, or change it before starting:

```bash
pct restore 199 <archive> --storage local-lvm --start 0
pct set 199 --net0 name=eth0,bridge=vmbr0,ip=192.168.178.199/24,gw=192.168.178.1
pct start 199
```

### Pulling a single file out of an archive

The whole guest does not need restoring to recover one file:

```bash
# LXC archives are plain tar
tar --zstd -tvf vzdump-lxc-102-*.tar.zst | grep nginx.conf
tar --zstd -xvf vzdump-lxc-102-*.tar.zst ./etc/nginx/nginx.conf

# VM archives need extracting first
vma extract vzdump-qemu-100-*.vma.zst /tmp/restore/
```

---

## Backing up the cluster configuration

`/etc/pve` is a synchronised cluster filesystem holding every guest config,
every user, every ACL and the storage definitions. `vzdump` does **not** back it
up, because it backs up guests, not the host.

```bash
# on each node, monthly, or after any change
tar czf /root/pve-config-$(hostname)-$(date +%F).tar.gz \
    /etc/pve /etc/network/interfaces /etc/hosts /etc/hostname \
    /etc/pve/corosync.conf 2>/dev/null

# corosync authentication key - needed to rejoin a cluster
cp /etc/corosync/authkey /root/corosync-authkey-$(date +%F)
```

Copy those off the node. A node whose disk died takes its `/etc/pve` copy with
it, and the surviving nodes have the cluster-wide parts but not that node's
local network configuration.

---

## Docker volumes

`vzdump` on the LXC captures the Docker volumes too, because they are files
inside the container. That is usually enough. When you want a volume on its own,
portable and restorable anywhere:

```bash
# back up a named volume to a tarball
docker run --rm \
  -v vaultwarden_data:/data:ro \
  -v "$PWD":/backup \
  alpine tar czf /backup/vaultwarden-$(date +%F).tar.gz -C /data .

# restore it
docker run --rm \
  -v vaultwarden_data:/data \
  -v "$PWD":/backup \
  alpine sh -c "cd /data && tar xzf /backup/vaultwarden-2026-08-11.tar.gz"
```

The pattern is always the same: a throwaway container that mounts the volume and
a directory of yours, and tars between them.

**Stop the service first for anything with a database.** Vaultwarden holds an
SQLite file open; tarring it while it is being written produces an archive that
restores into a corrupt database.

---

## Schedule

| What | When | How |
|---|---|---|
| all guests, `vzdump` snapshot | nightly 03:15 | `scripts/backup-all.sh` via cron |
| retention prune | with each run | `--prune-backups keep-last=7` |
| `/etc/pve` config tar | monthly | manual, per node |
| Vaultwarden volume export | weekly | manual |
| **restore drill** | **quarterly** | [`runbooks/09-backup-restore-drill.md`](../runbooks/09-backup-restore-drill.md) |

```cron
15 3 * * * /root/backup-all.sh --storage backup >> /var/log/backup.log 2>&1
```

---

## The restore drill

Once a quarter, and after any change to the backup configuration:

1. Pick a guest. Rotate through them; do not always pick the easy one.
2. Restore it to a spare ID with networking disabled.
3. Start it.
4. Log in. Open the application. Look at real data.
5. Write down how long the whole thing took.
6. Destroy the restored guest.

Step 4 is the one that matters. A guest that boots is not a guest that works: a
database can start with an empty schema, an application can start with its
configuration missing. "It booted" has fooled people into trusting broken
backups for years.

Step 5 is the one people skip and then regret. **Recovery time is a number you
should know before you need it**, because it is the number someone will ask for
when a service is down.

The full procedure is
[`runbooks/09-backup-restore-drill.md`](../runbooks/09-backup-restore-drill.md).

---

## What is not covered

Stated plainly, because a backup page that only lists strengths is not useful.

- **No offsite copy.** Fire, theft or a flood takes everything.
- **No automated restore verification.** The drill is manual and quarterly.
  Proxmox Backup Server would give verify jobs, deduplication and incremental
  backups; it needs a host to run on.
- **No encryption at rest** on the backup target. The archives sit on the NAS in
  the clear. If the NAS leaves the building, so does the Vaultwarden database.
- **The NAS backs up nothing to anywhere.** It is the target, not a source.

Each of these is a decision with a cost, not an oversight, and they are in the
README's limitations list so they stay visible.

---

**Next:** [Monitoring](08-monitoring.md) — knowing something broke before a
restore becomes necessary.
