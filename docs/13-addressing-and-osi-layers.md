# Addressing, and the OSI layers that actually matter

Every instruction in the DMZ migration was meaningless to me until I understood
this page. It is deliberately basic. If you already know what a `/24` is, skip
to [the layer 2 versus layer 3 section](#layer-2-and-layer-3).

---

## An address and a network

An IP address is a number identifying a device: `192.168.178.20`.

`192.168.178.0/24` means every address from `.0` to `.255`. The `/24` says the
first three numbers are fixed and only the last one varies. That block is one
network.

**The rule that everything else follows from:**

> Two devices can talk to each other directly only if they are in the same
> network.

`192.168.178.20` and `192.168.178.77` are neighbours. They can talk.
`192.168.178.20` and `10.10.10.20` are not, and cannot reach each other without
help. That "help" is a router, and choosing what that router will and will not
carry is the entire DMZ design.

### Reading the prefix

| Notation | Fixed part | Addresses | Typical use |
|---|---|---|---|
| `/24` | first 3 octets | 256 | one home or lab network |
| `/16` | first 2 octets | 65,536 | a large campus, or `192.168.0.0/16` as a family |
| `/32` | all 4 octets | 1 | exactly one host, used in firewall rules |
| `/0` | nothing | all | "anywhere", the default route |

In this lab you will see `10.10.10.0/24` (the sealed segment as a whole),
`10.10.10.20/24` (one host inside it, carrying its prefix so it knows who its
neighbours are) and `0.0.0.0/0` (the default route, meaning "everything else").

### Private address space

Three ranges are reserved for private networks and are never routed across the
internet:

| Range | Size |
|---|---|
| `10.0.0.0/8` | 16.7 million |
| `172.16.0.0/12` | 1 million |
| `192.168.0.0/16` | 65,536 |

The house LAN uses `192.168.178.0/24`. The sealed segment uses
`10.10.10.0/24`. Picking a different *family* (10.x rather than another
192.168.x) was deliberate: every address in this lab now tells you which side of
the firewall it is on, at a glance, with no lookup.

---

## Switch, router, firewall

Three words that get used interchangeably and are not interchangeable.

| Device | What it does | In this lab |
|---|---|---|
| **Switch** | moves data *inside* one network | the TP-Link TL-SG108, and every Proxmox bridge |
| **Router** | has an address in *two* networks at once and carries data between them | the FRITZ!Box, and now OPNsense |
| **Firewall** | a router that also decides which traffic it will refuse | OPNsense |

> **Switches move data inside a network. Routers move data between networks.**

A firewall is almost always the same physical box as a router, which is why the
words blur. Keep them separate mentally: routing answers *which way do I go*,
filtering answers *am I allowed*. They are independent systems, and
[15](15-nat-and-port-forwarding.md) shows a case where getting one without the
other produces a confusing failure.

---

## Layer 2 and layer 3

The OSI model has seven layers. Three of them mattered for this work.

### Layer 1, physical

Copper, electricity, light. Gets a 1 or a 0 to the other end of a cable.
Understands nothing about what it is carrying.

### Layer 2, local delivery

Data is grouped into **frames** carrying **MAC addresses**, which are burned
into each network card. A switch reads the destination MAC and picks a port.

Layer 2 only works **inside one network**. A switch has never heard of a MAC
address in a datacentre in Ireland and never will.

### Layer 3, distant delivery

Data is grouped into **packets** carrying **IP addresses**. Unlike MACs, IPs are
structured into groups, which lets a device work out "this destination is not
local, so send it toward the exit". The device that does that work is a router.

---

## The consequence that unlocked the design

**VLANs and Proxmox bridges are layer 2.**

They split one switch into several logical switches. They can never, by
construction, carry anything from one piece to another. That is not a limitation
to engineer around. That is what the word means.

This answered the question I kept asking: *why can't I just make another VLAN
and skip the firewall?* Because a VLAN with no router attached is a room with no
door. The container gets perfect isolation and also no Steam, no players and no
way for me to log in.

The corollary is the good news: because the isolation is a property of layer 2,
**the firewall rules are written entirely at layer 3** and do not care whether
the layer 2 separation is a software bridge today or a tagged VLAN on a managed
switch tomorrow. Swapping the hardware later changes nothing above it.

---

## Ports

A port number says *which service* on a machine you want.

| Port | Service |
|---|---|
| 22 | SSH |
| 53 | DNS |
| 80 | HTTP |
| 443 | HTTPS |
| 8006 | the Proxmox web UI |

`192.168.178.20:8006` means "the Proxmox UI on that machine". An address without
a port identifies a machine; an address with a port identifies a conversation.

Two protocols carry ports, and games use both:

- **TCP** establishes a connection, guarantees order and delivery. Web, SSH,
  Minecraft's main protocol.
- **UDP** fires packets with no handshake and no guarantees. Lower latency,
  which is why most game traffic and voice use it. Terraria and Space Engineers
  in this lab are UDP.

Getting the protocol wrong in a forwarding rule produces the most confusing
class of failure there is: the port scanner says "open" and the game still will
not connect.

---

## Applied to this lab

| Address | Network | What it is |
|---|---|---|
| `192.168.178.1` | LAN | FRITZ!Box, the house gateway |
| `192.168.178.77` | LAN | pve2, the node hosting the whole game stack |
| `192.168.178.60` | LAN | the OPNsense **WAN** leg, its address on the house side |
| `10.10.10.1` | DMZ | the OPNsense **LAN** leg, the gateway for the sealed segment |
| `10.10.10.20` | DMZ | wings |
| `10.10.10.21` | DMZ | AMP |
| `10.10.10.22` | DMZ | the Pterodactyl panel |

One machine, OPNsense, holds an address in both networks. That is the definition
of a router, and it is the only device in this lab that does.

---

**Next:** [14 · Proxmox bridges, NICs and VirtIO](14-proxmox-bridges-and-nics.md)
