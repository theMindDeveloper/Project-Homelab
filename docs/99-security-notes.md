# What this repository publishes, and what it does not

This is a public repository documenting a private network. That combination
needs a rule, not a gut feeling. This page is the rule.

---

## The principle

**Publish the design. Never publish the reachability.**

Someone reading this repository should be able to understand exactly how the lab
is built and rebuild something equivalent. They should not gain a single piece of
information that helps them reach *my* machines.

---

## Published, deliberately

| Category | Example | Why it is safe |
|---|---|---|
| Private IPv4 addresses | `192.168.178.87` | RFC1918, not routable from the internet. Meaningless without already being on the LAN. |
| Subnet and gateway | `192.168.178.0/24` | Same reasoning. |
| Internal service ports | Grafana on `3000` | Only reachable inside the LAN. |
| Hostnames and subdomains | `grafana.theminddev.com` | Already public in DNS and in Certificate Transparency logs. Hiding them would be theatre. |
| Ingress architecture | "one Cloudflare tunnel, one published hostname" | The design is the thing worth showing. It also happens to be the strongest part of the setup. |
| Software in use | Proxmox VE 8.x, Nginx Proxy Manager, AdGuard Home | Standard components. |

## Never published

| Category | Why |
|---|---|
| **Public IP address** | The one value that turns everything else from a description into a target. |
| **WAN port forwards** | Publishing "these ports are open" next to "this is my address" is an invitation. Forwards exist for game servers; the list stays out of this repository. |
| **IPv6 host addresses** | Globally routable, so they bypass NAT entirely. They are also EUI-64 derived, meaning the MAC address is embedded in them. |
| **MAC addresses** | Hardware fingerprinting, and they leak into IPv6 anyway. |
| **Cloudflare tunnel token, tunnel ID, connector ID** | The token is a credential. The IDs are identifying. |
| **The DuckDNS hostname** | It is a public DNS name that resolves to the current WAN address. Publishing it is the same as publishing the public IP, with the added convenience that it stays correct. |
| **Exact software versions** | "Proxmox VE 8.x" is fine. "8.2.4" plus a published CVE is a shopping list. |
| **Any secret** | API tokens, passwords, TLS private keys, SSH private keys, `.env` files, Vaultwarden exports, backup credentials. |
| **Personal hostnames** | Devices are named by function, not by person or place. `docker-01`, not `mohammads-laptop-berlin`. |

---

## How secrets are kept out mechanically

Not by discipline. Discipline fails.

1. **`.gitignore` blocks the categories**, not individual files: `.env`,
   `*.key`, `*.pem`, `*credentials*`, `*token*`, `*secret*`.
2. **Every compose file ships as `*.example.yml`** with variables, and the real
   file with values stays untracked.
3. **`scripts/check-secrets.sh` runs before every commit** and greps the staged
   diff for the public IP, IPv6 prefixes, MAC patterns, tunnel UUIDs and common
   token shapes. It exits non-zero and blocks the commit.
4. **Screenshots are blurred before they are committed.** Git history is
   permanent: deleting a file in a later commit does not remove it from
   `git log -p`. If something does slip through, the only real fix is rewriting
   history with `git filter-repo` and force-pushing, and rotating whatever
   leaked.

---

## Two calls the screenshots forced

Publishing screenshots of a live lab made two of the rules above cost something
real. Both are worth writing down, because a policy that has never been
inconvenient has never been tested.

### Game server ports are blurred

`assets/screenshots/pterodactyl-servers.png` and
`assets/screenshots/amp-game-instances.png` show four running game servers.
The port numbers in both are **blurred in the image itself**.

Those servers are the only things in this lab behind a WAN port forward, and
homelab forwards are usually one-to-one, so the internal port is a strong hint
at the external one. Publishing "this port is open" is exactly what the table
above says is never published. Blurring costs the reader nothing that matters
and keeps the rule intact.

The addresses in the same screenshots are `192.168.178.36` and
`192.168.178.32`, and they are left visible, because they are RFC1918.

### Container image tags are visible, and that is deliberate

`assets/screenshots/portainer-lxc102-containers.png` shows exact image tags,
including a pinned application version. The table above says exact software
versions are not published.

The distinction being drawn: that rule exists because a version number next to a
reachable address is a shopping list. **None of the services in that screenshot
is reachable from the internet.** There is no inbound path to any of them, and
the one internet-facing container is not in the list.

Against that, the image tags are the evidence that the lab is kept current,
which is the single most effective control it has against automated scanning.
Hiding them would remove the proof and keep the risk.

If any of those services ever becomes internet-facing, the screenshot comes
down. The rule is not "publish tags", it is "a version is only sensitive next to
a reachable address".

### What this section is really for

Both calls could have gone the other way. What matters is that the rule was
applied and the reasoning was written down, rather than the screenshot being
posted and the policy quietly forgotten. A security policy is only real at the
point where it costs you something.

---

## Why the private addresses are in the diagram on purpose

Every host and guest address in this repository is inside `192.168.178.0/24`,
which is RFC1918. Those addresses are **not routable on the internet**. Knowing
that Grafana sits on `192.168.178.87:3000` is worth nothing unless you are
already on the LAN, and if you are already on the LAN you did not need the
diagram. On top of that, `192.168.178.x` is the factory default of every
FRITZ!Box in Germany, so it identifies nothing about this particular network.

Half-redacting is worse than not redacting. Writing `192.168.178.x` for the
nodes while the guests still show `.59`, `.84` and `.36` costs the reader
clarity and gains no security at all. Either publish the addressing plan or
publish none of it. This repository publishes it.

## The part I would show an interviewer

The interesting property of this setup is that **almost nothing is exposed.**

Internal services resolve through a public wildcard DNS record that points at an
RFC1918 address. Anyone on the internet can resolve `grafana.theminddev.com` and
will get `192.168.178.178`, which they cannot route to. Inside the LAN it
resolves and works. TLS still uses real Let's Encrypt certificates, issued over
a DNS-01 challenge, so no inbound port has to be open for certificate renewal
either.

Exactly one hostname is published to the internet, and it goes through a
Cloudflare tunnel: an outbound connection from the lab to Cloudflare. There is no
inbound firewall rule for it at all.

The honest exception is the game servers, which use classic port forwards. That
is the weakest part of the setup and it is the next thing on the list to replace,
most likely with a WireGuard tunnel on the router so that players join the
network instead of the internet reaching the servers.
