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
| Game server ports | **yes** | forwarded to a firewall, into an isolated network segment |

The single sentence version: **the only inbound paths are the game server port
forwards, they land in a sealed segment that cannot reach the house, and
everything else is either LAN-only or reached through an outbound tunnel.**

Every forward now points at `192.168.178.60`, the OPNsense WAN leg. **Nothing on
the house LAN is a forward target any more.** That is the single structural
change made in August 2026.

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

### Segmentation is done for the game servers, and only for them

**What is done.** Everything internet-facing (Pterodactyl wings and panel, AMP)
lives in `10.10.10.0/24`, on a Proxmox bridge with `bridge-ports none` and no
physical uplink. An OPNsense VM is the only route out, and a block rule refuses
`10.10.10.0/24 -> 192.168.178.0/24`. Verified: a game container cannot reach
Proxmox, the NAS, AdGuard or my PC, and an `nmap` sweep of the house from inside
the segment finds nothing.

Full reasoning: [`12-network-segmentation.md`](12-network-segmentation.md).
The build: [runbooks 12 to 18](../runbooks/).

**What is not done.** IoT devices, the management plane and my own machines are
still on one flat `192.168.178.0/24`. A compromised smart plug can still reach
the Proxmox API. That is threat 2 and it is unaddressed.

**Why not:** the TL-SG108 v3 is unmanaged and cannot tag VLAN frames. A software
bridge works for the game segment only because those guests all live on one
node. Segmenting the physical LAN needs a managed switch, roughly sixty euros.

### Three gaps inside the segment that was built

Written down because a segment is not a boundary until these are closed.

1. **No internal walls.** wings, AMP and the panel share `10.10.10.0/24` and are
   neighbours on the same bridge, so traffic between them never reaches
   OPNsense. Compromise a game server and you can reach the panel; panel admin
   means code execution on wings. The fix is a subnet per service.
2. **Egress is unrestricted.** The segment may reach anything on the internet. A
   compromised server could mine, join a botnet, or attack third parties from my
   address.
3. **A Proxmox host escape defeats all of it.** OPNsense is a VM on pve2 and
   both bridges live on pve2. Root there controls the referee. Only enforcement
   in hardware the compromised machine does not control closes this, which is
   what the managed switch buys.

There is also a leftover **IPv6 allow rule** on the OPNsense LAN interface. The
block rule is IPv4 only. Harmless while the segment has no IPv6 address, and an
open door around the block the moment it gets one. It should be deleted.

### Game server port forwards still exist

They always will: players come from the internet and their addresses cannot be
known in advance. The point was never to remove them.

**What changed** is where they land. Previously a forward pointed at a container
that was a peer of every machine in the house. Now it points at a firewall,
which forwards it into a network with no route back.

**Mitigations in place:** Pterodactyl wings runs each game as its own Docker
container; the segment is sealed; the admin ports (panel, wings API) are
forwarded with a source restricted to `192.168.178.0/24`, so they exist for me
and not for the internet.

**WireGuard is no longer the planned fix.** It was the plan when the forwards
were the whole problem. Making players join the network was the correct model
for a private server and the wrong tool for a public one, and the segmentation
does more, for zero recurring cost and no friction for players.

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
| 3 | **Delete the leftover IPv6 allow rule** | two minutes, and it currently routes around the block rule if IPv6 ever appears |
| 4 | **Egress filtering out of the DMZ** | closes gap 2 above; an evening in the OPNsense rule editor, no hardware |
| 5 | **Offsite encrypted backup** | the failure with no recovery |
| 6 | **A subnet per service inside the DMZ** | closes gap 1 above |
| 7 | **Managed switch and VLANs** | the correct answer to threat 2, and it also closes gap 3 |
| 8 | **Host firewalls** | defence in depth once segmentation is physical |
| 9 | **Log aggregation** | valuable, and the largest time investment |

Items 3 and 4 moved to the top because they are cheap, they need no hardware,
and they close gaps in a control that already exists. Fixing something you
already built is almost always better value than building the next thing.

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

**Prefer removing the path to writing a rule.** Two attempts to protect the game
servers with Proxmox firewall rules on a flat network failed, because every
machine still had a physical path to every other one and one wrong rule either
broke everything or protected nothing. The third attempt worked because it began
by deleting the road. **A rule can be removed by mistake; a cable that does not
exist cannot.**

---

**Back to:** [wiki index](README.md) ·
**Repository policy:** [`99-security-notes.md`](99-security-notes.md)
