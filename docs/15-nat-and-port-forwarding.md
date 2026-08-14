# NAT, port forwarding, reflection and static routes

Four mechanisms that all involve "getting a packet to the right place" and are
constantly confused with each other. Three of them rewrite addresses. One of
them does not, and mistaking a route for a permission cost me an afternoon.

---

## NAT, in one paragraph

Your house has one public IP address. Every device inside has a private one. The
router rewrites the *sender* address of outgoing packets so everything appears
to come from the single public address, and keeps a table of who asked for what
so the replies get handed back to the right device.

That rewrite is **NAT**, Network Address Translation.

---

## Source NAT and destination NAT

| | Source NAT (SNAT) | Destination NAT (DNAT) |
|---|---|---|
| Rewrites | where the packet came **from** | where the packet is **going** |
| Direction | outbound | inbound |
| Also called | masquerading, outbound NAT | port forward, port mapping |
| Who starts the conversation | you | someone outside |
| In this lab | FRITZ!Box for the house, OPNsense for the DMZ | game ports and the admin ports |

The security asymmetry follows directly. SNAT happens because you started
something, so it opens nothing. **DNAT is the only mechanism that lets an
outsider start a conversation with something inside**, which is why every port
forward is a deliberate decision and why they are the only rules in this lab
with `source: any`.

In OPNsense 26.7 the menu item is **Firewall → NAT → Destination NAT**. Older
guides and older releases call the same page "Port Forward". Same thing.

---

## Double NAT, and why it wrecked the earlier attempt

Two routers each doing NAT, in a row.

```
internet -> FRITZ!Box [NAT 1] -> second router [NAT 2] -> everything
```

What that costs:

- **Two layers of forwarding.** A port has to be forwarded twice, on two devices
  with two different UIs, to reach one server.
- **Two DHCP servers**, unless you remember to disable one. If you do not,
  devices get addresses from whichever answers first and the network becomes
  intermittently broken in a way that looks like a hardware fault.
- **Split networks.** Devices behind the second router cannot be reached from
  devices in front of it without extra work.
- **Confusing diagnostics.** `traceroute` grows a hop that nobody expects.

This is exactly what happened with a FriendlyElec router placed in line behind
the FRITZ!Box, and it is why "just buy a router" was rejected as a solution.

**The fix was not a better device. It was a different position.** See
[12 · in line versus on a stick](12-network-segmentation.md#in-line-versus-on-a-stick).

The current design still has two NATs, but only the game segment sits behind the
second one. Nothing else in the house is affected, and DHCP is off on both
OPNsense legs so there is exactly one DHCP server on the LAN, as there always
was.

---

## The path a player's packet takes

```
player on the internet
        |
        v
FRITZ!Box, public IP, game port
        |  DNAT #1: rewrite destination to 192.168.178.60
        v
OPNsense WAN leg (192.168.178.60)
        |  DNAT #2: rewrite destination to 10.10.10.20, game port
        |  then the firewall rules decide whether to allow it
        v
wings (10.10.10.20), the game server
```

Two rewrites, one on each router. The reply retraces the path automatically
because both routers keep state for the conversation
([16 · stateful](16-firewalls-and-pf.md#stateful-filtering)).

**Adding a game server therefore means one rule on each device**, plus the
allocation in the panel. Three steps, about two minutes. That is the entire
ongoing cost of the DMZ: one extra click per game compared with the flat setup.

---

## NAT reflection

**Symptom.** From a laptop on the house LAN, connecting to
`192.168.178.60:8080` times out, even though the destination NAT rule is
correct and the same rule works from outside.

**Cause.** My PC and the OPNsense WAN leg are on the same subnet. A packet from
`192.168.178.x` to `192.168.178.60` does not "arrive from outside" the way an
internet packet does, so the packet filter never applies the redirect.

**Fix.** Firewall → Settings → Advanced, enable:

- *Reflection for destination NAT*
- *Automatic outbound NAT for Reflection*

Reflection makes the firewall treat same-subnet traffic the way it treats
external traffic, so the DNAT rules apply.

**It is a convenience feature for this topology, not a security setting.** It
does not open anything to the internet. It only changes how packets that were
already permitted get handled.

The cleaner alternative, and the one that ended up doing the real work here, is
a static route.

---

## Static routes

On the FRITZ!Box: *Heimnetz → Netzwerk → Netzwerkeinstellungen → Erweiterte
Netzwerkeinstellungen → Statische Routen*

```
destination  10.10.10.0/24
via          192.168.178.60
```

### What a route is

> **A route is not a permission. A route is a signpost.**

It says "if you want `10.10.10.x`, go via `.60`". It grants nothing. Packets
sent that way still arrive at a firewall and still face every rule.

### Why it was needed

My PC had no idea `10.10.10.x` existed. Without the route it would hand those
packets to its default gateway, the FRITZ!Box, which would hand them to the
internet, where they die. The route tells every device in the house which way to
go.

### Why it weakens nothing

1. The internet cannot use it. It exists only inside my house and nothing
   outside knows it.
2. It points at a **firewall**, not at the containers. Every packet still faces
   the rules.

### Routing and filtering are separate systems

| Question | Answered by |
|---|---|
| *Which way do I go?* | routing (the static route) |
| *Am I allowed?* | filtering (the firewall rules) |

You need both. A route with no matching pass rule produces packets that arrive
and are silently dropped, which looks exactly like a broken route. A pass rule
with no route produces packets that never arrive at all, which looks exactly
like a broken rule. Knowing they are two independent systems is what makes that
distinguishable.

In this lab the route is on the FRITZ!Box and the matching permission is a
floating pass rule in OPNsense from `192.168.178.0/24` to `10.10.10.0/24`.

---

## Why the "Exposed Host" checkbox is a trap

Consumer routers, the FRITZ!Box included, offer a checkbox usually labelled
*Exposed Host* and sometimes literally labelled *DMZ*.

**It is the opposite of a DMZ.** It forwards every unsolicited port to one
machine, and that machine is still sitting on the normal LAN as a peer of
everything else. It removes protection without adding any separation. It is the
exact configuration this whole project exists to undo.

It stays unticked, for IPv4 and IPv6 both.

---

## Quick reference

| Mechanism | Rewrites addresses? | Grants access? | Where configured |
|---|---|---|---|
| Source NAT | yes, the sender | no | automatic, outbound |
| Destination NAT | yes, the destination | **yes** | FRITZ!Box shares, OPNsense NAT |
| NAT reflection | yes, both | no | OPNsense advanced settings |
| Static route | **no** | **no** | FRITZ!Box static routes |
| Firewall pass rule | no | **yes** | OPNsense firewall rules |

---

**Next:** [16 · Firewalls and `pf`](16-firewalls-and-pf.md)
