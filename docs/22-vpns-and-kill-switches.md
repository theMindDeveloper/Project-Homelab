# VPNs and kill switches

What a privacy VPN like Mullvad does, what a kill switch is, the four places a
VPN can live in this network, and how gluetun gives one Docker app a VPN with a
kill switch that cannot be forgotten.

Written after the [September 2026 privacy update](reports/2026-09-11-privacy-update.md).
The build is [runbook 20](../runbooks/20-qbittorrent-behind-gluetun.md).

---

## What a VPN does

A VPN tunnel is an envelope inside an envelope. The real packet (to some
website) gets encrypted and put inside an outer packet addressed to the VPN
server. The ISP only sees the outer one: "encrypted traffic to a Mullvad
server". The VPN server unpacks it and sends it on, so the website or torrent
peer sees the VPN server's IP, not mine.

| Who | Without VPN | With VPN |
|---|---|---|
| ISP | every destination IP, SNI, all `http://` content | only "talks to Mullvad", how much, when |
| Website / torrent peers | my home IP | Mullvad's IP |
| VPN provider | nothing | the destinations (same position the ISP had) |

So a VPN moves trust from the ISP to the VPN provider. It does not make me
anonymous if I log in somewhere, and some services (streaming, banking)
block VPN addresses.

### This is not Tailscale

Easy to mix up because Tailscale sells Mullvad exit nodes as an add-on.

| | Tailscale / my own WireGuard | Mullvad |
|---|---|---|
| Purpose | **me reaching my lab** from outside | **hiding my traffic going out** |
| Traffic goes to | my own machines | the internet, via Mullvad |

Mullvad works on its own with plain WireGuard. No Tailscale needed.

---

## WireGuard, the three lines that matter

Mullvad removed OpenVPN on 15 January 2026, so it is WireGuard only now. A
config file from Mullvad's generator looks like this (values made up):

```ini
[Interface]
PrivateKey = <44 characters, ends with =>
Address = 10.66.123.45/32,fc00:bbbb:bbbb:bb01::3:7b2c/128
DNS = 10.64.0.1

[Peer]
PublicKey = <server public key>
AllowedIPs = 0.0.0.0/0,::0/0
Endpoint = <server>:51820
```

| Line | Meaning |
|---|---|
| `PrivateKey` | my identity. Treat it like a password. The website only shows the **public** key, the private one is only inside the downloaded file. |
| `Address` | my IP **inside** the tunnel. Mullvad assigns it to the key. |
| `AllowedIPs = 0.0.0.0/0` | "send **all** traffic into the tunnel". This line is what makes it a full VPN instead of a link to one network. |

Getting the file: Mullvad account → WireGuard configuration → platform Linux →
generate key → **scroll down** and pick a location → download file. Each key
counts as one device, and an account allows **5**.

---

## Kill switch

A tunnel can drop (server restart, network hiccup, reboot order). Without a kill
switch, traffic quietly falls back to the normal connection and the real IP
leaks. Nothing tells you.

**A kill switch is a firewall rule: if it does not go through the tunnel, drop
it.**

There are weak and strong versions:

| Kind | Example | Weak spot |
|---|---|---|
| App setting | VPN app "lockdown mode" | off when you disconnect by hand, depends on the app running |
| Bind the client to the VPN interface | qBittorrent → Advanced → Network interface → the Mullvad adapter | a setting that can be reset or forgotten |
| **No other network exists** | gluetun + `network_mode: service:gluetun` | none worth worrying about, the app has no other road |

The last one is the same idea as the DMZ in
[network segmentation](12-network-segmentation.md): **removing the path beats
writing a rule.**

---

## Where can the VPN live in this network?

The **default gateway** decides where a device's traffic goes. So "network level
VPN" just means "make a gateway send traffic into the tunnel". In this lab that
gateway could be in four places:

| Option | Who gets the VPN | Good | Bad |
|---|---|---|---|
| **1. VPN app** on PC / phone | that device | easiest, also works outside home | only that device, NAS and TV cannot run it |
| **2. gluetun container** | one Docker app | real kill switch, rest of the house untouched, 15 minutes | only for containers |
| **3. FRITZ!Box as WireGuard client** | the whole house | one setting | all or nothing; game server forwards would very likely break because replies leave through the tunnel; streaming and banking annoyances; router CPU limits speed |
| **4. OPNsense "VPN lane"** | devices on a chosen VLAN | per device, proper kill switch, reuses the [DMZ skills](17-opnsense-concepts.md) | most work; only wired devices or VMs; depends on pve2 |

### What I picked, and why

- **Torrents → option 2.** Torrents are the one thing that must always use the
  VPN and must never leak. gluetun guarantees that without touching anything
  else in the house.
- **Browsing when I want it → option 1.**
- **Option 4 later**, as a learning project. It is **policy-based routing**:
  choosing the gateway by *who sent the packet*, not only by where it is going.
- **Not option 3.** Breaks too much for too little.

Why not the others for torrents:

- option 1: the NAS has no Mullvad app, and a PC would have to run 24/7
- option 3: breaks the game servers just to protect one app
- option 4: the whole NAS would have to sit behind OPNsense, which makes
  Jellyfin and file shares slow and ties the NAS to pve2

---

## How gluetun works

Every Docker container normally gets its own **network namespace**: its own
interfaces, routes and firewall. `network_mode: "service:gluetun"` tells Docker
*not* to create one for qBittorrent and to put it inside gluetun's instead.

```
                 gluetun's network namespace
┌──────────────────────────────────────────────────────┐
│  gluetun: WireGuard tunnel + firewall                │
│  qBittorrent: no network of its own, uses this one   │
│                                                      │
│  eth0 (Docker bridge) ── only LAN allowed ── :8085   │
│  tun0 (WireGuard)     ══ everything else ══> Mullvad │
└──────────────────────────────────────────────────────┘
```

Consequences worth knowing, most of which I ran into:

| Consequence | Why |
|---|---|
| **Ports are published on gluetun**, not on qBittorrent | qBittorrent has no network interface of its own to publish on |
| `FIREWALL_OUTBOUND_SUBNETS=192.168.178.0/24` is needed | gluetun's firewall blocks everything that is not the tunnel, including answers to my PC |
| **Stopping gluetun kills the qBittorrent web UI** | the web UI lives in the same namespace. That is the kill switch working, not a bug. |
| **After restarting gluetun, restart qBittorrent** | it is still attached to the old namespace, which no longer has interfaces |
| In qBittorrent, leave Network interface on **Any** | the namespace already forces the tunnel. Binding to an interface here can break torrents (reported on UGOS Pro) |
| A **native NAS app** cannot use this | it runs on the host network, it cannot join a container's namespace |

Compare with a desktop qBittorrent next to the Mullvad app: there, binding the
network interface to the Mullvad adapter **is** the kill switch, because nothing
else forces the tunnel.

---

## Mullvad specifics worth knowing

- **WireGuard only** since 15 January 2026. Old guides with `OPENVPN_USER` are
  outdated for Mullvad.
- **No port forwarding** since 2023. Peers cannot connect *to* me, I can only
  connect to them. Popular torrents are fine, rare ones and seeding are slower.
  Some guides still say otherwise.
- **5 devices (keys)** per account.
- gluetun is official at `github.com/passteque/gluetun` (moved from
  `qdm12/gluetun` in 2026), the image name stayed `qmcgaw/gluetun`. Its README
  says any other site claiming to be official is a scam.

---

## Testing a torrent client's IP

ipleak.net → **Torrent Address detection** gives a magnet link. Every client
that adds it reports to ipleak's tracker, and the page lists the IP each one
used.

1. Right-click the magnet link → **copy link address**. Clicking it opens the
   desktop client instead of the NAS web UI.
2. NAS web UI → File → Add Torrent Link → paste. Make sure it is **started**.
3. Wait 1 to 2 minutes, refresh. Expect a **Mullvad address**, never the home IP.
4. Stop gluetun. **No new rows** should appear.

"Downloading metadata", 0 B and 0 peers is normal for this torrent, it has no
real content. If the page says "No data", check the torrent's **Trackers** tab:
`Working`, `Not contacted yet` (not running) or `Not working` (no internet, so
check the gluetun log).

To compare, add the same magnet to a client without VPN: it shows up with the
home address, the gluetun one with a Mullvad address.

---

## Key points

1. A VPN = **tunnel + route everything into it (`AllowedIPs 0.0.0.0/0`) + kill
   switch.** Without the kill switch it leaks silently.
2. **Whoever is the gateway decides who gets the VPN**: the device, a
   container, or a router.
3. The strongest kill switch is **not having another network**, which is what
   `network_mode: service:gluetun` does.

---

**Back to:** [Encrypted DNS](21-encrypted-dns.md) · [wiki index](README.md)
