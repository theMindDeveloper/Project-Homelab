# Hardening

What is actually done in this lab, what is deliberately not done and why, and
the threat model that makes the difference between those two lists coherent.

This page is about **the lab**.
[`99-security-notes.md`](99-security-notes.md) is about **the repository**.

---

## The threat model

Hardening without a threat model produces a checklist, and a checklist produces
effort spent on the wrong things. So, explicitly:

**What this lab is defending against**

1. **Automated internet scanning.** Constant, indiscriminate, looking for open
   ports, default credentials and known CVEs. This is 99% of hostile traffic any
   home network sees.
2. **A compromised device on the LAN.** A phone, a laptop, a smart plug. The
   most realistic path to anything interesting.
3. **Me.** A mistyped command, a container started with the wrong mount, a
   secret committed to a public repository.

**What it is not defending against**

4. A targeted attacker who wants *this* network specifically.
5. Anyone with physical access to the machines.
6. A nation-state.

Categories 4 to 6 are out of scope for a homelab, and pretending otherwise leads
to security theatre. The defences below are chosen against 1 to 3.

---

## Attack surface, as it stands

| Path from the internet | Exists? | Protection |
|---|---|---|
| Web services on ports 80/443 | **no** | nothing is forwarded; internal DNS returns RFC1918 |
| Proxmox web UI | **no** | LAN only |
| SSH | **no** | LAN only |
| VPN | **no** | none configured — see limitations |
| `apache.theminddev.com` | **yes** | Cloudflare Tunnel, outbound only, static content only |
| Game server ports | **yes** | classic port forwards — the weak point |

The single sentence version: **the only inbound paths are the game server port
forwards, and everything else is either LAN-only or reached through an outbound
tunnel.**

---

## What is done

### Nothing inbound that does not have to be

No port forwards for web services. Not for the reverse proxy, not for the
Proxmox UI, not for SSH, and **not even for certificate renewal**, because
DNS-01 needs no inbound connection.

The Cloudflare Tunnel is the mechanism that makes one public service possible
without an inbound rule: the connector dials out and Cloudflare answers down
that existing connection.

### Internal names resolve to unroutable addresses

`grafana.theminddev.com` resolves publicly to `192.168.178.178`. Anyone on the
internet gets an answer, and the answer is an RFC1918 address they cannot route
to. Inside the LAN it works normally.

This is worth understanding as a technique: it gives friendly names and real
certificates on internal services with no exposure whatsoever.

### Real TLS everywhere, including internally

Let's Encrypt wildcard certificate over DNS-01, terminated at Nginx Proxy
Manager. Internal traffic being encrypted matters for threat 2: a compromised
device on the LAN cannot read another service's session by sniffing.

### Unprivileged containers

Every LXC in the cluster is unprivileged. Container root maps to UID 100000 on
the host, so a root escape inside a container is not root outside it.

```bash
pct create <id> ... --unprivileged 1
```

You cannot flip an existing container between the two. Back up, restore into a
new one.

### Container hardening, applied consistently

Every compose file in this repository:

```yaml
security_opt:
  - no-new-privileges:true      # blocks privilege escalation via setuid
cap_drop: [ALL]                 # where the image tolerates it
cap_add:  [NET_BIND_SERVICE]    # only what is needed back
read_only: true                 # for the internet-facing container
```

The Docker socket, where it is mounted at all (Portainer), is mounted `:ro`.
That reduces the risk; it does not remove it. **Write access to
`/var/run/docker.sock` is root on the host**, because you can start a privileged
container that mounts `/`.

### Secrets are not in git, mechanically

`.gitignore` blocks by category, every compose file ships as `.example`, and
[`scripts/check-secrets.sh`](../scripts/check-secrets.sh) runs as a pre-commit
hook and refuses a commit containing a public IP, an IPv6 host address, a MAC
address, a UUID, a private key or a token-shaped string.

This is defence against threat 3, which is the most likely one on the list.

### A password manager, self-hosted

Vaultwarden. Unique generated passwords per service. Reused credentials are how
threat 2 turns into threat 1 having a very good day.

### Network-wide DNS filtering

AdGuard Home resolves for every device. Blocks ad and tracker domains, and
incidentally a good share of malware command-and-control domains, for devices
that cannot run any security software of their own.

### Automatic security updates

`unattended-upgrades` on the Debian hosts. Images are pulled and recreated
monthly:

```bash
docker compose pull && docker compose up -d && docker image prune -f
```

An unpatched container is the most likely way threat 1 succeeds.

---

## What is not done, and why

Written down as gaps, not omitted. A hardening page that only lists strengths is
a marketing page.

### No network segmentation

The right design puts IoT devices, game servers and the management plane in
separate VLANs, so a compromised smart plug cannot reach the Proxmox API.

**Why not:** the TL-SG108 v3 is unmanaged. VLANs need a managed switch. That is
the real reason and it costs about sixty euros to fix.

### Game server port forwards

The one direct inbound path. A game server is a complex application processing
untrusted input from strangers, running in a container, on the same flat network
as everything else.

**Mitigation in place:** Pterodactyl Wings runs each server as its own Docker
container, so a compromise is contained to that container rather than the host.

**The planned fix:** WireGuard on the router, so players join the network rather
than the internet reaching the servers. That changes the model from "anyone can
connect" to "people I gave a key to can connect", which is the correct model for
a private server.

### No 2FA on internal services

Proxmox supports TOTP. Vaultwarden supports TOTP. Neither is enabled.

**Why not:** honest answer, friction, on services only reachable from the LAN.
Proxmox is the one where this is least defensible, because the Proxmox API is
root over every guest in the lab. It belongs on the list of things to fix.

### No host firewall rules

Neither Proxmox's firewall nor `ufw` is configured. The network's only ingress
control is the router.

**Why not:** on a flat LAN with no inbound forwards, host firewalls would be
defence in depth against threat 2 only. It is a genuine gap, and the reason to
do it is precisely threat 2.

Worth knowing if it gets added: **Docker writes its own iptables rules and
bypasses ufw.** A ufw rule denying a port that Docker has published does
nothing. This surprises people badly and it is worth testing rather than
assuming.

### No intrusion detection, no log aggregation

No CrowdSec, no fail2ban, no Loki, no centralised logs. Each host's journal
stays on that host, which means a compromised host's logs are attacker-writable.

### No alerting

Prometheus collects, nothing notifies. A breach, like a disk filling, is
discovered by looking. This is in the README's limitations and it is the single
highest-value missing piece.

### No offsite backup, no encryption at rest

The backups sit on a NAS in the same room, unencrypted. Fire takes everything;
theft of the NAS takes the Vaultwarden database.

---

## The order I would fix these in

Ranked by risk reduced per hour spent, which is the only ranking that matters
for a lab run in evenings.

| # | Action | Why first |
|---:|---|---|
| 1 | **Alertmanager** | not knowing is worse than any single missing control |
| 2 | **2FA on Proxmox** | the API is root over everything; ten minutes of work |
| 3 | **WireGuard, drop the game port forwards** | removes the only real inbound path |
| 4 | **Offsite encrypted backup** | the failure with no recovery |
| 5 | **Managed switch and VLANs** | the correct answer to threat 2, but it needs hardware |
| 6 | **Host firewalls** | defence in depth once segmentation exists |
| 7 | **Log aggregation** | valuable, and the largest time investment |

---

## Habits, rather than configuration

The things that are not a setting.

**Snapshot before every change.** `pct snapshot 102 before-x` costs one second
and turns a bad evening into a rollback. Delete it afterwards; a forgotten
snapshot fills a thin pool.

**Read what you are piping to a shell.** `curl ... | bash` is normal in the
homelab world and it is executing a stranger's code as root. Download, read,
then run.

**One change at a time.** Not a security practice on paper, and in practice the
difference between knowing what broke and guessing.

**Assume the LAN is hostile.** It contains a smart plug, a TV and whatever
firmware they shipped with. Encrypt internal traffic, use unique credentials,
and do not leave admin interfaces unauthenticated because "it is only local".

---

**Back to:** [wiki index](README.md) ·
**Repository policy:** [`99-security-notes.md`](99-security-notes.md)
