"""Detail sections of Homelab · Security (folded by default)."""
from lib import *
from queries import *

def add_details(D):
    """Fold-out detail sections at the bottom of the Security dashboard."""
    L, P = Dash.loki, Dash.prom

    # ---- Firewall --------------------------------------------------------------------------
    D.row("Details · Firewall (OPNsense)", collapsed=True)
    D.stat("Game connections", [L(cnt(GAME), instant=True)], 0, 4, th=thr(GAME_C))
    D.stat("Unique players / scanners", [L(uniq(GAME), instant=True)], 4, 4, th=thr(GAME_C))
    D.stat("Countries", [L(uniq(GAME + ' | country!=""', by="country"), instant=True)], 8, 4, th=thr(GAME_C))
    D.stat("Blocked from internet", [L(cnt(BLOCK), instant=True)], 12, 4, th=thr(GOOD, 1, WARN, 100, BAD))
    D.stat("Firewall log lines (all, incl. LAN)", [L(cnt('{job="opnsense"}'), instant=True)], 16, 4, th=thr(NEUTRAL),
           desc="Everything OPNsense sent, including house-LAN broadcasts that the other panels ignore.")
    D.stat("Firewall lines, last 15 min", [L(cnt('{job="opnsense"}', rng="15m"), instant=True)], 20, 4,
           th=thr(BAD, 1, GOOD), desc="Red = OPNsense stopped sending logs.")
    D.next_row(4)
    D.ts("Game connections per server", [L(
            f'sum by (dst_ip) (count_over_time({GAME} [$__auto]))', legend="{{dst_ip}}")], 0, 12, 8, bars=True, stack=True,
         desc="10.10.10.20 = Pterodactyl wings, 10.10.10.21 = AMP.",
         overrides=[{"matcher": {"id": "byName", "options": "10.10.10.20"}, "properties": [{"id": "displayName", "value": "wings (Pterodactyl)"}]},
                    {"matcher": {"id": "byName", "options": "10.10.10.21"}, "properties": [{"id": "displayName", "value": "AMP"}]}])
    D.ts("Pass vs block (internet)", [L(f'sum by (action) (count_over_time({FW_NET} [$__auto]))', legend="{{action}}")],
         12, 12, 8, bars=True, stack=True,
         overrides=[{"matcher": {"id": "byName", "options": "pass"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": GOOD}}]},
                    {"matcher": {"id": "byName", "options": "block"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": BLOCK_C}}]}])
    D.next_row(8)
    D.table("Destination ports (from internet)", [L(f'topk(20, sum by (dst_ip, dst_port, proto, action) (count_over_time({FW_NET} | dst_port!="" [$__range])))', instant=True)],
            0, 8, 9, [("dst_ip", "Server", "string", None, None), ("dst_port", "Port", "string", None, None),
                      ("proto", "Proto", "string", None, None), ("action", "Action", "string", None, None),
                      ("Value", "Packets", "none", thr(INFO), BAR_BASIC)],
            sort=[{"displayName": "Packets", "desc": True}], labels_to_fields=True)
    D.table("Top game-traffic sources", [L(f'topk(20, sum by (src_ip, country, city) (count_over_time({GAME} [$__range])))', instant=True)],
            8, 8, 9, [("src_ip", "IP", "string", None, None), ("city", "City", "string", None, None),
                      ("country", "Country", "string", None, None), ("Value", "Connections", "none", thr(GAME_C), BAR_BASIC)],
            sort=[{"displayName": "Connections", "desc": True}], labels_to_fields=True)
    D.table("Top blocked sources", [L(f'topk(20, sum by (src_ip, country, dst_port) (count_over_time({BLOCK} [$__range])))', instant=True)],
            16, 8, 9, [("src_ip", "IP", "string", None, None), ("country", "Country", "string", None, None),
                       ("dst_port", "Port", "string", None, None), ("Value", "Blocked", "none", thr(BLOCK_C), BAR_BASIC)],
            sort=[{"displayName": "Blocked", "desc": True}], labels_to_fields=True)
    D.next_row(9)
    D.pie("Protocols (internet)", [L(f'sum by (proto) (count_over_time({FW_NET} [$__range]))', legend="{{proto}}", instant=True)], 0, 6, 8)
    D.pie("Countries (game)", [L(f'topk(8, sum by (country) (count_over_time({GAME} | country!="" [$__range])))', legend="{{country}}", instant=True)], 6, 6, 8)
    D.logs("Firewall log (internet only)", [L(FW_NET + r' | line_format "{{ .action }}  {{ .src_ip }}:{{ .src_port }} ({{ .city }}, {{ .country }})  →  {{ .dst_ip }}:{{ .dst_port }} {{ .proto }}  [{{ .iface }} {{ .dir }}, rule {{ .rule }}]"')],
           12, 12, 8)
    D.next_row(8)

    # ---- Website -----------------------------------------------------------------------------
    D.row("Details · Website (apache.theminddev.com)", collapsed=True)
    D.stat("Requests", [L(cnt(WEB), instant=True)], 0, 4, th=thr(WEB_C))
    D.stat("Unique visitors", [L(uniq(WEB), instant=True)], 4, 4, th=thr(WEB_C))
    D.stat("Countries", [L(uniq(WEB + ' | country!=""', by="country"), instant=True)], 8, 4, th=thr(WEB_C))
    D.stat("Errors (4xx/5xx)", [L(cnt(WEB + ' | status=~"[45].."'), instant=True)], 12, 4, th=thr(GOOD, 1, WARN, 100, BAD))
    D.stat("Attack probes", [L(cnt(WEB_PROBE), instant=True)], 16, 4, th=thr(GOOD, 1, WARN, 50, BAD),
           desc="wp-login, .env, .git, phpmyadmin, cgi-bin ... (the site has none of these: pure bot noise).")
    D.stat("Bots (by user agent)", [L(cnt(WEB + r' | user_agent=~"(?i).*(bot|crawl|spider|scan|curl|python|go-http|zgrab|masscan|nmap).*"'), instant=True)],
           20, 4, th=thr(INFO))
    D.next_row(4)
    D.ts("Requests by status", [L(f'sum by (status) (count_over_time({WEB} [$__auto]))', legend="{{status}}")], 0, 12, 8, bars=True, stack=True)
    D.table("Top paths", [L(f'topk(20, sum by (path, status) (count_over_time({WEB} [$__range])))', instant=True)],
            12, 12, 8, [("path", "Path", "string", None, None), ("status", "Status", "string",
                         thr(GOOD, 400, WARN, 500, BAD), TXT_CELL, 70), ("Value", "Requests", "none", thr(WEB_C), BAR_BASIC)],
            sort=[{"displayName": "Requests", "desc": True}], labels_to_fields=True)
    D.next_row(8)
    D.table("Top visitors", [L(f'topk(20, sum by (src_ip, country, city) (count_over_time({WEB} [$__range])))', instant=True)],
            0, 8, 9, [("src_ip", "IP", "string", None, None), ("city", "City", "string", None, None),
                      ("country", "Country", "string", None, None), ("Value", "Requests", "none", thr(WEB_C), BAR_BASIC)],
            sort=[{"displayName": "Requests", "desc": True}], labels_to_fields=True)
    D.table("Top user agents", [L(f'topk(15, sum by (user_agent) (count_over_time({WEB} [$__range])))', instant=True)],
            8, 8, 9, [("user_agent", "User agent", "string", None, None), ("Value", "Requests", "none", thr(WEB_C), BAR_BASIC, 110)],
            sort=[{"displayName": "Requests", "desc": True}], labels_to_fields=True)
    D.logs("Website log", [L(WEB + r' | line_format "{{ .status }}  {{ .method }} {{ .path }}  ·  {{ .src_ip }} ({{ .city }}, {{ .country }})  ·  {{ .user_agent }}"')],
           16, 8, 9)
    D.next_row(9)

    # ---- SSH ---------------------------------------------------------------------------------
    D.row("Details · SSH logins (LXC 102)", collapsed=True)
    D.stat("Failed logins", [L(cnt(SSH_FAIL), instant=True)], 0, 4, th=thr(GOOD, 1, WARN, 20, BAD))
    D.stat("Successful logins", [L(cnt(SSH_OK), instant=True)], 4, 4, th=thr(INFO))
    D.ts("Logins over time", [L(f'sum(count_over_time({SSH_FAIL} [$__auto]))', legend="failed"),
                              L(f'sum(count_over_time({SSH_OK} [$__auto]))', legend="successful", ref="B")],
         8, 16, 8, bars=True,
         overrides=[{"matcher": {"id": "byName", "options": "failed"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": BLOCK_C}}]},
                    {"matcher": {"id": "byName", "options": "successful"}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": GOOD}}]}])
    D.y += 4  # the log sits under the two stats, next to the chart
    D.logs("SSH log (logins only)", [L(SSH + r' |~ "Accepted |Failed password|Invalid user|authentication failure"')], 0, 8, 4)
    D.y -= 4
    D.next_row(8)

    # ---- CrowdSec ----------------------------------------------------------------------------
    D.row("Details · CrowdSec (watch only)", collapsed=True)
    D.stat("Engine", [P('max(up{job="crowdsec"}) or vector(0)', instant=True)], 0, 4, mappings=UPDOWN, th=thr(BAD, 1, GOOD))
    D.stat("Alerts (stored)", [P("sum(cs_alerts) or vector(0)", instant=True)], 4, 4, th=thr(GOOD, 1, BAD))
    D.stat("Would-block decisions", [P("sum(cs_active_decisions) or vector(0)", instant=True)], 8, 4, th=thr(GOOD, 1, WARN),
           desc="IPs CrowdSec would ban if a bouncer were installed. Nothing is actually blocked.")
    D.stat("Lines parsed OK", [P("sum(increase(cs_parser_hits_ok_total[$__range])) / clamp_min(sum(increase(cs_parser_hits_total[$__range])), 1)", instant=True)],
           12, 4, unit="percentunit", decimals=0, th=thr(INFO), color_mode="value")
    D.stat("Lines read", [P("sum(increase(cs_lokisource_hits_total[$__range])) or vector(0)", instant=True)], 16, 4, decimals=0, th=thr(INFO), color_mode="value")
    D.stat("Last heartbeat", [P("max(cs_machines_last_heartbeat_timestamp) * 1000", instant=True)], 20, 4,
           unit="dateTimeFromNow", th=thr(INFO), color_mode="none")
    D.next_row(4)
    D.ts("Log lines read, by source", [P("sum by (acquis_type) (rate(cs_lokisource_hits_total[$__rate_interval]))", legend="{{acquis_type}}")],
         0, 8, 8, unit="cps")
    D.ts("Scenario triggers", [P("sum by (name) (increase(cs_bucket_overflowed_total[$__rate_interval]))", legend="{{name}}")],
         8, 8, 8, bars=True, desc="Each bar = an attack pattern matched (e.g. ssh-bf = SSH brute force).")
    D.table("Alerts by scenario", [P("sort_desc(sum by (reason) (cs_alerts))", instant=True, fmt="table")], 16, 8, 8,
            [("reason", "Scenario", "string", None, None), ("Value", "Alerts", "none", thr(BAD), BAR_BASIC)],
            sort=[{"displayName": "Alerts", "desc": True}])
    D.next_row(8)

    # ---- AdGuard -----------------------------------------------------------------------------
    D.row("Details · DNS (AdGuard on the Pi)", collapsed=True)
    D.stat("Protection", [P("max(adguard_protection_enabled) or vector(0)", instant=True)], 0, 4,
           mappings=[{"type": "value", "options": {"0": {"text": "OFF", "color": BAD, "index": 0}, "1": {"text": "ON", "color": GOOD, "index": 1}}}],
           th=thr(BAD, 1, GOOD))
    D.stat("Lookups (stats window)", [P("sum(adguard_queries)", instant=True)], 4, 4, th=thr(INFO), decimals=0,
           desc="AdGuard's own statistics window (default: last 24 h).")
    D.gauge("Blocked share", [P("sum(adguard_queries_blocked) / sum(adguard_queries)", instant=True)], 8, 4, 4,
            th=thr(INFO), mx=0.5)
    D.stat("Avg answer time", [P("avg(adguard_avg_processing_time_seconds)", instant=True)], 12, 4, unit="s",
           th=thr(GOOD, 0.05, WARN, 0.2, BAD), decimals=1)
    D.stat("Safe-browsing hits", [P("sum(adguard_replaced_safebrowsing) or vector(0)", instant=True)], 16, 4,
           th=thr(GOOD, 1, WARN), desc="Lookups of known malware/phishing domains that AdGuard replaced.")
    D.stat("Exporter errors", [P("sum(increase(adguard_scrape_errors_total[$__range])) or vector(0)", instant=True)], 20, 4,
           th=thr(GOOD, 1, WARN), decimals=0)
    D.next_row(4)
    D.bargauge("Top clients", [P("topk(10, sum by (client) (adguard_top_clients))", legend="{{client}}", instant=True)],
               0, 8, 10, unit="none", mn=0, mx=None, th=thr(INFO), color={"mode": "continuous-BlPu"})
    D.bargauge("Top blocked domains", [P("topk(10, sum by (domain) (adguard_top_blocked_domains))", legend="{{domain}}", instant=True)],
               8, 8, 10, unit="none", mn=0, mx=None, th=thr(BAD), color={"mode": "continuous-YlRd"})
    D.bargauge("Top looked-up domains", [P("topk(10, sum by (domain) (adguard_top_queried_domains))", legend="{{domain}}", instant=True)],
               16, 8, 10, unit="none", mn=0, mx=None, th=thr(INFO), color={"mode": "continuous-GrYlRd"})
    D.next_row(10)
    D.pie("Query types", [P("sum by (type) (adguard_query_types)", legend="{{type}}", instant=True)], 0, 8, 8)
    D.bargauge("Upstream DNS answer time", [P("avg by (upstream) (adguard_top_upstreams_avg_response_time_seconds)", legend="{{upstream}}", instant=True)],
               8, 8, 8, unit="s", mn=0, mx=None, th=thr(GOOD, 0.05, WARN, 0.2, BAD), decimals=3)
    D.ts("Blocked share over time", [P("sum(adguard_queries_blocked) / sum(adguard_queries)", legend="blocked")],
         16, 8, 8, unit="percentunit", mn=0)
    D.next_row(8)

    # ---- Pipeline health ---------------------------------------------------------------------
    D.row("Details · Log pipeline health", collapsed=True)
    D.ts("Log lines stored per source", [L('sum by (job) (count_over_time({job=~".+"} [$__auto]))', legend="{{job}}")],
         0, 12, 7, bars=True, stack=True, desc="How much Loki stores. Watch for sudden spikes.")
    D.stat("Log lines, last 15 min", [L(cnt('{job=~".+"}', rng="15m"), instant=True)], 12, 4, h=7,
           th=thr(BAD, 1, GOOD), decimals=0, desc="Red = Loki gets nothing (Alloy or Loki down).")
    D.stat("GeoIP hit rate", [L(f'sum(count_over_time({FW_NET} | country!="" [$__range])) / sum(count_over_time({FW_NET} [$__range]))', instant=True)],
           16, 4, h=7, unit="percentunit", decimals=0, th=thr(WARN, 0.8, GOOD),
           desc="Share of internet lines that got a location. Low = GeoIP file missing or old.")
    D.stat("AdGuard exporter", [P('max(up{job="adguard"}) or vector(0)', instant=True)], 20, 4, h=7, mappings=UPDOWN, th=thr(BAD, 1, GOOD))
    D.next_row(7)
