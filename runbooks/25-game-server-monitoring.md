# Runbook 25 · Game server monitoring (AMP + Pterodactyl)

**Goal** Every game server's state, players, CPU, RAM, disk and uptime in
Prometheus; who connects from where to which game on the **Homelab · Games**
dashboard; a 🎮 Telegram message when a running server stops.

**Time** 30 minutes.
**Prerequisites** [Runbook 10](10-monitoring-stack.md), the firewall log from
[runbook 21](21-logs-and-crowdsec.md) (for "who connects"), alerts from
[runbook 23](23-alerts-to-telegram.md) (for the 🎮 message). The game panels
(AMP on `10.10.10.21`, Pterodactyl on `10.10.10.22`), see
[docs/20](../docs/20-game-server-hosting.md).
**Reverses cleanly?** Yes: remove the container and the two credentials.

---

## 0 · How it works

There is no good ready-made exporter for this pair of panels (the ones on GitHub
have 0-50 stars, and they would get panel credentials). So the lab has its own:
[`compose/monitoring/game-exporter/game_exporter.py`](../compose/monitoring/game-exporter/game_exporter.py),
about 150 lines, **Python standard library only**, **read-only**. Read it before
running it; that is the point of it being short.

Each time Prometheus asks (every 30 s), it:

1. logs in to AMP and lists the instances (state, players, CPU, RAM, ports);
2. lists the Pterodactyl servers with a client API key (state, CPU, RAM, disk,
   uptime, ports);
3. prints the answers as Prometheus numbers.

| Metric | Meaning |
|---|---|
| `game_server_up{platform, server}` | 1 = running and ready |
| `game_server_state{..., state}` | the panel's word for it: ready, starting, stopped, failed, offline ... |
| `game_server_players` / `_players_max` | players online / slots (AMP only) |
| `game_server_cpu_percent`, `_memory_bytes`, `_disk_bytes` | load per game (disk: Pterodactyl only) |
| `game_server_uptime_seconds` | running for (AMP: since the exporter saw it start) |
| `game_server_port_info{..., host, port}` | which address and port each game listens on |
| `game_exporter_api_up{platform}` | 1 = that panel answered |

If a panel cannot be reached (its node is switched off), its servers are left
out: no data, so no alerts.

Both panels are asked at the same time and each request gives up after 4 s.
So one dead panel (container stopped, node off) only sets its own
`game_exporter_api_up` to 0; the other panel's servers still show up and the
`games` target stays UP. Prometheus waits up to 20 s for this job
(`scrape_timeout: 20s`).

---

## 1 · Credentials with as little power as possible

### AMP

Create a **separate AMP user** (AMP → *Configuration → User Management*) with a
role that may only **view** instances. Do not reuse your admin login or a broad
role: the password sits in `game-exporter.env`, and whatever that user may do,
anyone who reads that file may do. The exporter only calls `Core/Login` and
`ADSModule/GetInstances`.

Both panels are spoken to over plain **HTTP** inside the lab (house LAN → DMZ),
so these logins cross the network unencrypted. That is acceptable only because
they are low-privilege monitoring users; it is one more reason not to reuse an
admin login here.

### Pterodactyl

Use a **separate panel user just for monitoring**, not your own and not an
admin. Add it as a subuser on each server you want to watch with **as few
permissions as possible**: it only has to *see* the server. Do not give it
*Control* (start/stop/console), *Files* or *Backups*. A key for a user with those
can stop servers, read the world files and delete backups, even though the
exporter never would. Then, logged in as that user,
**Account → API Credentials → Create**:

- Description: `game-exporter`
- **Allowed IPs: the address of the machine the exporter runs on**
  (`192.168.178.87`, LXC 102). The key is useless from anywhere else.

Copy the key. It starts with `ptlc_`. (Created through the API instead of the
UI, the answer has the key in two parts, `identifier` and `secret_token`; the
usable key is both joined: `ptlc_ab12...` + `secret...`. Only the second part
gives HTTP 401.)

Check it from LXC 102, and that it is refused elsewhere:

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer <key>" \
  -H "Accept: application/json" -H "User-Agent: check/1" http://10.10.10.22/api/client
# 200 on LXC 102, 403 from any other machine
```

**The `User-Agent` header matters.** The panel's web server refused Python's
default user agent with 403. The exporter sends its own.

---

## 2 · Start the exporter

On LXC 102, in `/opt/monitoring` (the script is in `game-exporter/` there):

```bash
cat > game-exporter.env <<'EOF'
AMP_URL=http://10.10.10.21:8080
AMP_USER=<amp user>
AMP_PASS=<amp password>
PTERO_URL=http://10.10.10.22
PTERO_KEY=ptlc_<the whole key>
EOF
chmod 600 game-exporter.env
chmod 644 game-exporter/game_exporter.py      # the container runs as "nobody"
docker compose -p stacks up -d game-exporter
docker exec stacks-grafana-1 curl -s http://game-exporter:9788/metrics | grep -E '^game_(exporter_api_up|server_up)'
```

Both `game_exporter_api_up` lines must be `1`, and there is one `game_server_up`
line per server.

The container runs as user `nobody`, with a read-only file system and a 48 MB
cap. AMP's URL is **without** `/API`; the script adds it.

---

## 3 · Name the games in the firewall log

The Games dashboard names each internet connection by its destination port
("Minecraft (AMP)", "Zomboid (Pterodactyl)"). The mapping is `GAME_PORTS` in
[`scripts/grafana/queries.py`](../scripts/grafana/queries.py). Get your ports:

```promql
max by (server, platform, host, port) (game_server_port_info)
```

Put them into `GAME_PORTS`, then regenerate the dashboards
([runbook 10](10-monitoring-stack.md#7--grafana)).

**Keep your copy with real ports out of any public repository.** Game forwards
are usually one-to-one, so the internal port tells the world which external port
is open ([docs/99](../docs/99-security-notes.md)). This repository has example
ports in `queries.py` for exactly that reason.

A port missing from the mapping is not lost: its connections show as "other
(port N)".

---

## 4 · The 🎮 alert

Already in `rules.yml` (runbook 23): "Game server stopped" fires when a server
that was running at any time in the last 10 minutes is not running now, for
1 minute. It goes to the `telegram-games` contact point: any time of day, and
without an "OK again" message, because the condition ends by itself after
10 minutes.

**Test it end to end:** start a game server, let it run 3 minutes, stop it.
About 2 minutes later: `🎮 <server> stopped (<panel>)`.

It also fires when **you** stop a server. The panels know who pressed stop
(activity log), but reading it needs one more permission for the monitoring
user. Until then the message says "If you stopped it yourself, ignore this."

---

## 5 · Verify

- Prometheus → *Targets*: `games` **UP**.
- **Homelab · Games**: one tile per server, "Panels" both UP, the port table
  filled. Map, "who connects" and the live feed fill as soon as anybody (or any
  scanner) connects to a game port. Players, CPU and RAM only move while a
  game runs.
- **Overview → Game servers**: the same servers in the timeline.

### Reading the Games dashboard

- **Many IPs, one or two connections each, games stopped**: server-list pings
  and scanners. Every open port gets them, from everywhere, all day.
- **The same IP again and again over an evening**: a player.

---

## If it goes wrong

| Symptom | Cause |
|---|---|
| `game_exporter_api_up{platform="pterodactyl"} 0`, exporter log: 401 | only half of the key (see step 1) |
| ... log: 403 | key's allowed IP is not this machine, or a user agent the panel blocks |
| `..."amp"} 0`, log: login failed | wrong AMP user/password, or `/API` added to `AMP_URL` |
| both 0 | the game node is switched off: expected, nothing alerts |
| connections show as "other (port N)" | port missing in `GAME_PORTS` |
| 🎮 arrives every time you stop a server yourself | known limitation, see step 4 |

---

## Undo

```bash
cd /opt/monitoring && docker compose -p stacks rm -s -f game-exporter && rm game-exporter.env
```

Delete the API key in Pterodactyl (*Account → API Credentials*) and the AMP user
if you made one.
