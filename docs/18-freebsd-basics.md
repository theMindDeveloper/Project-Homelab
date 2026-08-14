# FreeBSD basics, for someone who only knows Linux

Running OPNsense means occasionally dropping to a shell on a system that is not
Linux. It looks close enough to be dangerous: the commands that differ are
mostly the ones you reach for under pressure.

This page is the minimum needed to not waste time.

---

## FreeBSD is not a Linux distribution

Debian, Ubuntu and Alpine are different distributions of the **same kernel**.
FreeBSD is a **different operating system** with its own kernel, its own
userland, and its own history. The overlap is POSIX and the shared heritage of
Unix, not a common codebase.

Practical consequences:

| | Linux | FreeBSD |
|---|---|---|
| Kernel | Linux | FreeBSD |
| Init | systemd (usually) | `rc.d` scripts |
| Packet filter | `iptables` / `nftables` | **`pf`** |
| Package manager | `apt`, `dnf`, `apk` | `pkg` |
| Interface config | `ip` (iproute2) | **`ifconfig`** |
| Interface names | `eth0`, `ens18`, `eno1` | `em0`, `igb0`, **`vtnet0`** |
| Default shell | bash | `sh`, or `csh` for root |
| Filesystems | ext4, xfs, btrfs | **UFS**, ZFS |
| Service control | `systemctl` | `service` |
| Logs | `journalctl` | plain files in `/var/log` |

The row that costs the most time is `ip` versus `ifconfig`. On modern Linux
`ifconfig` is deprecated and often not installed; on FreeBSD it is the correct
and only tool.

And while we are here: **`ifconfig` is Unix, `ipconfig` is Windows.** Typing the
wrong one is a reliable way to lose two minutes and your composure.

---

## The commands that actually get used on OPNsense

### Networking

```sh
ifconfig                      # every interface, addresses, state
ifconfig vtnet0               # one interface
netstat -rn                   # the routing table
sockstat -4 -l                # what is listening, IPv4 only
ping -c 4 10.10.10.20
```

`sockstat` is the FreeBSD equivalent of `ss -tulpn`. It is the fastest way to
answer "is the GUI actually listening, and on which address".

### The packet filter

```sh
pfctl -s rules                # the loaded ruleset
pfctl -s nat                  # NAT rules
pfctl -s state                # the state table
pfctl -s info                 # counters, including how much has been blocked
pfctl -d                      # DISABLE filtering (emergency only)
pfctl -e                      # re-enable
```

See [16 · `pfctl`](16-firewalls-and-pf.md#pfctl-and-getting-back-in-after-locking-yourself-out).

### Services

```sh
service pf status
service configd restart
configctl interface reconfigure wan     # OPNsense-specific
```

`configctl` is OPNsense's own control channel, not FreeBSD. Worth knowing that
it can return `OK` and change nothing, which is exactly what happened during
this build.

### Files worth knowing

| Path | What |
|---|---|
| `/conf/config.xml` | **the entire OPNsense configuration**, one XML file |
| `/var/log/` | plain text logs, no journal |
| `/etc/rc.conf` | FreeBSD boot-time configuration |

`/conf/config.xml` is the whole box. Back it up and you can rebuild from bare
metal in minutes. It is also the file to grep when the GUI and reality disagree.

---

## The trap: saved config versus running state

During this build, `/conf/config.xml` correctly contained
`192.168.178.60` for the WAN interface while `ifconfig vtnet0` still showed an
old DHCP lease. `configctl interface reconfigure wan` returned `OK` and changed
nothing.

**Fix: reboot the VM.** A clean boot applies the saved configuration properly.

> **Lesson: the config file and the running state can disagree. Check both.**

The general diagnostic habit this teaches: when a setting "is definitely
correct" and behaviour says otherwise, verify the *running* state with
`ifconfig` or `pfctl -s rules`, not the file or the GUI form that claims to
describe it.

---

## UFS or ZFS

The installer asks. For this lab the answer is **UFS**.

| | UFS | ZFS |
|---|---|---|
| RAM appetite | minimal | wants GBs for ARC caching |
| Snapshots, checksums | no | yes |
| Useful on | a small virtual disk | real disks you care about |

The OPNsense virtual disk is 20 GB and already sits on LVM-thin on an NVMe,
which handles the redundancy and snapshot story one layer down. ZFS on top would
consume RAM to duplicate work already being done. On bare metal with real disks
the answer flips.

---

## Booting the installer instead of the installed system

A trap that cost two attempts.

**Symptom.** The VM boots to the installer again after you have installed.

**Cause.** SeaBIOS tries the virtual disk, does not immediately find a
bootloader, and falls back to the CD. Setting `--boot order=scsi0` is not always
enough.

**Fix.** Detach the ISO entirely:

```bash
qm set 200 --ide2 none,media=cdrom
```

**How to tell which one you booted**, from the console:

| Line shown | Meaning |
|---|---|
| `Root file system: /dev/iso9660/OPNSENSE_INSTALL` | you are in **live mode**, changes will be lost |
| `Root file system: /dev/gpt/rootfs` | the real installed system |

Anything configured in live mode is gone on the next reboot, which is why the
interface assignment had to be done twice.

### The config importer

If a key is pressed during boot, OPNsense offers to restore a saved
configuration from USB. Press Enter on an empty line to exit it.

---

## FreeBSD tools do not exist on the Proxmox host

Obvious in hindsight, easy to do at 1 a.m.:

```bash
# on pve2, a Debian host:
pfctl -s rules       # command not found
sockstat             # command not found
```

`pfctl` and `sockstat` live on the OPNsense VM. The Proxmox host has `nft`,
`ss`, `ip` and `journalctl`.

The matching mistake in the other direction is running `pct exec`, `qm` or `pvesm`
anywhere other than the Proxmox host, and running `ssh pve2 "..."` from inside a
container that has never heard of the name `pve2`.

**Before typing a command, know which of the three machines you are on:** the
Proxmox host, the OPNsense VM, or a container.

---

**Next:** [19 · LXC migration, memory and CPU](19-lxc-migration-and-resources.md)
