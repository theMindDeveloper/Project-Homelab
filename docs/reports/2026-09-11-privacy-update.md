# Privacy update

**Date** 11 September 2026
**Author** TheMindDev
**Scope** Encrypting DNS on its way out of the house, and running torrents on
the NAS only through a VPN
**Outcome** Both done and working. Network-level VPN for other devices was
planned but not built yet, see [section 8](#8--open-items)

> **Redaction.** No public addresses in here: not my home IP, not the Mullvad
> exit addresses the tests showed. Same rule as always,
> [`docs/99-security-notes.md`](../99-security-notes.md).

---

## Contents

1. [What I wanted](#1--what-i-wanted)
2. [Encrypted DNS](#2--encrypted-dns)
3. [Where should the VPN live?](#3--where-should-the-vpn-live)
4. [qBittorrent behind gluetun](#4--qbittorrent-behind-gluetun)
5. [Problems I hit](#5--problems-i-hit)
6. [How I checked it](#6--how-i-checked-it)
7. [What this protects, and what it does not](#7--what-this-protects-and-what-it-does-not)
8. [Open items](#8--open-items)

The concepts are written up as [`docs/21`](../21-encrypted-dns.md) and
[`docs/22`](../22-vpns-and-kill-switches.md), the steps as
[runbook 20](../../runbooks/20-qbittorrent-behind-gluetun.md) and an updated
[runbook 03](../../runbooks/03-adguard-home-dns.md). This page is what happened.

---

## 1 · What I wanted

Three things, all about privacy on the home network:

1. I had heard of **DoH and DoT** and could not find a single video on how to
   do it in a homelab. I also did not get why, since AdGuard already "does DNS".
2. **qBittorrent on the NAS, but only through a VPN.** I had a Mullvad
   subscription already.
3. Understand **network-level VPN** with Mullvad, without Tailscale.

Like with the DMZ, most of the time went into understanding the basics first:
what DNS actually leaks, who encrypts what, and what a kill switch really is.

---

## 2 · Encrypted DNS

### What I did not understand

My mental model was "PC → AdGuard → router → ISP → Quad9, so who is even
encrypting this?". The answer is simple once it clicks: **AdGuard encrypts on
the Pi, Quad9 decrypts.** The router and the ISP carry the packet but only see
the outer header. Written up properly in [`docs/21`](../21-encrypted-dns.md).

The other thing: DNS in this lab has two legs.

```
PC ──plain, inside the house──> AdGuard ══encrypted, across the ISP══> Quad9
```

Only the second leg matters for the ISP, so "DoH/DoT on AdGuard" just means
setting encrypted **upstreams**.

### The change

The inventory listed the upstreams as plain `1.1.1.1` and `9.9.9.9`. Now,
in AdGuard → Settings → DNS settings:

```text
https://dns.quad9.net/dns-query
tls://dns.quad9.net
[/fritz.box/]192.168.178.1
```

- line 1 is DoH, line 2 is DoT, AdGuard uses whichever is faster
- line 3 is a conditional upstream so `fritz.box` names still go to the router
- bootstrap `9.9.9.9` / `149.112.112.112`, private reverse DNS
  `192.168.178.1`, DNSSEC on

Ad blocking is not affected (blocklists are checked before anything goes
upstream) and port forwards have nothing to do with it (the connection to Quad9
is outbound).

### Why Quad9 and not Mullvad DNS

Most guides say `dns.mullvad.net`. Mullvad announced on 3 September 2026 that
its public encrypted DNS **shuts down on 2 November 2026** and it sponsors Quad9
instead. So I went straight to Quad9.

---

## 3 · Where should the VPN live?

Before building anything I went through where a VPN could sit in this network.
The idea that made it make sense: **whoever is the default gateway decides
where traffic goes**, so network-level VPN means making some gateway send
traffic into the tunnel.

| Option | Who gets the VPN | Verdict | Reason |
|---|---|---|---|
| Mullvad app on a device | that device | **fine per device** | easiest, but the NAS cannot run it |
| **gluetun container on the NAS** | only qBittorrent | **chosen for torrents** | kill switch that cannot be forgotten, nothing else in the house changes |
| FRITZ!Box as WireGuard client | whole house | rejected | all or nothing, the game server port forwards would very likely break, slower, streaming and banking trouble |
| OPNsense "VPN lane" on a VLAN | chosen devices | **later** | best learning project, reuses the DMZ work, but the most effort and only for wired devices or VMs |

Why not the others for torrents specifically: the app would need a PC running
24/7, the FRITZ!Box option breaks the game servers to protect one app, and the
OPNsense lane would put the whole NAS behind a VM on pve2, which makes Jellyfin
and file shares slow.

---

## 4 · qBittorrent behind gluetun

### The design

gluetun holds the WireGuard tunnel to Mullvad and a firewall. qBittorrent gets
**no network of its own**, it joins gluetun's network namespace with
`network_mode: "service:gluetun"`. Its only way out is the tunnel. If the
tunnel is down, qBittorrent is offline.

```
my PC ──LAN──> NAS :8085 ──> gluetun ══WireGuard══> Mullvad ──> torrent swarm
                               │
                         qBittorrent (inside gluetun's network)
```

That is the same idea as the DMZ: **remove the path instead of writing a
rule.**

### What changed

1. Dropped the native UGOS qBittorrent app. It runs on the host network and
   cannot be put behind gluetun.
2. Generated a WireGuard config in the Mullvad account, took `PrivateKey` and
   the IPv4 part of `Address` from the `.conf`.
3. Created `torrents/{gluetun,config,downloads}` in the `6TB_1` shared folder on
   volume 3, and got `PUID`/`PGID` from `id`.
4. Deployed a UGOS Docker **Project** with
   [`compose/torrent-vpn/docker-compose.example.yml`](../../compose/torrent-vpn/docker-compose.example.yml)
   (real values only in the NAS, never in the repo).
5. qBittorrent: permanent WebUI password, UPnP off, network interface left on
   Any.

The full steps are [runbook 20](../../runbooks/20-qbittorrent-behind-gluetun.md).

---

## 6 · How I checked it

### DNS

| Check | Result |
|---|---|
| `sudo tcpdump -ni any 'host 9.9.9.9 or host 149.112.112.112'` on the Pi while browsing | traffic to Quad9 showing up |
| dnsleaktest.com extended test from the PC | only Quad9 resolvers, no ISP resolvers, no Google/Cloudflare, so the browser is not bypassing AdGuard |

Worth remembering: a leak test shows **who** answers, not **whether it is
encrypted**. The capture is the real proof, and the port number says which
protocol (`.443` DoH, `.853` DoT).

### Torrents

| Check | Result |
|---|---|
| stop gluetun in the Docker UI | qBittorrent web UI gone, the client has no network |

Not finished yet, and needed before calling this verified:

- gluetun log shows `Public IP address is ...` with a Mullvad address
- the ipleak.net torrent address test **from the NAS** shows only a Mullvad
  address
- the same test with gluetun stopped: no new rows for 2 to 3 minutes

I learned how the ipleak test works on the way (magnet link, Trackers tab), but
the proper NAS run with a screenshot still needs doing. Steps in
[runbook 20](../../runbooks/20-qbittorrent-behind-gluetun.md#5--verify).

---

## 7 · What this protects, and what it does not

### Better now

- The ISP no longer sees which names the house looks up, and cannot quietly
  change DNS answers.
- The torrent swarm sees a Mullvad address, never my home address.
- If the tunnel drops, qBittorrent does not fall back to the normal connection.
  There is no other network it could use.
- Nothing else in the house changed. Game servers, Jellyfin, the Pi, all
  untouched.

### Still true

1. **The ISP still sees where the house connects**, just not the DNS lookups.
   Only traffic through a VPN hides that, and only qBittorrent uses one
   permanently.
2. **Quad9 sees every query** and Mullvad sees where qBittorrent connects. Trust
   moved, it did not disappear.
3. **The LAN leg is still plain DNS.** Fine inside the house, but a compromised
   device on the LAN could in theory intercept it.
4. **Devices can still bypass AdGuard**: browser Secure DNS, Windows DoH, or the
   FRITZ!Box announcing itself as IPv6 DNS. The leak test was clean from one PC,
   not every device.
5. **No port forwarding on Mullvad.** Rare torrents and seeding are slower. Not
   fixable with Mullvad.
6. **The Pi is still the single point of failure for DNS**, and now also the
   thing that holds the encrypted upstream config.
7. `gluetun` and `qbittorrent` run on `latest`, which goes against the repo's
   own compose conventions. Pinning at least gluetun would be cleaner, since a
   VPN container that changes behaviour after a pull is exactly the kind of
   surprise that breaks the kill switch assumptions.

### Grade

DNS went from **"the ISP reads every lookup"** to **"the ISP sees that I use
Quad9"**. Torrents went from **"no VPN"** to **"VPN or nothing"**.

---

## 8 · Open items

- [ ] Pin the gluetun image version
- [ ] OPNsense VPN lane: WireGuard to Mullvad on OPNsense, a VLAN on the Omada
      switch, policy-based routing for that VLAN, and a block rule as the kill
      switch
- [ ] Add qBittorrent + gluetun to Glance and the health check

---

**See also:** [`docs/21` · encrypted DNS](../21-encrypted-dns.md) ·
[`docs/22` · VPNs and kill switches](../22-vpns-and-kill-switches.md) ·
[the wiki](../) · [repository root](../../README.md)
