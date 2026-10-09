"""Homelab Security: the simple, visual page. Details live in gen_security_advanced.py."""
from lib import *
from queries import *
from gen_security_details import add_details

def build(path):
    D = Dash("Homelab · Security", "homelab-security", ["homelab", "security"], links=NAV, refresh="1m",
             desc="Watch only: nothing here blocks traffic. Locations are approximate (DB-IP Lite, CC BY 4.0).")
    L, P = Dash.loki, Dash.prom

    # ---- KPIs ----------------------------------------------------------------------------
    D.row("Internet → homelab (selected time range)")
    D.stat("Connections from the internet", [L(cnt(INET), instant=True)], 0, 4, th=thr(INFO), graph=False,
           desc="Game-server connections + website requests that came from the internet.")
    D.stat("Unique visitor IPs", [L(uniq(INET), instant=True)], 4, 4, th=thr("purple"))
    D.stat("Countries", [L(uniq(INET + ' | country!=""', by="country"), instant=True)], 8, 4, th=thr("#8F3BB8"))
    D.stat("Website requests", [L(cnt(WEB), instant=True)], 12, 4, th=thr(WEB_C),
           desc="apache.theminddev.com through the Cloudflare tunnel.")
    D.stat("Blocked by firewall", [L(cnt(BLOCK), instant=True)], 16, 4, th=thr(GOOD, 1, WARN, 100, BAD),
           desc="Internet packets OPNsense dropped. 0 is normal: the FRITZ!Box only forwards game ports.")
    D.stat("CrowdSec alerts", [P("sum(cs_alerts) or vector(0)", instant=True)], 20, 4, th=thr(GOOD, 1, BAD),
           desc="Attacks CrowdSec recognised (brute force, scans, web exploits). Watch only: nothing gets blocked.")
    D.next_row(4)

    # ---- the map ---------------------------------------------------------------------------
    geo_q = (f'sum by (lat, lon, city, country, kind) (count_over_time({INET} | lat!="" [$__range]))')
    D.geomap("Where the traffic comes from", [L(geo_q, instant=True)], 0, 17, 14,
             desc="Each dot is a city. Bigger = more connections. Blue = game servers, orange = website.",
             transformations=[{"id": "labelsToFields", "options": {"mode": "columns"}},
                              {"id": "merge", "options": {}},
                              {"id": "convertFieldType", "options": {"conversions": [
                                  {"targetField": "lat", "destinationType": "number"},
                                  {"targetField": "lon", "destinationType": "number"}]}},
                              {"id": "organize", "options": {"renameByName": {"Value": "Connections"}}}],
             overrides=[{"matcher": {"id": "byName", "options": "kind"}, "properties": [
                 {"id": "mappings", "value": [{"type": "value", "options": {
                     "game servers": {"color": GAME_C, "index": 0}, "website": {"color": WEB_C, "index": 1}}}]},
                 {"id": "color", "value": {"mode": "fixed", "fixedColor": GAME_C}}]}],
             layers=[{"type": "markers", "name": "Visitors", "tooltip": True,
                      "location": {"mode": "coords", "latitude": "lat", "longitude": "lon"},
                      "config": {"showLegend": False, "style": {
                          "size": {"field": "Connections", "min": 5, "max": 28, "fixed": 6},
                          "color": {"field": "kind", "fixed": GAME_C}, "opacity": 0.75,
                          "symbol": {"mode": "fixed", "fixed": "img/icons/marker/circle.svg"},
                          "symbolAlign": {"horizontal": "center", "vertical": "center"}}}}])
    D.bargauge("Top countries", [L(f'topk(12, sum by (country) (count_over_time({INET} | country!="" [$__range])))',
                                   legend="{{country}}", instant=True)], 17, 7, 14, unit="none", mn=0, mx=None,
               th=thr(INFO), mode="gradient", color={"mode": "continuous-BlPu"},
               desc="Countries with the most connections (game + website).")
    D.next_row(14)

    # ---- over time + split ------------------------------------------------------------------
    D.ts("Internet traffic over time", [
            L(f'sum by (kind) (count_over_time({INET} [$__auto]))', legend="{{kind}}"),
            L(f'sum(count_over_time({BLOCK} [$__auto]))', legend="blocked", ref="B")],
         0, 17, 8, bars=True, stack=True,
         overrides=[{"matcher": {"id": "byName", "options": n}, "properties": [
             {"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]}
             for n, c in (("game servers", GAME_C), ("website", WEB_C), ("blocked", BLOCK_C))])
    D.pie("What they reach", [L(f'sum by (kind) (count_over_time({INET} [$__range]))', legend="{{kind}}", instant=True)],
          17, 7, 8, overrides=[{"matcher": {"id": "byName", "options": n}, "properties": [
              {"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]}
              for n, c in (("game servers", GAME_C), ("website", WEB_C))])
    D.next_row(8)

    # ---- who + latest --------------------------------------------------------------------
    D.table("Top visitors", [L(f'topk(15, sum by (src_ip, country, city, kind) (count_over_time({INET} [$__range])))',
                               instant=True)],
            0, 10, 10, [("src_ip", "IP", "string", None, None, 130), ("country", "Country", "string", None, None),
                        ("city", "City", "string", None, None), ("kind", "Reached", "string", None, None),
                        ("Value", "Connections", "none", thr(INFO), BAR_BASIC)],
            sort=[{"displayName": "Connections", "desc": True}], merge=True, labels_to_fields=True)
    D.logs("Latest connections from the internet",
           [L(INET + r' | line_format "{{ .kind }}  ·  {{ .src_ip }}  ·  {{ .city }}, {{ .country }}  →  '
                     r'{{ if eq .job \"apache\" }}{{ .method }} {{ .path }} ({{ .status }}){{ else }}{{ .dst_ip }}:{{ .dst_port }} {{ .proto }}{{ end }}"')],
           10, 14, 10)
    D.next_row(10)

    # ---- health strip -----------------------------------------------------------------------
    D.row("Guards")
    D.stat("Failed SSH logins", [L(cnt(SSH_FAIL), instant=True)], 0, 4, th=thr(GOOD, 1, WARN, 20, BAD),
           desc="Failed logins on LXC 102 in the selected time range.")
    D.stat("Website attack probes", [L(cnt(WEB_PROBE), instant=True)], 4, 4, th=thr(GOOD, 1, WARN, 50, BAD),
           desc="Requests for typical attack paths (wp-login, .env, phpmyadmin, ...). Bots try these all day.")
    D.stat("CrowdSec", [P('max(up{job="crowdsec"}) or vector(0)', instant=True)], 8, 4, mappings=UPDOWN,
           th=thr(BAD, 1, GOOD), desc="CrowdSec engine running (watch only).")
    D.stat("Log lines checked by CrowdSec", [P("sum(increase(cs_lokisource_hits_total[$__range])) or vector(0)", instant=True)],
           12, 4, th=thr(INFO), decimals=0)
    D.stat("DNS ad/tracker blocking", [P("max(adguard_protection_enabled) or vector(0)", instant=True)], 16, 4,
           mappings=[{"type": "value", "options": {"0": {"text": "OFF", "color": BAD, "index": 0},
                                                   "1": {"text": "ON", "color": GOOD, "index": 1}}}],
           th=thr(BAD, 1, GOOD), desc="AdGuard Home on the Pi.")
    D.stat("DNS lookups blocked", [P("sum(adguard_queries_blocked) / sum(adguard_queries)", instant=True)], 20, 4,
           unit="percentunit", decimals=1, th=thr(INFO), desc="Share of DNS lookups AdGuard blocked (ads, trackers).")
    D.next_row(4)

    # ---- home network + router ------------------------------------------------------------------
    D.row("Home network & router (FRITZ!Box)")
    KD = 'max(fritz_known_devices_count)'
    D.stat("New devices", [P(f'{KD} - (max(fritz_known_devices_count offset $__range) or {KD})', instant=True)], 0, 4,
           th=thr(GOOD, 1, WARN), decimals=0,
           desc="Devices the FRITZ!Box saw for the first time in the selected time range. Not yours? Check FRITZ!Box → Heimnetz.")
    D.stat("Wi-Fi devices now", [P('sum(fritz_wifi_associations_count)', instant=True)], 4, 4, th=thr(INFO), decimals=0)
    D.stat("Known devices (all time)", [P(KD, instant=True)], 8, 4, th=thr(NEUTRAL), color_mode="value", decimals=0,
           desc="Every device the FRITZ!Box has ever seen (also old ones).")
    D.stat("Remote access (MyFRITZ)", [P('max(fritz_usp_myfritz_enabled)', instant=True)], 12, 4,
           mappings=[{"type": "value", "options": {"0": {"text": "OFF", "color": GOOD, "index": 0},
                                                   "1": {"text": "ON", "color": WARN, "index": 1}}}], th=thr(GOOD),
           desc="MyFRITZ lets you reach the FRITZ!Box from the internet. OFF = smaller attack surface.")
    D.stat("Firmware", [P('max(fritz_update_available)', instant=True)], 16, 4,
           mappings=[{"type": "value", "options": {"0": {"text": "up to date", "color": GOOD, "index": 0},
                                                   "1": {"text": "UPDATE!", "color": BAD, "index": 1}}}], th=thr(GOOD),
           desc="FRITZ!OS updates often fix security holes. Install via FRITZ!Box → System → Update.")
    D.stat("Internet reconnects", [P('sum(resets(fritz_ppp_connection_uptime_seconds_total[$__range])) or vector(0)', instant=True)],
           20, 4, th=thr(GOOD, 1, INFO, 3, WARN), decimals=0,
           desc="Times the DSL connection restarted (new public IP each time).")
    D.next_row(4)
    D.ts("Devices on the network", [P(KD, "known devices (all time)"), P('sum(fritz_wifi_associations_count)', "on Wi-Fi now", ref="B")],
         0, 12, 8, mn=0, desc="A jump in 'known devices' = a new device joined.")
    D.ts("Internet traffic (+ download / − upload)", [
            P('max(rate(fritz_wan_data_bytes_total{direction="rx"}[$__rate_interval]))', "download"),
            P('-max(rate(fritz_wan_data_bytes_total{direction="tx"}[$__rate_interval]))', "upload", ref="B")],
         12, 12, 8, unit="Bps", mn=None,
         desc="Big, long upload spikes you can't explain (no backups/streams running) can mean a device sends data out.",
         overrides=[{"matcher": {"id": "byName", "options": "upload"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": WEB_C}}]},
                    {"matcher": {"id": "byName", "options": "download"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": GAME_C}}]}])
    D.next_row(8)
    add_details(D)
    return D.save(path)
