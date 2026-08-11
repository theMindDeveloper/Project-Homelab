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

**Bind mount** — a host directory or file mounted into a container at a chosen
path. Contrast with a *named volume*. Rule used here: bind mounts for
configuration, named volumes for state.

**Bridge (`vmbr0`)** — a virtual switch on the Proxmox host. Guests attach to it
and appear on the physical LAN as if they had their own network card.

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

**DNS-01** — proving domain ownership to a CA by creating a TXT record instead
of serving a file over HTTP. The only way to get a **wildcard** certificate, and
the reason this lab needs nothing inbound.

**Docker** — packaging and running a single application as an isolated process
on the host kernel. → [Docker](01-docker.md)

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

**Nesting (`nesting=1`)** — the Proxmox LXC feature that permits a container
runtime *inside* the container. Without it, the Docker daemon will not start.

**Nginx Proxy Manager (NPM)** — a web UI over nginx. Terminates TLS for every
service in this lab and routes by `Host` header. Single point of failure for
every friendly name.

**node_exporter** — exposes a machine's metrics as an HTTP endpoint for
Prometheus to scrape. One per host.

**OOM killer** — the kernel picks a process to kill when memory runs out. It
chooses by size, not by guilt, so the victim is often not the culprit. Found in
`dmesg -T | grep -i "killed process"`.

**Portainer** — a web UI for Docker. Needs the Docker socket, which is
equivalent to root on the host.

**Prometheus** — a time-series database that **pulls**. It scrapes targets on a
schedule; nothing pushes to it. → [Monitoring](08-monitoring.md)

**Proxmox VE** — Debian plus KVM, LXC, a web UI, clustering and backup. The
hypervisor this lab runs on. → [Proxmox cheat sheet](03-proxmox-cheatsheet.md)

**Quorum** — the majority of votes a cluster needs before it will act. Three
nodes, two needed. A node in the minority makes `/etc/pve` read-only rather than
risk two halves disagreeing. That read-only state is what the grey question
marks in the UI mean.

**RFC1918** — the private IPv4 ranges: `10.0.0.0/8`, `172.16.0.0/12`,
`192.168.0.0/16`. Not routable on the internet. This is why the addresses in this
repository are published without concern.

**Reverse proxy** — accepts connections and forwards them to the right backend
based on the `Host` header. One certificate, one address, many services.

**Snapshot** — a point-in-time copy of a guest's disk. Cheap on LVM-thin and
ZFS, and it **grows as the guest writes**. A forgotten snapshot is a classic way
to fill a pool.

**Thin provisioning** — allocating more storage than exists, on the assumption
that guests will not all use their full allocation. Efficient, and it fails
abruptly. → [Storage](06-storage.md)

**TTL** — how long a DNS answer may be cached. Lower it *before* planning a
change, not after.

**Unprivileged container** — an LXC whose root maps to a high, powerless UID on
the host (usually 100000). Root inside is nobody outside. The default here, and
the reason bind mounts need UID mapping.

**vzdump** — Proxmox's backup command. One archive per guest, restorable to any
node. → [Backup and recovery](07-backup-and-recovery.md)

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
