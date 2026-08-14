# Proxmox bridges, NICs and VirtIO

`vmbr0`, `vmbr1`, `net0`, `vtnet1`, `eno1`. Five names for what turn out to be
three things. Untangling them is most of what it takes to build a software DMZ.

---

## The three things

| Thing | What it is | Exists physically? |
|---|---|---|
| **NIC** | Network Interface Card, the Ethernet socket on the machine | yes |
| **Bridge** | a switch made of software inside Proxmox | no |
| **Virtual NIC** | a fake network card handed to a guest | no |

Each ThinkCentre M710q in this lab has exactly **one** physical NIC. That single
socket is why the DMZ had to be built in software: there is no second port to
plug a second network into.

---

## Bridges

A Proxmox bridge is a switch. Everything plugged into the same bridge is on the
same layer 2 segment and can talk directly, with no router involved. Everything
in [13](13-addressing-and-osi-layers.md) about switches applies unchanged.

Bridges are defined in `/etc/network/interfaces`:

```
auto vmbr0
iface vmbr0 inet static
    address 192.168.178.77/24
    gateway 192.168.178.1
    bridge-ports eno1          # <-- the real NIC is plugged in
    bridge-stp off
    bridge-fd 0
```

`vmbr0` is created automatically when Proxmox is installed. The real NIC is a
port on it, so anything attached to `vmbr0` is on the house network.

---

## `bridge-ports none`, the whole trick

```
auto vmbr1
iface vmbr1 inet manual
    bridge-ports none          # <-- NO physical port. This is the isolation.
    bridge-stp off
    bridge-fd 0
```

A switch with no uplink cable. Guests attached to it can talk to each other and
to nothing else. There is no path off this bridge that does not go through
something else also attached to it.

**That one line is the separation half of the design.** Not a rule. Not a
policy. An absent road. It cannot be deleted by mistake in the way a firewall
rule can, because there is nothing to delete.

![Proxmox pve2 network: vmbr0 with a port, vmbr1 with none](../assets/screenshots/proxmox-pve2-bridges.png)

*`vmbr0` has `nic0` in the Ports/Slaves column and carries the house address.
`vmbr1` has **nothing** in that column. That empty cell is the isolation.*

> **Note the `10.10.10.254/24` still sitting on `vmbr1` in that screenshot.**
> That is the temporary host address described below, and it has not been
> removed yet. It is a real outstanding item, not an illustration: while it is
> there, the Proxmox host itself has an address inside the sealed segment.

### Applying it

```bash
cp /etc/network/interfaces /etc/network/interfaces.bak   # always
# append the stanza
ifreload -a
ip -br a show vmbr1
```

`ifreload -a` applies the file without rebooting and without dropping `vmbr0`,
which matters when you are doing this over SSH.

**Expect state `UNKNOWN`** on a bridge with no ports and nothing attached yet.
That is normal, not a fault. It changes once a guest is plugged in.

### The temporary host address

During the build I briefly gave `vmbr1` an address on the host
(`10.10.10.254/24`) so I could test the segment before OPNsense existed. It has
to be removed afterwards:

```bash
sed -i '/10.10.10.254/d' /etc/network/interfaces
ifreload -a
```

Leaving it means the Proxmox host itself has a foot in the sealed segment, which
quietly reintroduces exactly the path the design exists to remove.

---

## "No cable" does not mean "no connection"

This confused me badly, so it gets its own section.

`vmbr1` has no physical uplink. But the OPNsense VM is plugged into **both**
bridges. So the sealed segment is not a dead end. It has exactly one door, with
a guard standing in it.

```
house <-cable-> vmbr0 <-> [ OPNsense ] <-> vmbr1 <-> wings, amp, panel
```

Steam traffic goes: wings, to vmbr1, to OPNsense, to vmbr0, to the switch, to
the router, to the internet. Player traffic returns by the same path.

> "No cable" means **no connection that OPNsense does not control.**

---

## Virtual NICs, VirtIO, and the naming

When you give a guest a network card, Proxmox calls it `net0`, `net1`, and so
on, and asks which bridge to plug it into:

```bash
qm create 200 \
  --net0 virtio,bridge=vmbr0 \
  --net1 virtio,bridge=vmbr1
```

Inside the guest, the operating system names the same cards by its own
convention:

| Proxmox says | Linux guest sees | FreeBSD guest sees | Plugged into |
|---|---|---|---|
| `net0` | `eth0` / `ens18` | `vtnet0` | `vmbr0` |
| `net1` | `eth1` / `ens19` | `vtnet1` | `vmbr1` |

Same card, three names, depending on who is looking. Losing an hour to this is
a rite of passage.

### What VirtIO actually is

An emulated card (say, an Intel e1000) makes the hypervisor pretend to be a
specific real chip, register for register, so an unmodified driver works. That
is compatible and slow.

**VirtIO is paravirtualised**: a fake card that does not imitate any real
hardware and instead speaks a protocol designed for virtualisation. The guest
needs a VirtIO driver, and in exchange gets far less overhead per packet.

Linux and FreeBSD both ship VirtIO drivers, so `virtio` is the right default for
everything in this lab. The only time to reach for `e1000` is a guest OS with no
VirtIO support, which in practice means old Windows without the driver disk.

---

## Ordering matters when you assign interfaces

The order you attach NICs is the order the guest enumerates them. In the
OPNsense install, `net0` on `vmbr0` became `vtnet0` and was assigned as WAN;
`net1` on `vmbr1` became `vtnet1` and was assigned as LAN.

Get that backwards and the firewall faces the wrong way: the house becomes the
protected side and the game segment becomes the untrusted internet. Everything
still "works" in the sense that packets move, which is what makes it a
nasty mistake to diagnose. See
[17 · the WAN and LAN naming trap](17-opnsense-concepts.md#wan-and-lan-the-naming-trap).

---

## Moving a guest between bridges

```bash
pct set 105 --net0 name=eth0,bridge=vmbr1,ip=10.10.10.20/24,gw=10.10.10.1
pct reboot 105
```

One command changes the bridge, the address and the gateway together. That is
the moment a container leaves the house network and enters the sealed one, and
it is genuinely instantaneous.

For a VM the equivalent is:

```bash
qm set 200 --net1 virtio,bridge=vmbr1
```

Note the container also needs its DNS server changed, because the LAN resolver
is on the other side of the block rule. See
[19 · LXC migration](19-lxc-migration-and-resources.md).

---

## Checking your work

```bash
ip -br a                      # every interface and address, one line each
brctl show                    # which ports belong to which bridge
cat /etc/network/interfaces   # the persistent definition
ip -br a show vmbr1           # the sealed bridge specifically
```

`brctl show` is the useful one: `vmbr1` should list the guests' `veth`
interfaces and **no physical NIC**. If a physical interface ever appears there,
the isolation is gone and no firewall rule will tell you.

---

**Next:** [15 · NAT, port forwarding and static routes](15-nat-and-port-forwarding.md)
