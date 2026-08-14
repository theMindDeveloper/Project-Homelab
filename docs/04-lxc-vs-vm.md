# LXC or VM: how I decide

Proxmox gives you two ways to run a workload and the web UI presents them as
equals. They are not equals. Picking the wrong one is recoverable but annoying,
so this is the reasoning I apply before creating anything.

---

## The one-sentence difference

A **VM** boots its own kernel on emulated hardware. An **LXC container** is a
group of processes on the host's kernel, isolated by namespaces and cgroups.

Everything below follows from that single fact.

---

## What follows from it

| | LXC | VM |
|---|---|---|
| Kernel | shared with the host | its own |
| Boot time | under a second | 10 to 60 seconds |
| Memory overhead | tens of MB | 300 MB and up, before the workload |
| Memory behaviour | uses only what it needs | reserves what you assigned |
| Disk footprint | a few hundred MB | several GB |
| Guest OS | Linux only | anything, including Windows and BSD |
| Custom kernel modules | no | yes |
| Live migration | **no** | yes |
| Snapshot with RAM state | no | yes |
| Hardware passthrough | possible but fiddly | clean |
| Isolation strength | good | stronger |
| Density on one node | dozens | a handful |

---

## My decision rule

**Default to LXC.** Reach for a VM when one of these is true:

1. **It is not Linux.** Windows, a router OS, TrueNAS: VM, no discussion.
2. **It needs its own kernel or kernel modules.** ZFS inside the guest, a VPN
   with a kernel module, anything loading `.ko` files.
3. **You want hardware passed through cleanly.** GPU for transcoding, an HBA for
   a NAS VM, a USB device. Possible in LXC, painful in LXC.
4. **You want live migration.** Only VMs can move between nodes while running.
   If a service must survive a node reboot without downtime, it is a VM.
5. **You do not trust the workload.** Something you did not write, something
   exposed to the internet, something running untrusted user code. A kernel
   escape from a container is a host compromise; from a VM it is not.
6. **You need a full-RAM snapshot.** Only VMs can save the running memory state.

If none of those apply, LXC wins on every axis that matters in a homelab:
density, boot time, memory, and how quickly you can throw one away and rebuild.

---

## Applied to this lab

| Guest | Type | Reason |
|---|---|---|
| LXC 102 `docker` | LXC | Linux, no special kernel needs, benefits from the low overhead. Unprivileged with `nesting=1`. |
| LXC 101 `casaos` | LXC | same |
| LXC 106 `panel` | LXC | plain web app plus database |
| LXC 105 `wings` | LXC | runs Docker itself, so it needs `nesting=1` |
| LXC 107 `amp-server` | LXC | game server manager, Linux only |
| **VM 200 `opnsense`** | **VM** | **rules 1 and 5 together, see below** |

**Everything is an LXC container except the firewall.** That is a deliberate
choice and it has one visible cost: no live migration. Moving a workload to
another node means stopping it and starting it there.

### The one VM, and why the rule bent

Until August 2026 there was not a single VM in the cluster. The DMZ migration
changed that, and it is worth recording *why*, because it is a clean example of
the decision rule doing its job rather than being overridden.

**Rule 1 alone was sufficient.** OPNsense is FreeBSD. An LXC container borrows
the host's Linux kernel, and `pf` is a FreeBSD kernel feature. There is no
configuration that makes a FreeBSD kernel feature run on a Linux kernel. This is
not a hard case; it is what "shares the host kernel" means.

**Rule 5 says the same thing independently.** A firewall whose entire job is to
contain a compromised, internet-facing guest should not itself be a container
borrowing the very kernel it is protecting against. Even if OPNsense had been
Linux, a VM would have been the right answer.

Two independent rules pointing the same way is the signal that the exception is
real rather than convenient. Cost: 2 GB of RAM and a 20 GB disk on pve2.

Reasoning in full: [`17-opnsense-concepts.md`](17-opnsense-concepts.md).
Build: [runbook 13](../runbooks/13-install-the-opnsense-vm.md).

Jellyfin is the interesting case. It would have been the strongest candidate for
a VM, because hardware transcoding on the integrated Intel HD 630 is far easier
to pass through cleanly to a VM than into an unprivileged container. It ended up
somewhere else entirely: as a Docker container on the NAS, right next to the
media library, which removes both the passthrough problem and the network share.

The other thing worth noting about that table: LXC 105, 106 and 107 all now live
in a sealed network segment with no route to the house LAN, which is a different
kind of isolation from the container-versus-VM question and is complementary to
it. Containers isolate *processes from the kernel*; segmentation isolates
*machines from each other*. Getting the second one right is what made the first
one's weaker isolation acceptable for internet-facing workloads. See
[`12-network-segmentation.md`](12-network-segmentation.md).

The open question this raises is k3s. Running it on all three nodes is planned,
and k3s inside an unprivileged LXC needs cgroup delegation and kernel module
work that a VM would not. That is the point where the LXC-only rule will have to
be revisited.

---

## Docker inside LXC

It works, and it is what this lab does. Two conditions:

```bash
pct set <id> --features nesting=1
```

Without `nesting=1` the Docker daemon will not start inside the container.

For an **unprivileged** container you additionally need `keyctl=1` for some
workloads:

```bash
pct set <id> --features nesting=1,keyctl=1
```

**The honest counter-argument:** a lot of people say Docker belongs in a VM, not
in an LXC. Their reasoning is that you are then nesting two container runtimes
with different security models, and an unprivileged LXC plus Docker's own
namespace handling can interact in surprising ways, particularly around storage
drivers and `overlayfs`.

My position: for a homelab where I control every image, the memory savings and
the instant boot are worth it. For anything running untrusted code, I would use
a VM. Knowing that this is a trade-off rather than a settled question is the
point.

---

## Privileged or unprivileged

Always unprivileged, unless proven otherwise.

An unprivileged container maps its root user to a high, unprivileged UID on the
host. Root inside is nobody outside. The cost is that bind mounts from the host
need matching UID mapping, which is the usual reason people give up and switch
to privileged. Fixing the mapping is a ten-minute job and worth doing.

```bash
pct create <id> ... --unprivileged 1
```

You cannot flip an existing container between privileged and unprivileged.
Back up, restore into a new one.
