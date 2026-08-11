# Runbook 01 · Create an LXC container

**Goal** A new unprivileged Debian 12 container on P1, with a static address,
ready for a service.

**Time** 3 minutes.
**Prerequisites** root on a Proxmox node. A free container ID. A free IP.
**Reverses cleanly?** Yes — `pct destroy <id>` removes everything.

Everything in this cluster is an LXC container. The reasoning is in
[`docs/04-lxc-vs-vm.md`](../docs/04-lxc-vs-vm.md); this is the procedure.

---

## 0 · Decide, before you type anything

| Decision | This example | Why it matters |
|---|---|---|
| Container ID | `110` | must be unique **cluster-wide**, not just per node |
| Hostname | `svc-example` | function, never a person or a place |
| IP address | `192.168.178.90` | must be free, and outside the DHCP pool |
| Node | `pve` (P1) | with local storage, the guest lives where you create it |
| Resources | 2 cores, 2 GB, 16 GB disk | LXC uses only what it needs; over-allocating cores is free |

**Check both are actually free.** Two minutes here saves an hour of
"why is the network flapping".

```bash
# is the ID used anywhere in the cluster
pvesh get /cluster/resources --type vm --output-format json | grep -o '"vmid":[0-9]*'

# is the address answering
ping -c2 192.168.178.90        # you want "Destination Host Unreachable"
arping -c3 -I vmbr0 192.168.178.90
```

`ping` alone is not conclusive; a host that ignores ICMP will answer `arping`.

---

## 1 · Get a template

Templates are OS root filesystems, downloaded once and reused.

```bash
pveam update
pveam available --section system | grep debian
pveam download local debian-12-standard_12.7-1_amd64.tar.zst
pveam list local
```

The template goes on `local`, which is directory storage. Guest disks go on
`local-lvm`, which is LVM-thin. Different storages for different jobs; the
difference is explained in [`docs/06-storage.md`](../docs/06-storage.md).

---

## 2 · Create it

```bash
pct create 110 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
  --hostname     svc-example \
  --cores        2 \
  --memory       2048 \
  --swap         512 \
  --rootfs       local-lvm:16 \
  --net0         name=eth0,bridge=vmbr0,ip=192.168.178.90/24,gw=192.168.178.1 \
  --nameserver   192.168.178.178 \
  --onboot       1 \
  --unprivileged 1 \
  --features     nesting=1 \
  --start        0
```

The same thing, with the free-address check built in:

```bash
./scripts/new-lxc.sh --id 110 --name svc-example --ip 192.168.178.90
```

### The flags that are decisions, not boilerplate

**`--unprivileged 1`**
Container root maps to UID 100000 on the host. Root inside is nobody outside. Use
it unless you have a concrete, written-down reason not to. **You cannot change
this later** — converting means backup, restore into a new container.

**`--features nesting=1`**
Permits a container runtime *inside* the container. Required for Docker. Without
it the daemon starts and dies with a cgroup error that reads like a kernel bug.
Add `keyctl=1` as well if the container will run Docker in anger.

**`--onboot 1`**
Starts with the host. The container that works perfectly until the node reboots
is the container that was missing this.

**`--nameserver 192.168.178.178`**
AdGuard Home. Without it the container inherits the host's resolver and skips
LAN-wide filtering and internal name resolution.

**`--swap 512`**
Not zero. A container with swap 0 that spikes gets OOM-killed rather than
slowed. Containers share the host's memory pressure; give them somewhere to go.

**`--rootfs local-lvm:16`**
16 GB. Growing later is `pct resize 110 rootfs +8G`, online, one command.
**Shrinking is not possible.** Start small.

---

## 3 · Start and enter

```bash
pct start 110
pct enter 110          # a shell inside, no SSH, no network needed
```

`pct enter` works even when the container's networking is completely broken,
because it is not using the network. There is no `qm enter` for VMs; a VM is
opaque to the host because it runs its own kernel. That is one of the practical
differences between the two.

---

## 4 · First-boot setup, inside the container

```bash
apt update && apt upgrade -y
apt install -y --no-install-recommends \
    curl ca-certificates gnupg htop vim git

timedatectl set-timezone Europe/Berlin

# a non-root user, for anything that should not run as root
adduser admin
usermod -aG sudo admin
```

### Verify the basics before building anything on top

```bash
ip a                          # the address you asked for is on eth0
ip r                          # default via 192.168.178.1
cat /etc/resolv.conf          # nameserver 192.168.178.178
ping -c2 192.168.178.1        # gateway
getent hosts github.com       # DNS resolution works
timedatectl                   # clock is right - TLS depends on it
```

Five commands. Doing them now means that when the service you install next does
not work, you already know the network is not the reason.

---

## 5 · Record it

```bash
exit
pct config 110
```

Add the container to [`inventory/inventory.yml`](../inventory/inventory.yml):

```yaml
  - vmid: 110
    name: svc-example
    node: pve
    type: lxc
    address: 192.168.178.90
    unprivileged: true
    features: nesting=1
    purpose: what this container is for
```

The inventory is the source of truth. **A container that is not in it does not
officially exist**, which means nothing checks it, nothing monitors it, and
nobody remembers what it was for.

---

## Snapshot before you change it

```bash
pct snapshot 110 clean-install
```

One second, and it turns "I broke it" into "I rolled it back". Delete it once
the service is working:

```bash
pct listsnapshot 110
pct delsnapshot 110 clean-install
```

**Delete it.** A snapshot on thin-provisioned storage grows as the guest writes,
and a forgotten one is a classic way to fill a pool.
See [`docs/06-storage.md`](../docs/06-storage.md).

---

## Undo

```bash
pct stop 110
pct destroy 110              # removes the config and the disk
```

---

## If it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| `pct start` says "exited with status 1" | not enough information | `lxc-start -n 110 -F -l DEBUG` gives the real error |
| container starts, no network | address in use, or wrong bridge | `pct set 110 --net0 name=eth0,bridge=vmbr0,ip=...` |
| `CT 110 already exists` | ID used on another node | `pvesh get /cluster/resources --type vm` |
| "cannot lock file - got timeout" | an interrupted earlier operation | `pct unlock 110` |
| storage full | the thin pool, which `df` does not show | `lvs -o +data_percent,metadata_percent` |

---

**Next:** [Runbook 02 · Docker and Portainer on a new
LXC](02-portainer-on-a-new-lxc.md)
