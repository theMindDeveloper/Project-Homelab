# Runbook 14 · Write the DMZ firewall rules

**Goal** The sealed segment can reach the internet and cannot reach the house.
I can reach the sealed segment from the house. The OPNsense GUI is reachable
from the house and invisible from the internet.

**Time** 20 minutes.
**Prerequisites** [Runbook 13](13-install-the-opnsense-vm.md) done, GUI
reachable at `192.168.178.60`.
**Reverses cleanly?** Yes. Each rule can be disabled with its toggle, without
deleting it.

The reasoning behind every rule, especially the one that looks like a hole, is
in [`docs/16-firewalls-and-pf.md`](../docs/16-firewalls-and-pf.md). Read that
first if any rule here looks wrong to you. It should.

---

## The four rules, and what each is for

| # | Where | Action | From | To | Purpose |
|---|---|---|---|---|---|
| 1 | LAN | **BLOCK** | LAN net | `192.168.178.0/24` | the entire point of the project |
| 2 | LAN | PASS | LAN net | any | internet, Steam, package updates |
| 3 | Floating | PASS | `192.168.178.0/24` | `10.10.10.0/24` | so I can administer the segment |
| 4 | WAN | PASS | `192.168.178.0/24` | This Firewall, port 80 | the GUI, LAN-only |

Remember that **"LAN" is the sealed side**. From OPNsense's point of view the
house is the outside world.

---

## 1 · The block rule

**Firewall → Rules → LAN → Add.**

| Field | Value |
|---|---|
| Action | **Block** |
| Interface | LAN |
| Direction | in |
| TCP/IP Version | IPv4 |
| Protocol | any |
| Source | **LAN net** |
| Destination | Single host or network → `192.168.178.0` / `24` |
| Quick | **ticked** |
| Description | `BLOCK dmz -> house LAN` |

Save. **Do not apply yet.**

The finished result, for reference:

![OPNsense firewall rules](../assets/screenshots/opnsense-lan-rules.png)

### Then move it to the top

The two default allow rules already exist below where new rules land.

**Firewall → Rules → LAN**, tick your new rule, then click the arrow **on the
row you want it placed above** (the first default allow rule).

> The arrow means "insert the selected rules **here**", not "move this rule up".
> Clicking the arrow on the rule's own row gives you
> `Cannot move a rule before itself`.

**Order is everything.** `pf` reads top to bottom and stops at the first match
because Quick is ticked. Saved at the bottom, this rule is not weak, it is
inert: rule 2 catches everything first and the block never executes.

Now click **Apply**.

**Use Block, not Reject.** Block drops silently and gives a scanner nothing;
Reject answers "connection refused" and confirms the firewall exists. Every
successful test below shows a timeout for this reason.

---

## 2 · The outbound pass rule

This is one of the OPNsense defaults and is usually already present as
*Default allow LAN to any rule*. Confirm it exists and sits **below** the block
rule.

If it is missing:

| Field | Value |
|---|---|
| Action | Pass |
| Interface | LAN, direction in, IPv4 |
| Source | LAN net |
| Destination | any |
| Description | `PASS dmz -> internet` |

### Delete the IPv6 default

There is also a *Default allow LAN IPv6 to any rule*. The block rule you just
wrote is **IPv4 only**, so that IPv6 rule routes straight around it the moment
the segment ever gets an IPv6 address.

**Delete it**, or write an IPv6 twin of the block rule. A firewall policy
written for one address family is half a policy.

---

## 3 · The floating rule, so you can administer the segment

**Firewall → Rules → Floating → Add.**

| Field | Value |
|---|---|
| Action | Pass |
| Interface | WAN |
| Direction | in |
| Protocol | any |
| Source | `192.168.178.0/24` |
| Destination | `10.10.10.0/24` |
| Quick | ticked |
| Description | `PASS house -> dmz (admin)` |

**This does not undo the block rule.** It permits the opposite direction.

| Scenario | Source | Matches | Result |
|---|---|---|---|
| My PC opens the panel | `192.168.178.x` | this rule | allowed |
| The panel's reply | `10.10.10.22` | existing state | allowed |
| Compromised game server reaches for the NAS | `10.10.10.x` | LAN rule 1 | **blocked** |

Because `pf` is stateful, replies to conversations you start flow back without
needing their own rule, and an attacker cannot exploit that because they cannot
start the conversation.

> **A one-way door. You walk in; they cannot walk out.**

*Tidiness note:* placing this on the WAN interface rather than under Floating
would be more precise, since floating rules apply across all interfaces. It
works either way.

---

## 4 · The GUI rule

OPNsense blocks its own web GUI on WAN by default, and your PC is on the WAN
side. Without this rule you lose the GUI the moment filtering is active.

**Firewall → Rules → WAN → Add.**

| Field | Value |
|---|---|
| Action | Pass |
| Interface | WAN, direction in, IPv4 |
| Protocol | TCP |
| Source | `192.168.178.0/24` |
| Destination | **This Firewall** |
| Destination port range | 80 to 80 |
| Description | `PASS house -> GUI` |

Restricted to the house, and the router forwards nothing to it, so it is
invisible from the internet.

---

## 5 · Enable NAT reflection

**Firewall → Settings → Advanced**, tick:

- *Reflection for destination NAT*
- *Automatic outbound NAT for Reflection*

Needed because your PC shares a subnet with the OPNsense WAN leg, so packets to
`192.168.178.60` do not arrive the way an internet packet would and the port
forwards would otherwise never apply. It is a convenience feature for this
topology, not a security setting.

---

## 6 · Add the static route on the router

FRITZ!Box: *Heimnetz → Netzwerk → Netzwerkeinstellungen → Erweiterte
Netzwerkeinstellungen → Statische Routen*.

| Field | Value |
|---|---|
| Network | `10.10.10.0` |
| Subnet mask | `255.255.255.0` |
| Gateway | `192.168.178.60` |

**A route is a signpost, not a permission.** It tells every device in the house
which way to reach `10.10.10.x`. Without it, your PC hands those packets to its
default gateway, which throws them at the internet, where they die. Rule 3 above
is the matching permission; you need both.

It weakens nothing: the internet cannot use it (it exists only inside your
house), and it points at a firewall, not at the containers.

---

## Verify

Run after guests exist in the segment
([runbook 15](15-move-an-lxc-into-the-dmz.md)).

### Test 1 · The wall holds

```bash
for target in 192.168.178.77:8006 192.168.178.20:8006 192.168.178.49 192.168.178.178 192.168.178.1; do
  echo -n "$target -> "
  pct exec 105 -- timeout 4 curl -sk -o /dev/null "https://$target" 2>/dev/null \
    && echo REACHABLE || echo blocked
done
```

**Expected: every line `blocked`.** Exit code 124 means `timeout` fired, which
is the desired outcome. A single `REACHABLE` means the rule order is wrong.

### The exact three commands used

The loop above is tidy. These are the three commands actually typed on the day,
one per target, and they are the ones worth memorising because you can run them
from anywhere without a shell loop:

```bash
pct exec 105 -- timeout 4 curl -sk https://192.168.178.77:8006      # Proxmox API
pct exec 105 -- timeout 4 curl -sk https://192.168.178.49           # the NAS
pct exec 105 -- timeout 4 curl -sk https://192.168.178.178          # AdGuard DNS
```

**Every one must produce no output and exit 124.** Check with `echo $?`
immediately after. Those three targets are chosen deliberately: the hypervisor
that controls every guest, the box holding every backup, and the resolver for
the whole house. If a game server cannot reach those three, the interesting part
of the blast radius is gone.

`-s` silences the progress meter, `-k` skips certificate validation (all three
are self-signed), and `timeout 4` is what turns an indefinite hang into a
testable exit code.

### Test 2 · Scan the house from inside the segment

The convincing one.

```bash
pct exec 105 -- bash -c 'apt-get update -qq && apt-get install -y -qq nmap'
pct exec 105 -- nmap -sn --host-timeout 5s 192.168.178.0/24
```

Before the migration this listed every device in the house. Now it should find
nothing. Remove `nmap` afterwards if you prefer a clean container.

### Test 3 · The internet still works

```bash
pct exec 105 -- timeout 5 curl -s -o /dev/null -w 'steam=%{http_code}\n' https://store.steampowered.com
```

### Test 4 · Watch it live

**Firewall → Log Files → Live View**, filter on `10.10.10`. Re-run test 1 and
watch blocked entries appear in real time, each naming the rule that caught it.

![OPNsense live log showing blocked traffic from the DMZ](../assets/screenshots/opnsense-blocked-live-log.png)

*What a passing test looks like from the firewall's side: `10.10.10.20` reaching
for AdGuard, the NAS and the Proxmox API, every row saying `block`.*

This visibility is the thing the Proxmox firewall never gave, and the direct
reason two earlier attempts at this failed.

### Test 5 · What the world sees

From a phone on mobile data, use an external port scanner against your public
address.

**Expected:** game ports open, everything else closed. Specifically **8006,
8080, 9090 and 80 must all be closed.**

---

## If it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Block rule has no effect | it is below a matching pass rule | move it to the top; `pf` stops at the first match |
| Cannot reach the GUI after Apply | the WAN GUI rule is missing | console option 8, `pfctl -d`, add the rule, `pfctl -e` |
| `Cannot move a rule before itself` | clicked the arrow on the rule's own row | tick the rule, click the arrow on the destination row |
| Containers reach the internet but resolve nothing | DNS server is inside the blocked range | point them at a public resolver, or run Dnsmasq on the LAN leg |
| Port forwards work from outside, not from your PC | NAT reflection off | enable both reflection options |
| Can route to `10.10.10.x` but everything times out | static route exists, pass rule does not | add the floating rule |
| Blocked traffic still gets through for a while | existing state entries | `pfctl -F state`, or wait for them to expire |

---

## Undo

Toggle each rule off rather than deleting it, so the reasoning stays visible in
the UI. To fully revert, delete rules 1, 3 and 4, restore the IPv6 default, turn
off reflection, and remove the static route on the router.

---

**Next:** [Runbook 15 · Move an LXC into the DMZ](15-move-an-lxc-into-the-dmz.md)
