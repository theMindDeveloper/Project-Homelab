# Glossary

The terms that come up constantly in this repository, defined in the way that
makes the rest of it readable. Alphabetical.

Where a term has a longer page, it is linked.

---

**ACME** — the protocol Let's Encrypt uses to issue certificates automatically.
Two challenge types matter: HTTP-01 (needs an open port 80) and DNS-01 (needs
API access to your DNS). This lab uses DNS-01, which is why no port is open.
→ [Networking, DNS and TLS](05-networking-dns-tls.md)

**AdGuard Home** — a DNS server that filters. Every device on this LAN uses it,
which gives network-wide ad blocking with no client configuration and makes it
the most load-bearing container in the lab.

**Alias (firewall)** — a name for a host, network or port group in OPNsense,
referenced by rules. Change the alias once and every rule that uses it follows.
→ [Firewalls and `pf`](16-firewalls-and-pf.md)

**`allowed_origins`** — the list of websocket origins Pterodactyl wings will
accept. Empty means wings trusts only the panel URL it already knows and answers
`403` to everything else, which presents as a console spinner.
→ [Game server hosting](20-game-server-hosting.md)

**Bind mount** — a host directory or file mounted into a container at a chosen
path. Contrast with a *named volume*. Rule used here: bind mounts for
configuration, named volumes for state.

**Bogon** — an address that should never appear as a source from the internet,
such as an RFC1918 address arriving on a WAN interface. OPNsense blocks bogons
by default, which locks you out when the "WAN" side faces your own house.
→ [OPNsense concepts](17-opnsense-concepts.md)

**Bridge (`vmbr0`)** — a virtual switch on the Proxmox host. Guests attach to it
and appear on the physical LAN as if they had their own network card. `vmbr1` is the same thing created with
`bridge-ports none`: a switch with no uplink cable, which is the separation half
of the DMZ design. → [Bridges and NICs](14-proxmox-bridges-and-nics.md)

**`bridge-ports none`** — the line that gives a Proxmox bridge no physical
uplink. One line, and it is the entire *separation* half of the DMZ design. A
rule can be deleted by mistake; an absent cable cannot.
→ [Network segmentation](12-network-segmentation.md)

**Capabilities** — root's powers, split into about forty separate flags
(`NET_BIND_SERVICE`, `SYS_ADMIN`, …). Containers run with most of them dropped,
which is why "root in a container" is much weaker than root on the host.

**cgroups** — the kernel feature that limits **how much** a process can use: CPU,
memory, I/O. Namespaces control what it can *see*; cgroups control what it can
*consume*.

**Cloudflare Tunnel** — an outbound connection from your network to Cloudflare,
down which they send requests for a published hostname. Publishes a service with
**no inbound firewall rule**. Cloudflare terminates TLS and can see the
plaintext, which is the trade.

**Compose** → [Docker Compose](02-docker-compose.md)

**Corosync** — the messaging layer Proxmox clustering runs on. It carries the
votes that decide quorum. Sensitive to latency and to clock drift; when the
cluster misbehaves, corosync is usually why.

**Crash consistent** — a backup taken without telling the guest, so it captures
the exact state of an instant. Equivalent to pulling the power cable at that
moment. Journalling filesystems and databases usually recover; applications that
buffer in memory may not.

**Destination NAT (DNAT)** — rewriting where an incoming packet is going. A port
forward. The only mechanism that lets an outsider *start* a conversation with
something inside, which is why every one is a deliberate decision. Called "Port
Forward" in older OPNsense releases.
→ [NAT and port forwarding](15-nat-and-port-forwarding.md)

**DMZ** — a network segment holding internet-facing hosts, with no path into the
trusted network. Note that the checkbox labelled "DMZ" or "Exposed Host" on
consumer routers is the **opposite**: it forwards every port to one machine that
is still a peer of everything else on the LAN.
→ [Network segmentation](12-network-segmentation.md)

**DNS-01** — proving domain ownership to a CA by creating a TXT record instead
of serving a file over HTTP. The only way to get a **wildcard** certificate, and
the reason this lab needs nothing inbound.

**Docker** — packaging and running a single application as an isolated process
on the host kernel. → [Docker](01-docker.md)

**Double NAT** — two routers each translating addresses in a row. Two DHCP
servers, two layers of port forwarding, split networks. What happens when a
second router is placed *in line* rather than *on a stick*.
→ [NAT and port forwarding](15-nat-and-port-forwarding.md)

**Exit code 124** — the shell's `timeout` command fired, meaning the connection
was silently dropped. Throughout the DMZ verification tests, `124` is the
desired result. → [the migration report](reports/2026-08-13-dmz-migration.md)

**Exit code 137** — killed by the OOM killer, meaning a memory cap was hit.
Usually a container cap that disagrees with an application-level limit inside it.
→ [LXC migration and resources](19-lxc-migration-and-resources.md)

**FreeBSD** — a Unix operating system with its own kernel, not a Linux
distribution. OPNsense runs on it, which is why OPNsense cannot be an LXC
container on a Linux host. → [FreeBSD basics](18-freebsd-basics.md)

**Glance** — the dashboard at the front of this lab. HTTP health checks and
bookmarks in a YAML file. Answers "is anything red" in one second, which is why
it gets looked at and Grafana does not.

**Grafana** — draws graphs from a data source. Stores dashboards, not metrics.

**Image (Docker)** — a stack of read-only filesystem layers plus metadata. A
container is an image plus one thin writable layer.

**Inode** — the metadata entry for a file. Finite and separate from disk space,
which is why a disk can report "no space left" at 40% full.
Diagnose with `df -i`.

**LXC** — a container that holds a **whole Linux userland**, with systemd, apt
and an IP address. Behaves like a lightweight server. Every guest in this
cluster is one. → [LXC or VM](04-lxc-vs-vm.md)

**LVM-thin** — Proxmox's default block storage. Supports snapshots and thin
provisioning. When the pool fills, **every guest on it goes read-only at once**,
and `df` inside the guests will not have warned you. → [Storage](06-storage.md)

**Named volume** — Docker-managed storage in `/var/lib/docker/volumes/`.
Survives `docker compose down`. Deleted by `down -v`.

**Namespaces** — the kernel feature that controls **what** a process can see:
processes, mounts, network, hostname, users. The other half of what makes a
container.

**NAT reflection** — making destination NAT rules apply to clients on the same
subnet as the firewall, whose packets do not "arrive from outside". A
convenience feature for a router-on-a-stick topology, not a security setting.
→ [NAT and port forwarding](15-nat-and-port-forwarding.md)

**Nesting (`nesting=1`)** — the Proxmox LXC feature that permits a container
runtime *inside* the container. Without it, the Docker daemon will not start.

**Nginx Proxy Manager (NPM)** — a web UI over nginx. Terminates TLS for every
service in this lab and routes by `Host` header. Single point of failure for
every friendly name.

**NIC** — Network Interface Card, the physical Ethernet socket. Each ThinkCentre
in this lab has exactly one, which is why the DMZ had to be built in software.
→ [Bridges and NICs](14-proxmox-bridges-and-nics.md)

**node_exporter** — exposes a machine's metrics as an HTTP endpoint for
Prometheus to scrape. One per host.

**`NoMatchingMachineId`** — the AMP licence error produced when a container lands
on a different physical host and its machine fingerprint changes. Fixed with
`ampinstmgr reactivate`. → [Game server hosting](20-game-server-hosting.md)

**OOM killer** — the kernel picks a process to kill when memory runs out. It
chooses by size, not by guilt, so the victim is often not the culprit. Found in
`dmesg -T | grep -i "killed process"`.

**OPNsense** — a FreeBSD-based firewall and router distribution with a web GUI
over `pf`. VM 200 in this lab, and the only virtual machine in an otherwise
LXC-only cluster. → [OPNsense concepts](17-opnsense-concepts.md)

**`pf`** — the FreeBSD packet filter, the actual firewall engine behind OPNsense.
Stateful, reads rules top to bottom, and stops at the first match when `quick`
is set. → [Firewalls and `pf`](16-firewalls-and-pf.md)

**`pfctl`** — the command that controls `pf`. `-d` disables filtering, `-e`
re-enables it, `-s rules` lists the ruleset. `pfctl -d` is the emergency exit
from a GUI lockout and must never be left in place.
→ [Runbook 17](../runbooks/17-recover-from-an-opnsense-lockout.md)

**Portainer** — a web UI for Docker. Needs the Docker socket, which is
equivalent to root on the host.

**Prometheus** — a time-series database that **pulls**. It scrapes targets on a
schedule; nothing pushes to it. → [Monitoring](08-monitoring.md)

**Proxmox VE** — Debian plus KVM, LXC, a web UI, clustering and backup. The
hypervisor this lab runs on. → [Proxmox cheat sheet](03-proxmox-cheatsheet.md)

**Quick (`pf`)** — a rule flag meaning "if this matches, stop reading and apply
it". Ticked by default in OPNsense, and the reason rule *order* is decisive.
→ [Firewalls and `pf`](16-firewalls-and-pf.md)

**Quorum** — the majority of votes a cluster needs before it will act. Three
nodes, two needed. A node in the minority makes `/etc/pve` read-only rather than
risk two halves disagreeing. That read-only state is what the grey question
marks in the UI mean.

**RFC1918** — the private IPv4 ranges: `10.0.0.0/8`, `172.16.0.0/12`,
`192.168.0.0/16`. Not routable on the internet. This is why the addresses in this
repository are published without concern.

**Reverse proxy** — accepts connections and forwards them to the right backend
based on the `Host` header. One certificate, one address, many services.

**Router on a stick** — a router hanging off a switch rather than sitting in
line, so only the traffic that needs it passes through it. The difference
between the failed attempt and the working one.
→ [Network segmentation](12-network-segmentation.md)

**Snapshot** — a point-in-time copy of a guest's disk. Cheap on LVM-thin and
ZFS, and it **grows as the guest writes**. A forgotten snapshot is a classic way
to fill a pool.

**Source NAT (SNAT)** — rewriting where a packet came from, so many devices
share one public address. Opens nothing, because it only happens for
conversations you started.
→ [NAT and port forwarding](15-nat-and-port-forwarding.md)

**Stateful** — a firewall that tracks conversations rather than individual
packets, so replies flow back without needing their own rule. This is why a pass
rule in one direction does not undo a block rule in the other.
→ [Firewalls and `pf`](16-firewalls-and-pf.md)

**Static route** — a signpost telling a device which way to reach a network.
**It grants no permission.** Routing answers *which way do I go*; filtering
answers *am I allowed*. You need both.
→ [NAT and port forwarding](15-nat-and-port-forwarding.md)

**Thin provisioning** — allocating more storage than exists, on the assumption
that guests will not all use their full allocation. Efficient, and it fails
abruptly. → [Storage](06-storage.md)

**TTL** — how long a DNS answer may be cached. Lower it *before* planning a
change, not after.

**Unprivileged container** — an LXC whose root maps to a high, powerless UID on
the host (usually 100000). Root inside is nobody outside. The default here, and
the reason bind mounts need UID mapping.

**VirtIO** — a paravirtualised device: a fake network card that does not imitate
any real chip and instead speaks a protocol designed for virtualisation. Much
faster than emulating real hardware. Appears as `vtnet0` in FreeBSD and `eth0`
in Linux. → [Bridges and NICs](14-proxmox-bridges-and-nics.md)

**VLAN** — one way to split a physical switch into several logical networks,
using tags on frames. A layer 2 mechanism, so a VLAN with no router attached is
a room with no door. → [Addressing and the OSI layers](13-addressing-and-osi-layers.md)

**`vmbr1`** — the Proxmox bridge holding the sealed game segment. Created with
`bridge-ports none`, so nothing reaches it except through the OPNsense VM that
is attached to both bridges. → [Bridges and NICs](14-proxmox-bridges-and-nics.md)

**`vtnet0` / `vtnet1`** — FreeBSD's names for VirtIO network cards. The same
devices Proxmox calls `net0` and `net1`, and that a Linux guest would call
`eth0` and `eth1`. → [FreeBSD basics](18-freebsd-basics.md)

**vzdump** — Proxmox's backup command. One archive per guest, restorable to any
node. → [Backup and recovery](07-backup-and-recovery.md)

**WAN and LAN (OPNsense)** — labels for interface *roles*, not for trust levels.
WAN faces the outside world; LAN faces the network being protected. In this lab
the **house** is on the WAN side, which feels backwards and is correct.
→ [OPNsense concepts](17-opnsense-concepts.md)

**Wildcard certificate** — one certificate covering `*.domain`. Requires DNS-01.
Covers every internal service in this lab with a single renewal.

**X-Forwarded-For / X-Forwarded-Proto** — headers a reverse proxy adds so the
backend knows the real client address and the original scheme. Missing
`X-Forwarded-Proto` is the cause of infinite redirect loops. Trusting these
headers from *any* source is a vulnerability, which is what `TRUSTED_PROXIES`
settings exist to prevent.

**ZFS** — a filesystem with checksums, compression, snapshots and send/receive.
Detects silent corruption, which RAID alone does not. Wants RAM.

---

**Back to:** [wiki index](README.md)
