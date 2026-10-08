"""Homelab · Games: who plays from where, which game, uptime, players, load."""
from lib import *
from queries import *

S = "{{server}} ({{platform}})"
RUN = [{"type": "value", "options": {"0": {"text": "stopped", "color": "#555555", "index": 0},
                                     "1": {"text": "running", "color": GOOD, "index": 1}}}]

def build(path):
    D = Dash("Homelab · Games", "homelab-games", ["homelab", "games"], links=NAV, refresh="30s", time_from="now-24h",
             desc="Game servers on AMP (10.10.10.21) and Pterodactyl (10.10.10.20): who plays, from where, uptime, load.")
    L, P = Dash.loki, Dash.prom

    # ---- right now ----------------------------------------------------------------------------
    D.row("Right now")
    D.stat("Servers running", [P('count(max by (server, platform) (game_server_up) == 1) or vector(0)', instant=True)], 0, 4,
           th=thr(NEUTRAL, 1, GOOD), decimals=0)
    D.stat("Players online", [P('sum(game_server_players) or vector(0)', instant=True)], 4, 4, th=thr(NEUTRAL, 1, INFO),
           decimals=0, desc="AMP games only: Pterodactyl doesn't report players.")
    D.stat("Connections from internet", [L(cnt(GAMEN), instant=True)], 8, 4, th=thr(GAME_C),
           desc="In the selected time range (firewall log).")
    D.stat("Unique player IPs", [L(uniq(GAMEN), instant=True)], 12, 4, th=thr("purple"))
    D.stat("Countries", [L(uniq(GAMEN + ' | country!=""', by="country"), instant=True)], 16, 4, th=thr("#8F3BB8"))
    D.stat("Panels", [P('max by (platform) (game_exporter_api_up)', "{{platform}}", instant=True)], 20, 4, mappings=UPDOWN,
           th=thr(BAD, 1, GOOD), text_mode="value_and_name", desc="DOWN = panel not reachable (usually: pve2 is off).")
    D.next_row(4)
    D.stat("Servers", [P('max by (server, platform) (game_server_up)', S, instant=True)], 0, 24, h=4, mappings=RUN,
           th=thr("#555555", 1, GOOD), text_mode="value_and_name")
    D.next_row(4)

    # ---- who plays from where -------------------------------------------------------------------
    D.row("Who connects from where")
    D.geomap("Players' locations", [L(f'sum by (lat, lon, city, country, game) (count_over_time({GAMEN} | lat!="" [$__range]))', instant=True)],
             0, 14, 13, desc="Each dot = a city connecting to a game server. Bigger = more connections. Hover for the game.",
             transformations=[{"id": "labelsToFields", "options": {"mode": "columns"}}, {"id": "merge", "options": {}},
                              {"id": "convertFieldType", "options": {"conversions": [
                                  {"targetField": "lat", "destinationType": "number"},
                                  {"targetField": "lon", "destinationType": "number"}]}},
                              {"id": "organize", "options": {"renameByName": {"Value": "Connections"}}}],
             layers=[{"type": "markers", "name": "Players", "tooltip": True,
                      "location": {"mode": "coords", "latitude": "lat", "longitude": "lon"},
                      "config": {"showLegend": False, "style": {
                          "size": {"field": "Connections", "min": 5, "max": 28, "fixed": 6},
                          "color": {"fixed": GAME_C}, "opacity": 0.75,
                          "symbol": {"mode": "fixed", "fixed": "img/icons/marker/circle.svg"},
                          "symbolAlign": {"horizontal": "center", "vertical": "center"}}}}])
    D.bargauge("Connections per game", [L(f'sum by (game) (count_over_time({GAMEN} [$__range]))', "{{game}}", instant=True)],
               14, 10, 6, unit="none", mn=0, mx=None, th=thr(GAME_C), color={"mode": "continuous-BlPu"})
    D.y += 6
    D.bargauge("Top countries", [L(f'topk(8, sum by (country) (count_over_time({GAMEN} | country!="" [$__range])))', "{{country}}", instant=True)],
               14, 10, 7, unit="none", mn=0, mx=None, th=thr(INFO), color={"mode": "continuous-GrYlRd"})
    D.y -= 6
    D.next_row(13)
    D.table("Who connects", [L(f'topk(25, sum by (src_ip, country, city, game) (count_over_time({GAMEN} [$__range])))', instant=True)],
            0, 14, 10, [("src_ip", "IP", "string", None, None, 130), ("game", "Game", "string", None, None),
                        ("city", "City", "string", None, None), ("country", "Country", "string", None, None),
                        ("Value", "Connections", "none", thr(GAME_C), BAR_BASIC)],
            sort=[{"displayName": "Connections", "desc": True}], labels_to_fields=True,
            desc="Many IPs with few connections = server-list pings and scanners. Real players connect again and again.")
    D.logs("Live: connections to game servers",
           [L(GAMEN + r' | line_format "{{ .game }}  ·  {{ .src_ip }}  ·  {{ .city }}, {{ .country }}  ({{ .proto }})"')],
           14, 10, 10)
    D.next_row(10)
    D.ts("Connections per game over time", [L(f'sum by (game) (count_over_time({GAMEN} [$__auto]))', "{{game}}")],
         0, 24, 7, bars=True, stack=True)
    D.next_row(7)

    # ---- uptime ---------------------------------------------------------------------------------
    D.row("Uptime")
    D.state_timeline("When were they running?", [P('max by (server, platform) (game_server_up)', S)], 0, 24, 7, mappings=RUN,
                     desc="Green = running and ready. Empty = panel not reachable (pve2 off).")
    D.next_row(7)
    D.bargauge("Uptime in the selected time", [P('avg by (server, platform) (avg_over_time(game_server_up[$__range]))', S, instant=True)],
               0, 8, 7, th=thr(NEUTRAL, 0.01, INFO), mode="gradient", desc="Share of the time range the server was running.")
    D.bargauge("Hours running in the selected time", [P('max by (server, platform) (sum_over_time(game_server_up[$__range])) * 30', S, instant=True)],
               8, 8, 7, unit="s", mn=0, mx=None, th=thr(INFO), mode="gradient", desc="Scraped every 30 s.")
    D.bargauge("Running for (now)", [P('max by (server, platform) (game_server_uptime_seconds)', S, instant=True)],
               16, 8, 7, unit="s", mn=0, mx=None, th=thr(INFO), mode="gradient",
               desc="Pterodactyl: from the panel. AMP: since the exporter saw it start.")
    D.next_row(7)

    # ---- players + load -------------------------------------------------------------------------
    D.row("Players & load")
    D.ts("Players online (AMP)", [P('max by (server) (game_server_players{platform="amp"})', "{{server}}")], 0, 12, 8, mn=0,
         desc="Pterodactyl doesn't report players.")
    D.ts("CPU per game", [P('max by (server, platform) (game_server_cpu_percent) / 100', S)], 12, 12, 8, unit="percentunit", mn=0,
         desc="AMP: % of the game's CPU limit. Pterodactyl: % of one core (can be > 100%).")
    D.next_row(8)
    D.ts("RAM per game", [P('max by (server, platform) (game_server_memory_bytes)', S)], 0, 12, 8, unit="bytes", mn=0)
    GH = 'id=~"lxc/105|lxc/107"'
    NAME = 'max by (id, name) (pve_guest_info{id=~"lxc/105|lxc/107"})'
    D.ts("Game hosts (LXC) CPU + RAM", [
            P(f'max by (name) (max by (id) (pve_cpu_usage_ratio{{{GH}}}) * on (id) group_left(name) {NAME})', "{{name}} CPU"),
            P(f'max by (name) (max by (id) (pve_memory_usage_bytes{{{GH}}} / pve_memory_size_bytes{{{GH}}}) * on (id) group_left(name) {NAME})', "{{name}} RAM", ref="B")],
         12, 12, 8, unit="percentunit", mn=0, mx=1, desc="pterodactyl-wings (LXC 105) and amp-server (LXC 107) as Proxmox sees them.")
    D.next_row(8)
    D.bargauge("Disk per game (Pterodactyl)", [P('max by (server) (game_server_disk_bytes)', "{{server}}", instant=True)],
               0, 12, 6, unit="bytes", mn=0, mx=None, th=thr(INFO), mode="gradient")
    D.table("Ports (live from the panels)", [P('max by (server, platform, host, port) (game_server_port_info)', instant=True, fmt="table")],
            12, 12, 6, [("server", "Server", "string", None, None), ("platform", "Panel", "string", None, None, 110),
                        ("host", "Host", "string", None, None, 110), ("port", "Port", "string", None, None, 80)],
            sort=[{"displayName": "Port"}], desc="If a port here is missing from GAME_PORTS in scripts/grafana/queries.py, "
                                                 "its connections show as 'other (port N)'.")
    D.next_row(6)
    return D.save(path)
