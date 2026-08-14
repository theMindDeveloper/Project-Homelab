# Firewalls and `pf`: state, order, and the rule that looks wrong

OPNsense's rule editor is a front end. The thing that actually decides whether
a packet lives is `pf`, the FreeBSD packet filter. Three of its properties
explain every rule in this lab, and one of them makes a rule that looks like a
security hole into a one-way door.

---

## Stateful filtering

`pf` tracks **conversations**, not individual packets.

When a packet is allowed and starts a new connection, `pf` records an entry in
its state table. Every subsequent packet belonging to that conversation,
including all the replies coming back the other way, matches the state entry and
is allowed without consulting the rules again.

The consequence that matters:

> A rule allowing traffic in one direction does **not** undo a rule blocking
> traffic in the other.

An attacker cannot exploit a return path, because they cannot *start* the
conversation that creates the state. They can only answer one that was started
from the protected side.

This single property is what makes the design work, and it is the answer to the
question I was most suspicious of. See
[the floating rule](#the-rule-that-looks-wrong) below.

### Practical effects

- You never write "allow the replies". There is no such rule and there should
  not be.
- Blocking outbound traffic to a network genuinely blocks it, even though
  inbound traffic from that network is allowed.
- Changing a rule does not tear down existing connections. Established sessions
  keep working off their state entries until they expire. When testing a new
  block rule, this is why "it did not take effect" is usually "the connection
  you are testing with was already open".

---

## Rule order, and `quick`

`pf` reads rules **top to bottom**.

In OPNsense, the **Quick** flag means "if this rule matches, stop reading and
apply it". Nearly every rule you write should have Quick ticked, and OPNsense
ticks it by default.

The LAN rules in this lab, in order:

| # | Action | From | To | Purpose |
|---|---|---|---|---|
| 1 | **BLOCK** | LAN net | `192.168.178.0/24` | the entire point of the project |
| 2 | PASS | LAN net | any | internet, Steam, package updates |
| 3 | PASS (IPv6) | LAN net | any | leftover default, see below |

Trace two packets:

- **wings to the NAS at `192.168.178.49`** matches rule 1, dies. Rules 2 and 3
  are never read.
- **wings to a Steam server** does not match rule 1 (the destination is not in
  `192.168.178.0/24`), matches rule 2, goes.

![OPNsense firewall rules, block rule above the two default allows](../assets/screenshots/opnsense-lan-rules.png)

*The whole design in one screen. The floating rule permits house to DMZ. On the
LAN interface the red-X block rule sits **above** the two green default allows,
which is the only reason it does anything. Note the third interface rule: the
IPv4 block has no IPv6 twin, which is the gap described below.*

**Order is everything.** When the block rule was first saved at the *bottom* of
the list, rule 2 caught everything first and the block never executed at all.
The rule was present, correct, and completely inert.

> A blocking rule below a matching pass rule is not a weak rule. It is not a
> rule.

### Moving a rule in the OPNsense UI

The arrow icon means **"insert the selected rules here"**, not "move this rule
up". Tick the rule you want to move, then click the arrow on the row you want it
placed *above*. Clicking the arrow on the rule's own row produces
`Cannot move a rule before itself`, which is a confusingly literal error message
for a UI misunderstanding.

---

## Interfaces, and which direction "in" means

Rules are attached to an interface and a direction, and the direction is stated
from the firewall's point of view.

- **LAN / in** means "arriving at OPNsense from the sealed segment". This is
  where the block rule lives, because it is where traffic *leaving* the
  containers is first seen.
- **WAN / in** means "arriving at OPNsense from the house".
- **Floating** rules apply across all interfaces and are evaluated before
  interface rules.

The confusing part is that "in" on the LAN interface catches traffic that is,
from the container's perspective, going out. The interface is the vantage point,
not the destination.

---

## The rule that looks wrong

| Action | From | To |
|---|---|---|
| PASS | `192.168.178.0/24` | `10.10.10.0/24` |

At first sight this appears to undo the block rule. It does not. It permits the
**opposite direction**.

| Scenario | Source | Matches | Result |
|---|---|---|---|
| My PC opens the Pterodactyl panel | `192.168.178.x` | this pass rule | allowed |
| The panel's reply to my PC | `10.10.10.22` | existing **state** | allowed |
| A compromised game server reaches for the NAS | `10.10.10.x` | LAN rule 1 | **blocked** |

The first two are the same conversation. The third is a new one, started from
the wrong side, and there is no rule that permits it.

> **A one-way door. I walk in; they cannot walk out.**

*Tidiness note:* in this lab that rule ended up under Floating rules rather than
on the WAN interface. It works, because floating rules apply everywhere, but it
is broader than strictly necessary and moving it to WAN would be more precise.

---

## Block versus reject

| | Block (drop) | Reject |
|---|---|---|
| What the sender sees | nothing, then a timeout | an immediate "connection refused" |
| Reveals the firewall exists | no | yes |
| Speed of failure | slow | instant |

**Use block for anything facing something untrusted**, which in this lab means
the rule stopping the DMZ from reaching the house. Silence gives a scanner no
information and makes it slow.

Use reject only inside a fully trusted network where a fast, clear failure saves
you debugging time.

This is why every successful verification test in the migration report shows
**exit code 124**, the shell's `timeout` exit status. The connection was
silently dropped. In this project, `124` means it worked.

---

## The leftover IPv6 rule

OPNsense ships default rules allowing LAN to reach anywhere, for IPv4 and IPv6.
The block rule written here is **IPv4 only**, so the default IPv6 allow rule
still sits underneath it.

Harmless today, because the sealed segment has no IPv6 addressing at all. But if
it ever gets one, that rule is an open door that routes straight around the
block. It should be deleted, and it is on the open items list.

**The general lesson:** a firewall policy written for one address family is half
a policy. Every block rule needs its IPv6 twin, or IPv6 needs to be off.

---

## `pfctl`, and getting back in after locking yourself out

`pfctl` is the command-line control for `pf`. The GUI just writes rules for it.

| Command | Effect |
|---|---|
| `pfctl -d` | **disable** filtering entirely |
| `pfctl -e` | enable it again |
| `pfctl -s rules` | list the loaded rules |
| `pfctl -s state` | show the state table |
| `pfctl -s nat` | show the NAT rules |

`pfctl -d` is the emergency exit, reachable from OPNsense console option 8
(Shell). If applying a rule locks you out of the web GUI, disable the filter,
fix the rule, re-enable.

**It is not a fix and must never be left in place.** With `pf` disabled the
firewall is a router with no rules, which means the sealed segment is not
sealed. Full procedure:
[runbook 17](../runbooks/17-recover-from-an-opnsense-lockout.md).

---

## Watching it work

**Firewall → Log Files → Live View**, filtered on `10.10.10`.

Run a reachability test from a container and watch the blocked entries appear in
real time, each showing which rule caught it.

![OPNsense live log showing blocked traffic from the DMZ](../assets/screenshots/opnsense-blocked-live-log.png)

*Source `10.10.10.20` (wings) reaching for `192.168.178.178:443` (AdGuard),
`192.168.178.49:443` (the NAS) and `192.168.178.77:8006` (the Proxmox API).
Every row is `block`, and every row names the rule that caught it. Four
retries per destination, because TCP retransmits into a black hole rather than
failing fast, which is exactly what `block` rather than `reject` buys.*

This visibility is the thing the Proxmox firewall never gave, and it is the
direct reason two earlier attempts at the same goal failed. A rule you cannot
observe is a rule you cannot debug, and a rule you cannot debug eventually gets
switched off.

---

## Aliases, for when this gets tedious

**Firewall → Aliases** lets you name things once and reference the name in
rules:

| Alias | Type | Content |
|---|---|---|
| `wings` | Host | `10.10.10.20` |
| `amp` | Host | `10.10.10.21` |
| `dmz_hosts` | Network | `10.10.10.0/24` |
| `house` | Network | `192.168.178.0/24` |

If a container ever moves, you change the alias once and every rule referencing
it follows. A **Port** alias can also cover several ports in one rule, where the
protocol and the internal and external ports match.

Worth doing before the rule count gets past about a dozen.

---

**Next:** [17 · OPNsense concepts](17-opnsense-concepts.md)
