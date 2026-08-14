# Runbook 12 · Create an isolated bridge on a Proxmox node

**Goal** A Linux bridge `vmbr1` on pve2 with no physical uplink, ready to hold
the sealed game segment.

**Time** 5 minutes.
**Prerequisites** root on the Proxmox node. A subnet nothing else uses.
**Reverses cleanly?** Yes. Remove the stanza, `ifreload -a`. Nothing else on the
node is touched.

This is the **separation** half of the DMZ. The reasoning is in
[`docs/12-network-segmentation.md`](../docs/12-network-segmentation.md); the
mechanics of bridges are in
[`docs/14-proxmox-bridges-and-nics.md`](../docs/14-proxmox-bridges-and-nics.md).

---

## 0 · Decide, before you type anything

| Decision | This lab | Why it matters |
|---|---|---|
| Which node | `pve2` | a software bridge exists on **one host only**. Every guest attached to it must live there. |
| Bridge name | `vmbr1` | `vmbr0` already exists and has the real NIC |
| Subnet | `10.10.10.0/24` | a different *family* from `192.168.178.x`, so every address says which side it is on |
| Firewall address | `10.10.10.1` | taken by OPNsense later, not now |

Confirm the subnet is genuinely unused anywhere in the lab, including on the
router's static routes and any VPN.

---

## 1 · Back up the network configuration

Not optional. A malformed `/etc/network/interfaces` plus `ifreload` can take the
node off the network, and you are probably doing this over SSH.

```bash
cp /etc/network/interfaces /etc/network/interfaces.bak
```

---

## 2 · Add the bridge

```bash
cat >> /etc/network/interfaces << 'STANZA'

auto vmbr1
iface vmbr1 inet static
    address 10.10.10.254/24
    bridge-ports none
    bridge-stp off
    bridge-fd 0
STANZA
```

| Line | Why |
|---|---|
| `bridge-ports none` | **the whole point.** No physical port, so no path off this bridge. |
| `bridge-stp off` | spanning tree solves loops between physical switches. There are none here. |
| `bridge-fd 0` | forwarding delay. Zero, because there is no topology to converge. |
| `address 10.10.10.254/24` | **temporary**, so you can test the segment before OPNsense exists. Removed in step 5. |

If you do not need to test before installing the firewall, use
`iface vmbr1 inet manual` with no address and skip step 5 entirely. That is the
cleaner end state.

---

## 3 · Apply it

```bash
ifreload -a
```

`ifreload` applies the file without rebooting and without disturbing `vmbr0`.
This is why it is safe to run over SSH; `systemctl restart networking` is not.

---

## 4 · Verify

```bash
ip -br a show vmbr1
brctl show
cat /etc/network/interfaces
```

| Check | Expected |
|---|---|
| `vmbr1` exists | yes |
| Its state | **`UNKNOWN`** |
| `brctl show` interfaces column for `vmbr1` | **empty** |
| `vmbr0` still has an address and you are still connected | yes |

**`UNKNOWN` is correct, not a fault.** A bridge with no ports and nothing
attached has no link state to report. It changes once a guest is plugged in.

**If a physical interface ever appears under `vmbr1` in `brctl show`, the
isolation is gone** and no firewall rule will tell you. That is the one check
worth repeating after any network change on this node.

---

## 5 · Remove the temporary host address, once the firewall exists

Do this after [runbook 13](13-install-the-opnsense-vm.md), not before.

```bash
sed -i '/10.10.10.254/d' /etc/network/interfaces
ifreload -a
ip -br a show vmbr1        # no address now
```

**Why it matters:** leaving it means the Proxmox host itself has a foot in the
sealed segment. That quietly reintroduces exactly the path the design exists to
remove, and it does so on the one machine that also controls the firewall.

---

## Verify, end to end

Run after a guest has been attached (see
[runbook 15](15-move-an-lxc-into-the-dmz.md)):

```bash
brctl show vmbr1                    # lists veth interfaces, no physical NIC
ip -br a show vmbr1                 # no address on the host
pct exec 105 -- ping -c2 10.10.10.1 # the guest reaches the firewall
```

---

## If it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| SSH dies on `ifreload -a` | typo in the stanza broke `vmbr0` too | physical console, `cp /etc/network/interfaces.bak /etc/network/interfaces`, `ifreload -a` |
| `vmbr1` does not appear | `auto vmbr1` line missing, or the stanza is indented wrong | interface lines are indented 4 spaces, `auto` and `iface` are not |
| Guests on `vmbr1` cannot reach each other | they are on different subnets, or one has no gateway | check `ip -br a` inside each guest |
| `bridge-ports none` rejected | very old `ifupdown` | use `bridge-ports regex ^$` on legacy systems |
| Address conflict warning | `10.10.10.254` clashes with the firewall's later `.1` | it does not, but do remove the temporary address once OPNsense is up |

---

## Undo

```bash
# detach any guests first
pct set 105 --net0 name=eth0,bridge=vmbr0,ip=dhcp

# then remove the bridge
cp /etc/network/interfaces.bak /etc/network/interfaces
ifreload -a
```

---

**Next:** [Runbook 13 · Install the OPNsense VM](13-install-the-opnsense-vm.md)
