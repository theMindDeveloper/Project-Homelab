# Proxmox VE cheat sheet

Commands I actually use, grouped by what I am trying to do rather than by tool.
Run everything as root on the node unless stated otherwise.

---

## Where am I

```bash
pveversion -v                  # Proxmox and kernel versions
hostname                       # which node am I on
pvecm status                   # cluster status, quorum, node list
pvecm nodes                    # nodes and their IDs
```

`pvecm status` is the first thing to check when the web UI shows grey question
marks on guests. Grey usually means "quorum lost", not "guest dead".

---

## Listing things

```bash
qm list                        # VMs on THIS node
pct list                       # LXC containers on THIS node
pvesh get /cluster/resources --type vm   # every guest on the WHOLE cluster
```

`qm` and `pct` are node-local. On a cluster, `pvesh get /cluster/resources` is
the only command that gives you the full picture from any node.

---

## Entering a guest

```bash
pct enter 102                  # shell inside LXC 102, no SSH needed
pct exec 102 -- df -h          # run one command inside an LXC

qm terminal 100                # serial console of VM 100 (needs serial0 configured)
qm monitor 100                 # QEMU monitor
```

`pct enter` is the fastest way in and works even when the container's network is
broken. There is no `qm enter`: a VM is a black box from the host's perspective,
which is one of the practical differences between the two.

---

## Start, stop, reboot

```bash
pct start 102 ; pct shutdown 102 ; pct stop 102     # stop = hard kill
qm  start 100 ; qm  shutdown 100 ; qm  stop 100

pct reboot 102
qm reset 100                   # hard reset, like the reset button
```

Prefer `shutdown` over `stop`. `stop` is a power cut and can corrupt a database
mid-write.

---

## Creating an LXC container

```bash
# 1. get a template
pveam update
pveam available --section system | grep debian
pveam download local debian-12-standard_12.7-1_amd64.tar.zst

# 2. create
pct create 110 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
  --hostname   svc-example \
  --cores      2 \
  --memory     2048 \
  --swap       512 \
  --rootfs     local-lvm:16 \
  --net0       name=eth0,bridge=vmbr0,ip=192.168.178.90/24,gw=192.168.178.1 \
  --nameserver 192.168.178.178 \
  --onboot     1 \
  --unprivileged 1 \
  --features   nesting=1

pct start 110
pct enter 110
```

Two flags worth understanding rather than copying:

`--unprivileged 1` maps container root to an unprivileged UID on the host, so a
root escape inside the container is not root on the host. Use it unless you have
a concrete reason not to.

`--features nesting=1` is required if you want to run Docker inside the
container. Without it the Docker daemon will not start.

---

## Creating a VM

```bash
qm create 120 \
  --name        vm-example \
  --memory      4096 \
  --cores       4 \
  --cpu         host \
  --net0        virtio,bridge=vmbr0 \
  --scsihw      virtio-scsi-single \
  --scsi0       local-lvm:32,discard=on,ssd=1 \
  --ide2        local:iso/debian-12.iso,media=cdrom \
  --boot        order='scsi0;ide2' \
  --ostype      l26 \
  --agent       enabled=1 \
  --onboot      1

qm start 120
```

`--agent enabled=1` requires `qemu-guest-agent` installed inside the VM. Without
it, Proxmox cannot see the guest's IP address and a graceful shutdown will time
out and turn into a hard stop.

### Cloud-init template, the faster route

```bash
# download a cloud image once
wget https://cloud.debian.org/images/cloud/bookworm/latest/debian-12-genericcloud-amd64.qcow2

qm create 9000 --name debian12-tmpl --memory 2048 --cores 2 \
  --net0 virtio,bridge=vmbr0 --scsihw virtio-scsi-single --ostype l26
qm importdisk 9000 debian-12-genericcloud-amd64.qcow2 local-lvm
qm set 9000 --scsi0 local-lvm:vm-9000-disk-0 --boot order=scsi0
qm set 9000 --ide2 local-lvm:cloudinit --serial0 socket --vga serial0
qm set 9000 --agent enabled=1
qm template 9000

# then clone in seconds
qm clone 9000 121 --name web-01 --full
qm set 121 --ipconfig0 ip=192.168.178.91/24,gw=192.168.178.1 \
            --ciuser admin --sshkeys ~/.ssh/authorized_keys
qm start 121
```

This is the difference between installing an OS for twenty minutes and having a
running VM in ten seconds. If you build one thing from this page, build this.

---

## Resizing

```bash
pct set 102 --memory 4096 --cores 4      # LXC, live for memory
pct resize 102 rootfs +8G                # grow disk, online, cannot shrink

qm set 100 --memory 8192                 # VM, needs a reboot unless ballooning
qm resize 100 scsi0 +20G                 # grow, then extend the filesystem
                                         # INSIDE the guest afterwards
```

Growing a VM disk in Proxmox only grows the block device. The partition and
filesystem inside still have to be extended with `growpart` and `resize2fs`.

---

## Snapshots

```bash
pct snapshot 102 before-upgrade
pct listsnapshot 102
pct rollback 102 before-upgrade
pct delsnapshot 102 before-upgrade

qm snapshot 100 before-upgrade --vmstate 1     # --vmstate also saves RAM
qm rollback 100 before-upgrade
```

Take a snapshot before every upgrade. Delete it afterwards: snapshots on
thin-provisioned storage grow as the guest writes, and a forgotten snapshot is a
classic way to fill a disk.

---

## Backup and restore

```bash
# back up one guest, compressed, to the storage named "backup"
vzdump 102 --storage backup --mode snapshot --compress zstd

# back up everything except two guests
vzdump --all --exclude 105,106 --storage backup --mode snapshot --compress zstd

# restore
pct restore 112 /var/lib/vz/dump/vzdump-lxc-102-*.tar.zst --storage local-lvm
qm  restore 122 /var/lib/vz/dump/vzdump-qemu-100-*.vma.zst --storage local-lvm
```

Backup modes:

| Mode | Downtime | Consistency |
|---|---|---|
| `snapshot` | none | good, uses storage snapshots |
| `suspend` | short freeze | good |
| `stop` | full stop | perfect |

**A backup you have never restored is not a backup.** Restore one guest to a
spare ID once a quarter and boot it.

---

## Cluster and migration

```bash
pvecm create HomelabCluster              # on the first node
pvecm add 192.168.178.20                 # on every additional node

qm  migrate 100 pve2 --online            # live migration, VM keeps running
pct migrate 102 pve2 --restart           # LXC: needs a restart, no live migration
```

LXC containers cannot be live-migrated. They are processes on the host kernel,
and you cannot move a running process between kernels. This is the second
practical difference between containers and VMs.

---

## Storage

```bash
pvesm status                             # all storages, size, used, available
pvesm list local                         # contents of one storage
zpool status                             # ZFS pool health
zpool list
zfs list -o name,used,avail,refer
```

`zpool status` belongs in your weekly routine. A degraded mirror still works
perfectly and gives no visible symptom until the second disk dies.

---

## Templates and cloning

```bash
pct template 110                         # turn container into a template
pct clone 110 111 --hostname svc-two     # linked clone, fast, shares base
pct clone 110 112 --hostname svc-two --full   # full clone, independent
```

---

## Users, permissions, API

```bash
pveum user add deploy@pve --password ...
pveum role add Deployer --privs "VM.Allocate VM.Config.Disk VM.PowerMgmt"
pveum acl modify / --users deploy@pve --roles Deployer
pveum user token add deploy@pve automation --privsep 0
```

API tokens instead of passwords for anything automated. `--privsep 0` gives the
token the user's full rights; leave it at `1` and grant explicitly if you want
to be strict.

---

## Logs and troubleshooting

```bash
journalctl -u pve-cluster -f             # cluster filesystem
journalctl -u pvedaemon  -f              # API daemon
journalctl -u pveproxy   -f              # web UI
tail -f /var/log/pve/tasks/active        # currently running tasks

pct config 102                           # full config of a container
qm config 100
cat /etc/pve/lxc/102.conf                # the same, as a file
```

`/etc/pve` is a **cluster filesystem**. It is synchronised across all nodes
automatically, so editing a config there on any node changes it everywhere. It
is also only writable while the node has quorum, which is why a broken cluster
feels like a read-only filesystem.

---

## Things that will bite you

**The enterprise repository.** A fresh install without a subscription cannot
update, because the enterprise repo returns 401. Switch to the no-subscription
repository or `apt update` fails forever.

**Turning off swap in an LXC.** Containers share the host kernel and therefore
the host's memory pressure. Setting swap to 0 on a container that occasionally
spikes gets it OOM-killed rather than slowed down.

**Snapshots on `local` (directory storage).** Directory storage does not support
snapshots for VMs unless the disk is qcow2. If the snapshot button is greyed out,
that is why.

**Passing hardware into an unprivileged LXC.** GPU or USB passthrough into an
unprivileged container needs explicit `lxc.cgroup2.devices.allow` and
`lxc.mount.entry` lines plus matching group IDs. It is doable and it is fiddly.
A VM is the simpler answer if you only need it once.

**Deleting a node from the cluster.** `pvecm delnode` is not reversible and the
removed node must never rejoin with the same name without a full reinstall.
