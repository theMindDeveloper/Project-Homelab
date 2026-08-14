# Network segmentation, and why rules on a flat network never worked

This is the page that explains the single most expensive lesson in this lab.
Everything in `13` through `20` is a mechanism. This page is the idea those
mechanisms serve.

---

## The problem, stated precisely

Before August 2026 the game servers were reachable from the internet through
port forwards on the router, and they sat on the same flat `192.168.178.0/24`
network as everything else I own.

```
FRITZ!Box .1
   |
unmanaged switch
   |
   +-- my PC
   +-- Raspberry Pi .178     AdGuard DNS, Nginx Proxy Manager
   +-- NAS .49               all backups
   +-- pve  .20              Proxmox web UI :8006
   +-- pve3 .50              Proxmox web UI :8006
   +-- pve2 .77              Proxmox web UI :8006
   +-- wings                 <-- THE INTERNET CAN REACH THIS
   +-- amp                   <-- AND THIS
```

**The port forward was never the vulnerability.** The vulnerability was that the
machine the internet could reach was a *peer* of every machine I own.

A game server exploit is not exotic. Game servers run mod code, parse untrusted
input from players, and are patched slowly. Assume one gets popped. In that
layout the attacker then had a working network path to Proxmox on `:8006` with
no 2FA, the NAS holding every backup, Vaultwarden holding every password,
AdGuard controlling DNS for the whole house, and my own PC.

**One game exploit equalled total compromise.**

---

## Why two earlier firewall attempts failed

Both attempts tried to enforce separation with **rules** on a **flat** network.

Every machine still had a physical path to every other one. One wrong rule
either broke everything or protected nothing, and debugging meant reading
`cluster.fw` and per-guest `.fw` files with no visibility into what was being
dropped. The Proxmox firewall ended up disabled, twice.

That approach is brittle by construction:

| | Rules on a flat network | Separate segment plus a chokepoint |
|---|---|---|
| What stops the traffic | a rule | the absence of a road |
| Failure mode of a mistake | the path is live again | still no path |
| Where you debug | many files, many hosts | one firewall, one log |
| What a deleted rule costs | everything | nothing, if it is the block rule |

**A rule can be deleted by mistake. A missing cable cannot.**

---

## The pattern

Anything the internet can talk to lives in its own network that has no path
into the real network.

Two halves, and **both** are required:

1. **Separation.** The exposed machine is in a different network segment with
   no physical path to the trusted one. Not "is blocked from". Has no road.
2. **A chokepoint.** One router/firewall sits between that segment and the LAN
   and is the only door. All rules live there, and nowhere else.

VLANs are one way to do the separation. They are **not** the idea. That
distinction is what nobody had explained to me, and it is why I kept trying to
solve a topology problem with a rule editor.

---

## Why a VLAN on its own buys nothing

A VLAN is a layer 2 mechanism (see [13](13-addressing-and-osi-layers.md)). It
splits one switch into several logical switches. It can never carry anything
from one piece to another, because that is what the word means.

So a container alone in a VLAN with no router gets:

- perfect isolation from the house, and
- no Steam, no players, no package updates, and no way for me to administer it.

**A VLAN with no router is a room with no door.** The door is the firewall.

---

## Options I considered

| Option | Verdict | Reason |
|---|---|---|
| Do nothing | rejected | this was the existing state and the whole problem |
| Rented VPS plus a WireGuard relay | rejected | I paid for a homelab to host my own things, not to rent someone else's box |
| Free third-party relay (playit.gg, ngrok) | rejected | a stranger's machine sits in the middle of my traffic, plus latency |
| A second router placed **in line** behind the FRITZ!Box | rejected | tried it before with a FriendlyElec unit: double NAT, two DHCP servers, two layers of port forwarding, split networks. A mess. |
| Managed switch and VLANs alone | deferred | a VLAN separates but cannot route or filter. Also the TL-SG108 is unmanaged and cannot tag frames at all. |
| Full rebuild: replace the FRITZ!Box, dedicated firewall box, managed switch | deferred | roughly 180 EUR, a weekend, and whole-LAN downtime. Worth doing later. |
| **Software DMZ on the hypervisor** | **chosen** | zero cost, zero LAN downtime, uses hardware I already own, and the rules transfer unchanged to a hardware VLAN later |

---

## In line versus on a stick

This is the distinction that explains why the earlier router attempt failed and
this one did not. It is not about the device or the software. It is about
**position in the cable path**.

```
IN LINE  (what failed)
internet -> FRITZ!Box [NAT 1] -> second router [NAT 2] -> switch -> EVERYTHING

ON A STICK  (what works)
internet -> FRITZ!Box [NAT 1] -> switch -> everything, unchanged
                                    |
                              OPNsense [NAT 2, game segment only]
                                    |
                              sealed containers
```

In the second layout OPNsense is **not** in the path. Nothing has to travel
through it to reach the internet. My PC, the Pi, the NAS and all three Proxmox
nodes route exactly as they did before. Only the game containers sit behind the
second NAT.

This is called **router on a stick**, or one-armed routing. It is the reason
the migration caused zero downtime for anything outside the game stack.

---

## What this lab actually built

A Proxmox bridge with `bridge-ports none` (a switch made of software, with no
cable) plus an OPNsense VM with one virtual NIC on each side.

```
house <-cable-> vmbr0 <-> [ OPNsense ] <-> vmbr1 <-> wings, amp, panel
                            the door
```

"No cable" does not mean "no connection". It means **no connection that
OPNsense does not control**. Steam traffic still leaves: wings to vmbr1 to
OPNsense to vmbr0 to the switch to the router to the internet. Player traffic
comes back the same way. Every packet in both directions passes one referee.

Mechanics: [14 bridges](14-proxmox-bridges-and-nics.md) ·
[15 NAT](15-nat-and-port-forwarding.md) ·
[16 firewalls](16-firewalls-and-pf.md) ·
[17 OPNsense](17-opnsense-concepts.md)

---

## What it did and did not buy

**Did:** a compromised game server reaches the internet and nothing else in the
house. Verified with real timeouts, not theory. See
[the migration report](reports/2026-08-13-dmz-migration.md).

**Did not:**

1. **Internal walls inside the segment.** wings, AMP and the panel share
   `10.10.10.0/24` and are neighbours on the same bridge, so traffic between
   them never touches OPNsense. Compromise a game server and you can reach the
   panel; panel admin means code execution on wings.
2. **Egress control.** The segment may reach anything on the internet. A
   compromised server could mine, join a botnet, or attack others from my
   address.
3. **Protection from a hypervisor escape.** OPNsense is a VM on pve2 and both
   bridges live on pve2. Root there controls the referee. This is precisely the
   gap a hardware VLAN closes, because enforcement then lives in a box the
   compromised machine does not control.

Honest grade: went from *one game exploit costs everything* to *one game
exploit costs the game containers*. Not yet at *one game exploit costs one
container*.

---

## The upgrade path, and why it is cheap

When a managed switch arrives, `vmbr1` becomes a real tagged VLAN on a physical
switch and OPNsense gets a VLAN-tagged interface instead of a virtual bridge.

**Every firewall rule stays byte for byte identical**, because the rules are
written against network addresses and interface roles, not against bridges.
That is the payoff for building the software version first: it is not a
throwaway prototype, it is the same design with a different layer 1.

---

**Next:** [13 · Addressing and the OSI layers](13-addressing-and-osi-layers.md)
