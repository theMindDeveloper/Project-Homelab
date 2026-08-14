# Runbook 16 · Publish a game server port through the DMZ

**Goal** A game server inside the sealed segment is reachable by players on the
internet, and nothing else becomes reachable.

**Time** 2 minutes per game.
**Prerequisites** [Runbook 14](14-opnsense-dmz-firewall-rules.md) done. The game
server exists and is listening.
**Reverses cleanly?** Yes. Delete the two rules and the port is closed again.

> **Note on this page.** Real external port numbers are deliberately not
> published in this repository. Placeholders in the shape `<external-port>` are
> used throughout. The rule is in
> [`docs/99-security-notes.md`](../docs/99-security-notes.md) and it is enforced
> by `scripts/check-secrets.sh`.

---

## The path a player's packet takes

```
player on the internet
        |
        v
FRITZ!Box, public address, <external-port>
        |  DNAT #1 -> 192.168.178.60
        v
OPNsense WAN leg
        |  DNAT #2 -> 10.10.10.20:<internal-port>
        |  then the firewall rules decide
        v
the game server
```

**Two rewrites, one on each router.** That is why publishing a game takes two
rules instead of one. The reply retraces the path automatically because both
routers hold state for the conversation.

---

## 0 · Decide, before you type anything

| Decision | How to pick |
|---|---|
| Which host | `10.10.10.20` for Pterodactyl games, `10.10.10.21` for AMP games |
| Internal port | whatever the game is actually bound to |
| External port | can differ from the internal one; differing is slightly better, since it breaks trivial fingerprinting |
| **Protocol** | **TCP, UDP or both.** Get this wrong and a scanner says "open" while no player can join. |

Confirm what is actually listening before forwarding anything at it:

```bash
pct exec 105 -- ss -tulnp | grep <internal-port>
pct exec 107 -- ss -tulnp | grep <internal-port>
```

`-t` is TCP, `-u` is UDP. If the port only appears under one of them, forward
only that protocol.

---

## 1 · The OPNsense destination NAT rule

**Firewall → NAT → Destination NAT → Add.**

(In older releases and older guides this page is called "Port Forward". Same
thing.)

| Field | Value |
|---|---|
| Interface | **WAN** |
| TCP/IP Version | IPv4 |
| Protocol | TCP, UDP, or TCP/UDP, matching step 0 |
| Source | **any** |
| Destination | **WAN address** |
| Destination port range | `<external-port>` to `<external-port>` |
| Redirect target IP | `10.10.10.20` |
| Redirect target port | `<internal-port>` |
| NAT reflection | use system default |
| Filter rule association | **Add associated filter rule** |
| Description | `game: <name>` |

**Source `any` is unavoidable here.** Players come from the internet and you
cannot know their addresses. This is the one category of rule in the lab that is
open to the world, and it is why the segment exists.

**"Add associated filter rule"** creates and maintains the matching pass rule
for you. Without it the packet gets rewritten and then dropped, which is a
uniquely annoying failure to debug.

### Use the copy icon

For the second and every subsequent game, click the **copy icon** on an existing
rule and change only the ports and the target. That reduces the whole step to
three fields.

---

## 2 · The FRITZ!Box share

*Internet → Freigaben → Portfreigaben*.

**Attach every share to one device entry: OPNsense at `192.168.178.60`.**

| Field | Value |
|---|---|
| Device | OPNsense (`192.168.178.60`) |
| Protocol | matching step 0 |
| Port to device | `<external-port>` |
| Port externally desired | `<external-port>` |

Everything published points at the firewall. Nothing on the house LAN is ever a
forward target again. That single property is the difference between this design
and the one it replaced.

**Leave "Exposed Host" unticked**, for IPv4 and IPv6 both. It sounds like a DMZ
and is the opposite: it forwards every unsolicited port to one machine that is
still a peer of everything else on the LAN.

---

## 3 · Admin ports are different

Ports for the panel and the wings API are **not** published to the world. They
are destination NAT rules with a restricted source, so they work from the house
and do not exist from the internet.

| External on `.60` | Source | Target |
|---|---|---|
| `8080/tcp` | `192.168.178.0/24` | `10.10.10.22:80` (panel) |
| `9090/tcp` | `192.168.178.0/24` | `10.10.10.20:9090` (wings API) |

No FRITZ!Box share is created for these. Source `any` is for players; source
restricted is for you.

---

## Verify

```bash
# 1 · the game is actually listening inside the segment
pct exec 105 -- ss -tulnp | grep <internal-port>

# 2 · reachable from the house through the firewall
nc -vz 192.168.178.60 <external-port>          # TCP
nc -vzu 192.168.178.60 <external-port>         # UDP
```

3. **From outside.** Use a phone on mobile data, not the house Wi-Fi, or an
   external port checker. Testing from inside the house exercises NAT
   reflection, not the real path.
4. **Actually join the game.** A port check proves a packet arrives. Only a real
   client proves the protocol and the application agree.
5. **Confirm nothing else opened.** Re-scan from outside: ports **8006, 8080,
   9090 and 80 must all be closed.**

---

## If it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Port shows closed from outside | FRITZ!Box share missing or pointing at the wrong device | every share attaches to `192.168.178.60` |
| Port shows open, players cannot join | wrong protocol | check `ss -tulnp`; most game traffic is UDP |
| Works from a phone, not from your PC | NAT reflection off | Firewall → Settings → Advanced, enable both reflection options |
| Packet arrives and is dropped | no associated filter rule | edit the NAT rule, set "Add associated filter rule" |
| Works, then stops after the game restarts | the server bound to a different address or port | check the allocation in the panel |
| Works for one game, not the next | copied rule still has the old target | check the redirect target IP and port |
| Everything is open from outside | Exposed Host got ticked | untick it, IPv4 and IPv6 |

---

## Undo

Delete the destination NAT rule in OPNsense (which removes the associated filter
rule with it) and delete the FRITZ!Box share. The port is closed again
immediately; existing sessions drain from the state table.

---

## Making this cheaper

**Firewall → Aliases.** Define `wings = 10.10.10.20` and `amp = 10.10.10.21`
once and reference them by name. If a container moves, change the alias once and
every rule follows. A **Port** alias can cover several ports in one rule where
the protocol and the internal and external ports match.

The FRITZ!Box side has no cloning and stays manual while it remains the edge
router.

---

**Next:** [Runbook 17 · Recover from an OPNsense lockout](17-recover-from-an-opnsense-lockout.md)
