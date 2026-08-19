# Runbook 19 · Nextcloud storage on the UGREEN NAS (NFS)

> **Status: written, not yet deployed.** Companion to
> [Runbook 07](07-nextcloud.md), which assumed local storage on P2. This one
> changes two decisions: Nextcloud runs in **LXC 102 "docker" on P1**, and user
> files live on the **UGREEN DH4300 Plus** over NFS instead of on a local disk.

**Goal** A Nextcloud data directory that is physically on the NAS RAID 1 pair,
reachable from an unprivileged LXC, with the right ownership, and that does not
quietly fall back to the container's own root filesystem.

**Time** 45 minutes for the storage part, plus Runbook 07 for the app itself.
**Prerequisites** Drives installed in the NAS and a storage pool created. As of
the last inventory update the drives were **removed**, so this is step 0, not an
assumption.
**Reverses cleanly?** Yes. Unmount, remove the fstab line, `pct set 102
--delete mp0`. Nothing is written to the NAS that a delete does not remove.

---

## The problem, stated once

Three facts collide:

1. Nextcloud's data directory must behave like a local POSIX filesystem. It
   needs ownership, permissions, and locking to work.
2. LXC 102 is **unprivileged**. Its Docker daemon cannot call `mount(2)` for an
   NFS filesystem, so `driver: local, type: nfs` in a compose file fails with
   "operation not permitted" and the container never starts.
3. An unprivileged LXC shifts every UID by 100000. Container root is host
   100000; the `www-data` user Nextcloud runs as, UID 33, is host **100033**.
   The NAS sees that number over the wire, and it means nothing to UGOS.

The resolution is the same for all three: mount NFS **on the Proxmox host**,
fix the ownership **on the Proxmox host** in host-side numbers, then hand the
directory to the container as a plain bind mount. From inside the container it
looks like an ordinary folder owned by `www-data`, because that is exactly what
it is.

```
UGREEN DH4300 Plus                P1 (pve, 192.168.178.20)              LXC 102
192.168.178.49                    ────────────────────────              ───────
/volume1/nextcloud   ──NFSv4.1──▶ /mnt/nas-nextcloud  ──bind──▶ /srv/nextcloud/data
  owner: whatever                   chown 100033:100033            appears as 33:33
                                                                          │
                                                                    docker bind mount
                                                                          ▼
                                                              /var/www/html/data
```

---

## 0 · Put the drives back in

The 2 x 6 TB RAID 1 pair is the point of this exercise. Until it exists there is
nothing to mount.

UGOS Pro → **Storage Manager** → create the storage pool → create the volume.
Confirm the volume path is `/volume1`. If UGOS named it something else, every
path in this runbook changes with it.

**RAID 1 is not a backup.** It survives one dead disk. It does not survive a
deleted folder, a ransomware run, or the NAS itself. Nextcloud will be the
primary copy of files that exist nowhere else, which makes the offsite backup
item in the inventory's `planned:` list considerably less optional than it was.

---

## 1 · Create the share on the NAS

UGOS Pro → **Control Panel → Shared Folder → Create**

| Field | Value |
|---|---|
| Name | `nextcloud` |
| Location | the RAID 1 volume |
| Description | Nextcloud user data, do not touch from SMB |
| Encryption | off |
| Recycle bin | **off** |

Two of those are deliberate.

**Recycle bin off.** Nextcloud has its own trash, with its own retention
policy and its own quota accounting. A second, invisible one underneath it
means deleted files still occupy the volume and Nextcloud's free-space figure
is a lie.

**Do not touch it from SMB.** Nextcloud maintains a database index of every
file. A file dropped into this share over SMB does not exist as far as
Nextcloud is concerned until an `occ files:scan` runs, and a file *deleted*
that way leaves a database row pointing at nothing. If you want NAS folders
visible in Nextcloud, that is what the External Storage app is for, and it is
a different mechanism from the data directory. See step 8.

---

## 2 · Enable NFS and export the share

UGOS Pro → **Control Panel → File Services → NFS** → enable. NFSv4.1 or later.

Then on the `nextcloud` shared folder → **NFS Permissions → Add**:

| Field | Value | Why |
|---|---|---|
| Client IP / hostname | `192.168.178.20` | P1 only. Not the LXC's address: the mount is made by the host kernel, so the host is the NFS client. Not a wildcard, and not the whole subnet. |
| Privilege | Read/Write | |
| Squash | **No mapping** (`no_root_squash`) | The host must be able to `chown` the export to UID 100033. Root squash rewrites that request to `nobody` and the chown silently does nothing. |
| Security | `sys` | Kerberos is the only real alternative and it needs a KDC. |
| Async | off if offered | Async lets the NAS acknowledge writes before they hit disk. Faster, and it loses acknowledged writes on a power cut. |
| Allow non-privileged port | off | |

**`no_root_squash` is a real trust decision**, so state it plainly: root on P1
becomes root on that export. It is scoped to one client address and one folder,
and P1 is a machine you already trust completely, which is what makes it
acceptable here. It would not be acceptable exported to the whole LAN.

Note the exact export path UGOS shows you. It is usually `/volume1/nextcloud`.

---

## 3 · Mount it on P1

```bash
# on P1 (pve), as root
apt update && apt install -y nfs-common

# does the export exist and is this host allowed?
showmount -e 192.168.178.49
```

If that returns nothing, the export rule is wrong or NFS is not running. Fix it
before continuing; every later step depends on it.

```bash
mkdir -p /mnt/nas-nextcloud

cat >> /etc/fstab <<'EOF'
# Nextcloud user data - UGREEN DH4300 Plus, RAID 1 volume
192.168.178.49:/volume1/nextcloud  /mnt/nas-nextcloud  nfs4  rw,hard,noatime,nodiratime,nconnect=4,_netdev,x-systemd.automount,x-systemd.mount-timeout=30  0  0
EOF

systemctl daemon-reload
mount -a
mountpoint /mnt/nas-nextcloud     # must say "is a mountpoint"
```

The options are not decoration:

- **`hard`** - on an NFS timeout, block and retry forever instead of returning
  an I/O error. `soft` turns a NAS reboot into a stream of failed writes, and
  Nextcloud will happily record a half-written file as complete. The cost of
  `hard` is that if the NAS goes away, PHP processes hang rather than erroring,
  and the web UI stops responding. That is the correct failure: visible.
- **`_netdev` + `x-systemd.automount`** - do not block boot on a NAS that is not
  up yet, and mount on first access instead. Without this, P1 waits on the
  network mount at every boot.
- **`nconnect=4`** - four TCP connections instead of one. The DH4300 Plus has a
  2.5 GbE port and an ARM CPU; parallel connections is where the throughput is.
  Drop it if the kernel refuses the option.
- **`noatime,nodiratime`** - no write to the NAS every time Nextcloud reads a
  file.

---

## 4 · Fix the ownership, in host numbers

This is the step that everything else depends on, and the one with no obvious
error message when it is skipped.

```bash
# on P1, still as root
chown -R 100033:100033 /mnt/nas-nextcloud
chmod 770 /mnt/nas-nextcloud

stat -c '%u:%g %a' /mnt/nas-nextcloud    # expect: 100033:100033 770
```

100033 is 100000 (the unprivileged container's UID offset) + 33 (`www-data`).
Inside LXC 102 the same directory reports `33:33`, which is what Nextcloud
requires. `770` rather than `755` because Nextcloud's own security check warns
about a data directory that other users can read.

If `stat` still shows the old owner, the export is squashing root. Go back to
step 2 and set Squash to "No mapping".

---

## 5 · Pass it into LXC 102

```bash
# on P1, as root@pam. mp0 may already be in use - check first.
pct config 102 | grep -E '^mp[0-9]'

pct set 102 --mp0 /mnt/nas-nextcloud,mp=/srv/nextcloud/data
```

No `size=` on a bind mount: the container gets whatever the underlying
filesystem has, and quota is set inside Nextcloud instead.

**This is a restart, and LXC 102 is not a quiet container.** Vaultwarden,
Grafana, Prometheus, Glance, n8n, Apache and the Cloudflare tunnel all live
there and all go down with it. Pick the moment.

```bash
pct reboot 102
```

**Backups change too.** `vzdump` does not follow bind mounts, so the Proxmox
backup of LXC 102 now contains the application and the database but **not** a
single user file. That is not a bug to work around, it is the reason the split
exists: files are backed up from the NAS side, on the NAS's schedule. It does
mean the restore drill in [Runbook 09](09-backup-restore-drill.md) needs a
second half.

---

## 6 · Verify from inside, before Nextcloud exists

Cheap now, expensive later.

```bash
pct enter 102

mountpoint -q /srv/nextcloud/data && echo "mounted"
stat -c '%u:%g %a' /srv/nextcloud/data          # expect: 33:33 770
df -h /srv/nextcloud/data                       # expect the NAS volume size

# can UID 33 actually write? this is the question that matters.
runuser -u '#33' -g '#33' -- touch /srv/nextcloud/data/.write-test \
  && echo "write OK" && rm /srv/nextcloud/data/.write-test
```

All four must pass. If `df` shows the LXC's own 8 GB rootfs, the bind mount did
not apply and starting Nextcloud now would fill the container's disk with user
files.

---

## 7 · Deploy the stack

Per [Runbook 07](07-nextcloud.md), with the files from
[`compose/nextcloud/`](../compose/nextcloud/):

```bash
mkdir -p /opt/nextcloud && cd /opt/nextcloud
# copy in docker-compose.example.yml and .env.example

cp docker-compose.example.yml docker-compose.yml
cp .env.example .env
$EDITOR .env                  # NEXTCLOUD_DATA_DIR=/srv/nextcloud/data
chmod 600 .env

docker compose config         # renders variables, fails loudly on a typo
docker compose up -d
docker compose logs -f app    # wait for "Initializing finished"
```

In Portainer 1, add it as a Stack instead if you prefer the UI. Same file.

Then confirm Nextcloud actually landed on the NAS:

```bash
ls -la /srv/nextcloud/data     # .ocdata, appdata_*, and the admin user's folder
```

If that directory is empty and the files are somewhere else, stop and fix it
before anyone uploads anything.

---

## 8 · The other way to use the NAS, and when to want it

The data directory is Nextcloud's own storage: it owns those files, indexes
them, and nothing else should write there. That is what steps 1 to 7 set up.

**External Storage** is the other mechanism. It mounts a folder the NAS already
owns, `/volume1/media` or `/volume1/photos`, and shows it inside Nextcloud
alongside the user's own files.

```bash
alias occ='docker compose exec -u www-data app php occ'
occ app:enable files_external
```

Then add a **Local** external storage pointing at a second bind mount, set up
exactly like steps 3 to 5 but with a different share, and mark it read-only.

Use it when the NAS is the source of truth for those files and something else,
Jellyfin, Immich, Syncthing, is already managing them. Do not use it for files
you want Nextcloud to sync and version. The two mechanisms answer different
questions and mixing them up is the most common way to end up with a duplicated
photo library.

---

## 9 · Reverse proxy

Unchanged from [Runbook 07 step 4](07-nextcloud.md), except the target address:

| Field | Value |
|---|---|
| Domain Names | `cloud.theminddev.com` |
| Scheme | `http` |
| Forward Hostname / IP | `192.168.178.87` |
| Forward Port | `8082` |
| Websockets Support | on |
| SSL | wildcard, Force SSL, HTTP/2, HSTS |

Advanced config, all four required:

```nginx
client_max_body_size 0;
proxy_request_buffering off;
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;

location = /.well-known/carddav { return 301 $scheme://$host/remote.php/dav; }
location = /.well-known/caldav  { return 301 $scheme://$host/remote.php/dav; }
```

The DNS record is already handled: the Cloudflare wildcard A record points at
the LAN, and AdGuard resolves `*.theminddev.com` internally.

---

## 10 · Post-install, the NFS-specific parts

The full list is in [Runbook 07 step 5](07-nextcloud.md). Three items matter
more than usual once the data directory is on a network filesystem.

```bash
alias occ='docker compose exec -u www-data app php occ'

# Redis file locking. Non-negotiable here: NFS advisory locks across a network
# are exactly the thing that goes wrong, and this moves locking off the
# filesystem entirely. The compose file wires Redis up; confirm it took.
occ config:system:get memcache.locking          # \OC\Memcache\Redis

# Do not stat every file on every page load looking for outside changes.
# Over NFS that is thousands of round trips. Nothing writes to this directory
# except Nextcloud, so there are no outside changes to find.
occ config:system:set filesystem_check_changes --value 0 --type integer

# Chunked uploads assemble in the data directory. 10 MB chunks over 2.5 GbE is
# a reasonable default; the 16 GB PHP limit in the compose file is the ceiling.
occ config:app:set files max_chunk_size --value 10485760
```

Then the indices and the scan job from Runbook 07, in that order.

---

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `driver_opts type=nfs` volume fails, "operation not permitted" | Docker inside an unprivileged LXC cannot mount NFS | This runbook. Mount on the host. |
| Data directory owned by `nobody` inside the container | Root squash on the export | Step 2, Squash = No mapping, then redo step 4 |
| "Your data directory is not writable" | Ownership is not 33:33 inside the container | Step 4, in host numbers, not container numbers |
| `df` shows 8 GB, not the NAS | Bind mount did not apply | `pct config 102`, then reboot the container |
| Web UI hangs, no error | NAS is down and the mount is `hard` | Correct behaviour. Bring the NAS back. |
| "Access through untrusted domain" | `NEXTCLOUD_TRUSTED_DOMAINS` | Host only, no scheme, no trailing slash |
| Redirect loop at login | `OVERWRITEPROTOCOL` | Must be `https`, since NPM terminates TLS |
| Every log line shows 192.168.178.178 | `TRUSTED_PROXIES` unset, or Apache is rewriting too | Set it to the Pi, and `APACHE_DISABLE_REWRITE_IP=1` |
| Uploads fail at ~1 MB | NPM `client_max_body_size` | Step 9 |
| Files on the NAS not visible in Nextcloud | Written outside Nextcloud | `occ files:scan --all`, and read step 8 |

---

## What this does not solve

- **The NAS is now a single point of failure for a service on P1.** Nextcloud
  is up only when the NAS is up. That is the trade for putting the files on the
  redundant disks.
- **No backup of the user data exists yet.** RAID 1 is not one, and `vzdump`
  does not see the bind mount. Until the offsite target in the inventory's
  `planned:` list exists, this stack has exactly one copy of every file in it.
- **LXC 102 now carries eleven services.** The next one should probably go
  somewhere else.
