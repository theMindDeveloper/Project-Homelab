# OPNsense: what it is, why a VM, and the naming trap

OPNsense is a FreeBSD-based firewall and router distribution with a web GUI over
`pf`. In this lab it is VM 200 on pve2, and it is the only virtual machine in an
otherwise LXC-only cluster.

This page covers the decisions and the vocabulary. The build itself is
[runbook 13](../runbooks/13-install-the-opnsense-vm.md).

---

## Why OPNsense and not pfSense

Both are FreeBSD, both are built on `pf`, and either would have worked.

| | OPNsense | pfSense CE |
|---|---|---|
| Release cadence | weekly security updates, two major releases a year | slower, less predictable |
| GUI | modern, consistent, sensible defaults | dated, and the newer version is behind a paywall |
| Licensing | BSD, no commercial gate | CE has had unpredictable licensing moves |
| Community | large, and what most homelabs run today | large but shrinking |

The deciding factors were the update cadence and the licensing predictability.
For a box whose entire job is to be the security boundary, "gets patched every
week" is worth more than any feature.

---

## Why it had to be a VM

Two independent reasons, either of which is sufficient.

**1. It is FreeBSD, not Linux.**
An LXC container borrows the host's Linux kernel. `pf` is a FreeBSD kernel
feature. There is no way to run a FreeBSD kernel feature on a Linux kernel, so
OPNsense cannot be a container on a Proxmox host. This is not a configuration
problem, it is what "shares the host kernel" means. See
[04 · LXC or VM](04-lxc-vs-vm.md).

**2. You would not want it to be one anyway.**
Rule 5 of the decision rule in `04` says: use a VM when you do not trust the
workload or when isolation strength matters. A firewall guarding against a
compromised guest should not itself be a container borrowing the kernel it is
supposed to be protecting.

This makes OPNsense the first VM in the cluster and formally breaks the
"LXC only" rule recorded in `04`, which is now updated to say so.

---

![OPNsense dashboard, both interfaces up](../assets/screenshots/opnsense-dashboard.png)

*Both legs up and carrying traffic: WAN `192.168.178.60/24`, LAN
`10.10.10.1/24`. Memory at 37% of 2 GB and load at 1.04 on two cores, which is
why the allocation below is as small as it is. The red slice of the firewall
chart is `Default deny / state violation rule (WAN)`, which is the internet
being the internet. Patch levels redacted, see
[`99-security-notes.md`](99-security-notes.md).*

## Resources, and why they are small

| | Value | Reasoning |
|---|---|---|
| RAM | 2048 MB | routing and `pf` are cheap; this is comfortable headroom |
| Cores | 2 | see [19 · cores are not reserved](19-lxc-migration-and-resources.md) |
| Disk | 20 GB | the base install is a few GB; the rest is logs |
| Filesystem | **UFS**, not ZFS | ZFS wants RAM for caching and gains nothing on a 20 GB virtual disk that already sits on LVM-thin |
| Boot | `--onboot 1` | if pve2 reboots and the firewall does not come back, the game segment is dark |

`--onboot 1` is the one that matters operationally. Everything in the DMZ
depends on this VM being up.

---

## WAN and LAN: the naming trap

These are just labels OPNsense uses for interface roles:

- **WAN** is the side facing the outside world.
- **LAN** is the side facing the network being protected.

**From OPNsense's point of view, my house is the outside world.**

| Leg | VirtIO device | Bridge | Address | Faces |
|---|---|---|---|---|
| **WAN** | `vtnet0` | `vmbr0` | `192.168.178.60/24` | the house LAN |
| **LAN** | `vtnet1` | `vmbr1` | `10.10.10.1/24` | the sealed game segment |

This feels backwards and it is correct. The house is untrusted *relative to the
thing this firewall protects*, which is the game segment... and simultaneously
the game segment is untrusted relative to the house. Both are true; the labels
only describe which side each interface is on, not which side is more
trustworthy.

![OPNsense interface assignments: WAN on vtnet0, LAN on vtnet1](../assets/screenshots/opnsense-interface-assignments.png)

*Two hardware interfaces, and the assignment that decides which way the firewall
faces. MAC addresses redacted per
[`99-security-notes.md`](99-security-notes.md).*

Every rule in [16](16-firewalls-and-pf.md) reads correctly once you hold this
straight, and reads like nonsense until you do.

---

## Addressing, and the two settings that must be off

Console menu option **2** (Set interface IP address):

| Leg | Address | Gateway | **DHCP server** |
|---|---|---|---|
| WAN `vtnet0` | `192.168.178.60/24` | `192.168.178.1` | **off** |
| LAN `vtnet1` | `10.10.10.1/24` | none | **off** |

**DHCP off on both legs is critical.** A second DHCP server on the house LAN is
exactly what wrecked the earlier in-line router attempt
([15 · double NAT](15-nat-and-port-forwarding.md#double-nat-and-why-it-wrecked-the-earlier-attempt)).
Everything in this lab is statically addressed, so nothing needs it.

Only the WAN leg gets a gateway. A firewall has exactly one default route, and
it points at the way out. Setting a gateway on LAN as well creates two default
routes and asymmetric routing.

In OPNsense 26.7, DNS and DHCP are served by **Dnsmasq**; the old ISC DHCPv4
service was removed in recent releases. If you are following an older guide
looking for "DHCPv4 → disable", that is where it went.

---

## The two WAN checkboxes that will lock you out

Interfaces → WAN, in the defaults:

- ☑ **Block private networks**
- ☑ **Block bogon networks**

These exist for a firewall facing the real internet, where a packet arriving
from outside with an RFC1918 source address is spoofed and should be discarded.

**Mine faces my house, which *is* a private network.** With these ticked, every
packet from `192.168.178.x` is dropped, including my browser trying to reach the
GUI. Both must be **unticked** in a router-on-a-stick topology.

> **This is correct here and dangerous elsewhere.** It is right because this
> firewall's "WAN" faces my own house, which is a private network. **If your
> OPNsense is the actual edge router facing the real internet, leave both of
> these ticked.** There, a packet arriving from outside with an RFC1918 or bogon
> source address is spoofed and dropping it is the whole reason the option
> exists. Unticking them on a genuine internet-facing WAN removes a real
> protection for no benefit.

This is one of two independent causes of "the GUI at `.60` is unreachable"; the
other is that the address was saved to `/conf/config.xml` but never applied to
the running interface. See
[runbook 17](../runbooks/17-recover-from-an-opnsense-lockout.md).

---

## Menu map for the things this lab uses

| What | Where in 26.7 | Note |
|---|---|---|
| Assign interfaces | console option 1 | LAGGs no, VLANs no |
| Set addresses | console option 2 | DHCP off on both |
| Shell / `pfctl` | console option 8 | the emergency exit |
| Firewall rules | Firewall → Rules → *interface* | order matters, top down |
| Cross-interface rules | Firewall → Rules → Floating | evaluated first |
| Port forwards | Firewall → **NAT → Destination NAT** | called "Port Forward" in older guides |
| Outbound NAT | Firewall → NAT → Outbound | automatic is correct here |
| NAT reflection | Firewall → Settings → Advanced | needed for same-subnet clients |
| Named hosts and ports | Firewall → Aliases | do this before you have a dozen rules |
| Live blocked traffic | Firewall → Log Files → Live View | filter on `10.10.10` |
| Updates | System → Firmware → Updates | weekly, and worth actually doing |

---

## What OPNsense is doing in this lab, and what it is not

**It is:**

- the only router between `10.10.10.0/24` and everything else
- the only place firewall rules for the game segment exist
- the second DNAT hop for published game ports
- the thing that makes `bridge-ports none` useful rather than merely isolating

**It is not:**

- in the path of any other traffic in the house
- a DHCP server
- a DNS resolver (though enabling Dnsmasq on the LAN leg is the clean fix for
  the containers currently pointing at `1.1.1.1` directly)
- a VPN endpoint, yet

---

## Honest limitations of this deployment

1. **It runs on the machine it is protecting from.** Both bridges and the
   firewall VM live on pve2. Root on pve2 defeats all of it. A hardware
   firewall closes this; a software one on the same hypervisor cannot.
2. **It is a single point of failure for the game segment.** If VM 200 is down,
   nothing in the DMZ reaches anything. Acceptable for games; it would not be
   for anything that matters.
3. **No 2FA on its own GUI**, though the GUI is reachable only from the house
   LAN and is not forwarded from the internet.
4. **No IDS/IPS.** OPNsense ships Suricata and it is not enabled. On a 2-core
   allocation, turning it on would need a resource review first.

---

**Next:** [18 · FreeBSD basics for the OPNsense admin](18-freebsd-basics.md)
