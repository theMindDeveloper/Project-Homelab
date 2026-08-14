# Runbook 17 · Recover from an OPNsense lockout

**Goal** Get back into the OPNsense GUI after a rule, an interface setting or a
reboot has made it unreachable, without destroying the VM.

**Time** 5 minutes, if you know which of the four causes you have.
**Prerequisites** Proxmox console access to VM 200.
**Reverses cleanly?** Yes. Everything here is undone by re-enabling the filter.

Read this **before** you need it. The whole point is that when you need it, the
web interface is gone.

---

## Rule zero: you always have the console

Proxmox → pve2 → 200 (opnsense) → **Console**.

The console is not affected by any firewall rule, because it is a virtual serial
console attached by the hypervisor, not a network service. As long as the VM is
running, you can get in.

> **Open the console from the node that actually hosts the guest.** The Proxmox
> UI is cluster-wide, so you can see the guest from any node, but the console
> websocket connects directly to the hosting node on its own port 8006 with its
> own self-signed certificate. An untrusted certificate makes the socket die
> silently while the rest of the UI works fine, producing "Failed to connect to
> server". Visit `https://192.168.178.77:8006` once and accept it.

---

## Which of the four causes do you have?

Work through these in order. They are ordered by how often they are the answer.

| # | Cause | Distinguishing symptom |
|---|---|---|
| 1 | "Block private networks" / "Block bogon networks" ticked on WAN | never worked, from any house machine |
| 2 | The WAN GUI pass rule is missing | worked until you applied firewall rules |
| 3 | Config saved but not applied to the interface | `ifconfig` disagrees with `/conf/config.xml` |
| 4 | The address is on the wrong interface | "This IP address conflicts with another interface" earlier |

---

## Cause 1 · The two WAN blocking checkboxes

These exist for a firewall facing the real internet, where an RFC1918 source
address arriving from outside is spoofed and should be discarded.

**Yours faces your house, which is a private network.** With them ticked, every
packet from `192.168.178.x` is dropped, including your browser.

**Diagnose**, from console option 8 (Shell):

```sh
pfctl -s rules | head -20        # look for a block on private/bogon sources
```

**Fix.** You need the GUI to untick them, so use the `pfctl -d` route below,
then Interfaces → WAN and uncheck both.

---

## Cause 2 · The GUI pass rule is missing

OPNsense blocks its own web GUI on WAN by default, and your PC is on the WAN
side. If GUI access worked earlier only because filtering was disabled, applying
rules re-enables it and the door closes.

### The emergency exit

Console option **8** (Shell):

```sh
pfctl -d
```

Filtering is now off. The GUI is reachable at `http://192.168.178.60`.

**Add the rule immediately.** Firewall → Rules → WAN → Add:

| Field | Value |
|---|---|
| Action | Pass |
| Interface | WAN, direction in, IPv4 |
| Protocol | TCP |
| Source | `192.168.178.0/24` |
| Destination | **This Firewall** |
| Destination port range | 80 to 80 |

Apply, then re-enable filtering:

```sh
pfctl -e
```

Reload the GUI to confirm it survives with the filter on.

> **`pfctl -d` is not a fix and must never be left in place.** With filtering
> disabled, OPNsense is a router with no rules, which means the sealed segment
> is not sealed. Anything in the DMZ can reach the whole house for as long as it
> stays off.

Set a timer if you have to. Ten minutes with the wall down is a very different
risk from an afternoon.

---

## Cause 3 · Config saved but not applied

The config file and the running state can disagree. During this lab's build,
`/conf/config.xml` correctly held `192.168.178.60` while `ifconfig vtnet0` still
showed an old DHCP lease, and `configctl interface reconfigure wan` returned
`OK` and changed nothing.

**Diagnose:**

```sh
ifconfig vtnet0 | grep inet          # what is actually configured
grep -A5 '<wan>' /conf/config.xml    # what is supposed to be
```

**Fix: reboot the VM.** A clean boot applies the saved configuration properly.

```bash
qm reboot 200                        # from the Proxmox host
```

> **Lesson: verify the running state, not the form that claims to describe it.**

---

## Cause 4 · The address is on the wrong interface

**Symptom:** `This IP address conflicts with another interface`.

One address cannot exist on two interfaces. This happens when `.60` was assigned
to the LAN leg first and you are now trying to put it on WAN.

**Fix:** move the wrong one away first, then assign. Console option 2, set the
incorrectly-assigned interface to something else (or to none), then set the
correct one.

---

## The nuclear options, in increasing order of pain

### Reset to factory defaults, keeping the install

Console option **4**. You lose all rules and interface assignments and start
from [runbook 13 step 4](13-install-the-opnsense-vm.md). Roughly 20 minutes.

### Restore a config backup

If you have `/conf/config.xml` saved somewhere, this is by far the fastest
recovery. **That single file is the entire firewall.**

Export it while things are working: System → Configuration → Backups → Download.
Do this after every rule change that took effort.

### Rebuild the VM

```bash
qm stop 200 && qm destroy 200
```

Then [runbook 13](13-install-the-opnsense-vm.md) from the top. About 45 minutes.

The containers and the bridge are untouched, but the DMZ has no door while the
firewall is gone: guests on `vmbr1` can reach each other and nothing else.

---

## Verify you are properly back

```sh
pfctl -s info | head -3        # Status: Enabled
pfctl -s rules | wc -l         # a plausible number, not zero
ifconfig vtnet0 | grep inet    # 192.168.178.60
ifconfig vtnet1 | grep inet    # 10.10.10.1
```

Then re-run the wall test from
[runbook 14](14-opnsense-dmz-firewall-rules.md#verify). **Do not consider the
incident closed until that test passes again**, because `pfctl -d` left off is
exactly the kind of thing that survives a "well, it works now".

---

## Prevention

- **Back up `/conf/config.xml`** after every meaningful change.
- **Add the WAN GUI rule before applying any other rule**, not after.
- Untick both WAN blocking checkboxes during the initial build, not when locked
  out.
- Keep a second browser tab logged in while editing rules. A live session
  usually survives a change that would block a new one.
- Know where the Proxmox console is before you need it.

---

**Next:** [Runbook 18 · Reconfigure Pterodactyl after a move](18-reconfigure-pterodactyl-after-a-move.md)
