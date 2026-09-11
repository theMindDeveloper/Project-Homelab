# Runbook 20 · qBittorrent behind gluetun on the NAS

**Goal** qBittorrent on the NAS that can only reach the internet through
Mullvad, and has no internet at all when the VPN is down.

**Time** 30 minutes.
**Prerequisites** A Mullvad account. Docker on UGOS Pro. SSH enabled on the NAS
(only needed for `id`).
**Reverses cleanly?** Yes. Delete the project and the folder.

The why behind every step: [VPNs and kill switches](../docs/22-vpns-and-kill-switches.md).

---

## Read this before starting

**Do not use the native qBittorrent app from the UGOS app center.** It runs on
the NAS's normal network and cannot be put behind gluetun. If it is installed,
uninstall it first so nothing downloads without the VPN by accident.

**Do not use the Docker "create container" form for gluetun.** It lists every
environment variable the image supports (OpenVPN, AmneziaWG, dozens of
providers) and marks the empty ones red. They are all optional. Use a
**Project** with the compose file instead.

---

## 1 · Get the WireGuard values from Mullvad

Mullvad account → **WireGuard configuration**, platform **Linux** →
**Generate key**.

The page now shows a **public** key. That is not the one needed. **Scroll
down**, pick a country and city, then **Download file**.

Open the `.conf` in a text editor:

```ini
PrivateKey = <copy all of it>                       # -> WIREGUARD_PRIVATE_KEY
Address = 10.66.123.45/32,fc00:bbbb:...::7b2c/128   # -> WIREGUARD_ADDRESSES = 10.66.123.45/32
```

Only the IPv4 part of `Address`, before the comma, including `/32`.

Each generated key is one of the 5 devices Mullvad allows per account.

---

## 2 · Folders and user IDs

In the UGOS **Files** app, inside an existing shared folder, create:

```
torrents/
├── gluetun/
├── config/
└── downloads/
```

Creating them in the Files app (not with `sudo mkdir`) means my user owns them,
which avoids permission errors later.

Then SSH in and find the real path and my IDs:

```bash
ls /volume3/6TB_1/torrents   # expect: config  downloads  gluetun
id                           # uid=... -> PUID, gid=... -> PGID
```

If `ls` fails, run `ls /volume3` (or `/volume1`, `/volume2`) and find the shared
folder. The path is always `/volumeN/<shared folder>/...`.

**Spelling has to match exactly**, capitals included. A path that does not exist
gets created by Docker as root, and qBittorrent then cannot write to it.

---

## 3 · Create the project

UGOS **Docker → Project → Create**, paste
[`compose/torrent-vpn/docker-compose.example.yml`](../compose/torrent-vpn/docker-compose.example.yml)
and replace the `${...}` values (the UGOS UI has no `.env`):

| Variable | Value |
|---|---|
| `WIREGUARD_PRIVATE_KEY` | from step 1 |
| `WIREGUARD_ADDRESSES` | from step 1, IPv4 only |
| `${TORRENT_DIR}` | `/volume3/6TB_1/torrents` (three places) |
| `PUID` / `PGID` | from `id` |

Deploy.

**If UGOS warns "shared folders will be created automatically"**: cancel. One of
the volume paths is missing the shared folder name, for example
`/volume3/torrents/...` instead of `/volume3/6TB_1/torrents/...`.

---

## 4 · First login

Docker → Containers → **gluetun → Logs**. Look for:

```
Public IP address is <some address> (Germany, ...)
```

A German Mullvad address means the tunnel is up. Errors or the home address
means stop here, see the table below.

Docker → Containers → **qbittorrent → Logs**, find the temporary WebUI password.

Open `http://<NAS-IP>:8085`, log in as `admin`.

Tools → Options:

| Tab | Setting | Why |
|---|---|---|
| WebUI | username + a real password, **Save** | the temporary one changes every restart. Stored in `config/`, so it survives updates. |
| Connection | UPnP / NAT-PMP **off** | there is nothing to open, Mullvad has no port forwarding |
| Advanced | Network interface: **Any interface** | gluetun already forces the tunnel; binding here can break torrents |
| Downloads | Default save path `/downloads` | the right side of the volume mapping |

---

## 5 · Verify

Ordered so a failure tells you where the problem is.

### 5.1 · The tunnel is up

gluetun log shows a Mullvad address (step 4). Over SSH, the same thing:

```bash
sudo docker exec gluetun wget -qO- https://am.i.mullvad.net/json
# expect "mullvad_exit_ip": true
```

### 5.2 · Torrent traffic uses Mullvad

1. ipleak.net → Torrent Address detection → right-click the magnet link →
   **copy link address** (clicking opens the desktop client instead).
2. qBittorrent web UI → File → **Add Torrent Link** → paste → started.
3. Wait 1 to 2 minutes, refresh ipleak.

Expected: rows with a **Mullvad address**. Never the home address.

### 5.3 · Kill switch

1. Docker UI → **stop gluetun**.
2. The qBittorrent web UI stops loading. **That is correct**, it lives inside
   gluetun's network.
3. On ipleak, wait 2 to 3 minutes and refresh: **no new rows**.

A new row with the home address would be a leak.

### 5.4 · Bring it back

1. **Start gluetun**, wait until the log shows the public IP again.
2. **Restart qbittorrent.** It is still attached to the old namespace.
3. Web UI loads again.

Delete the ipleak test torrent afterwards.

---

## If it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| form wants `OPENVPN_*`, `AMNEZIAWG_*` values | using the container form | use a Project, step 3 |
| gluetun log: WireGuard or key errors | wrong key, or `Address` pasted with the IPv6 part | step 1 again, IPv4 only |
| "shared folders will be created" warning | shared folder missing from a path | fix the path, step 3 |
| qBittorrent cannot save, permission denied | folder created by Docker as root, or wrong PUID/PGID | create the folders in the Files app, check `id` |
| web UI not reachable while gluetun runs | port not published on gluetun, or LAN missing from `FIREWALL_OUTBOUND_SUBNETS` | both belong on gluetun, not qBittorrent |
| web UI dead after gluetun restart | qBittorrent still on the old namespace | restart qbittorrent |
| torrents all "Errored", no peers | Network interface bound to something | set to Any interface |
| ipleak says "No data" | torrent not started, or link copied from an old page load | check the torrent's **Trackers** tab, copy the link again without reloading ipleak |
| rare torrents slow, never "connectable" | Mullvad has no port forwarding | expected, nothing to fix |

---

## Undo

Docker → Project → stop and delete the project. Delete the `torrents` folder.
Revoke the key in the Mullvad account (Devices) so it stops counting toward the
5.

---

**See also:** [VPNs and kill switches](../docs/22-vpns-and-kill-switches.md) ·
[the privacy update report](../docs/reports/2026-09-11-privacy-update.md) ·
[runbooks index](README.md)
