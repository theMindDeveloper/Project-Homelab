"""Homelab Overview: the start page. Big, coloured, at-a-glance."""
from lib import *
from queries import *

NODE = 'job="proxmox-host"'
GI = 'max by (id, name, node, type) (pve_guest_info{template="0"})'

def J(expr):
    """One row per guest with name/node/type, even if a metric exists more than once."""
    return f'max by (id, name, node, type) (max by (id) ({expr}) * on (id) group_left(name, node, type) {GI})'

def build(path):
    D = Dash("Homelab · Overview", "homelab-overview", ["homelab", "overview"], links=NAV, refresh="30s",
             time_from="now-6h", desc="Start page: is everything up, is anything full or hot, what's happening.")
    P, L = Dash.prom, Dash.loki

    # ---- at a glance ------------------------------------------------------------------------
    D.row("At a glance")
    D.stat("Nodes", [P(f'max by (node) (up{{{NODE}}})', legend="{{node}}", instant=True)], 0, 6, h=6,
           mappings=UPDOWN, th=thr(BAD, 1, GOOD), text_mode="value_and_name", links=host_link(),
           desc="Proxmox nodes. Red = node or its exporter is down. Click a node for details.")
    D.gauge("Cluster CPU", [P(f'1 - avg(rate(node_cpu_seconds_total{{{NODE},mode="idle"}}[5m]))', instant=True)], 6, 3)
    D.gauge("Cluster RAM", [P(f'1 - sum(node_memory_MemAvailable_bytes{{{NODE}}}) / sum(node_memory_MemTotal_bytes{{{NODE}}})', instant=True)], 9, 3)
    D.gauge("Fullest storage", [P('max(max by (id) (pve_disk_usage_bytes{id=~"storage/.*"} / pve_disk_size_bytes{id=~"storage/.*"}))', instant=True)], 12, 3,
            desc="The fullest Proxmox storage. Details in the Storage row.")
    D.gauge("Hottest CPU", [P('max(node_thermal_zone_temp{type="x86_pkg_temp"})', instant=True)], 15, 3,
            unit="celsius", th=TEMP, mx=100, decimals=0)
    D.pie("Guests", [P('count(max by (id) (pve_up{id=~"(qemu|lxc)/.*"}) == 1) or vector(0)', legend="running", instant=True),
                     P('count(max by (id) (pve_up{id=~"(qemu|lxc)/.*"}) == 0) or vector(0)', legend="stopped", ref="B", instant=True)],
          18, 3, h=6, overrides=[{"matcher": {"id": "byName", "options": n}, "properties": [
              {"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]} for n, c in (("running", GOOD), ("stopped", "#808080"))])
    D.stat("Guests with NO backup", [P('count(max by (id) (pve_not_backed_up_info) == 1) or vector(0)', instant=True)], 21, 3, h=6,
           th=thr(GOOD, 1, BAD), desc="VMs/LXCs no Proxmox backup job covers. Red = not protected.")
    D.next_row(6)

    # ---- internet (FRITZ!Box) ----------------------------------------------------------------
    D.row("Internet (FRITZ!Box 7590)")
    D.stat("Internet", [P('max(fritz_wan_phys_link_status) or vector(0)', instant=True)], 0, 3, h=5, mappings=UPDOWN,
           th=thr(BAD, 1, GOOD), desc="DSL/WAN link of the FRITZ!Box.")
    D.stat("Connected for", [P('max(fritz_wan_connection_uptime_seconds_total)', instant=True)], 3, 3, h=5, unit="s",
           th=thr(WARN, 86400, GOOD), desc="Time since the last reconnect. Orange = reconnected in the last 24 h.")
    D.stat("DSL speed ↓", [P('max(fritz_dsl_datarate_kbps{direction="rx", type="curr"}) * 1000', instant=True)], 6, 3, h=5,
           unit="bps", th=thr(INFO), color_mode="value", desc="Line sync speed (what the line can carry), not current use.")
    D.stat("DSL speed ↑", [P('max(fritz_dsl_datarate_kbps{direction="tx", type="curr"}) * 1000', instant=True)], 9, 3, h=5,
           unit="bps", th=thr(INFO), color_mode="value")
    D.stat("Line quality (noise margin ↓)", [P('max(fritz_dsl_noise_margin_dB{direction="rx"})', instant=True)], 12, 3, h=5,
           unit="dB", decimals=1, th=thr(BAD, 6, WARN, 8, GOOD), color_mode="value",
           desc="Higher = more stable line. Under 6 dB = expect disconnects.")
    D.stat("DSL errors (range)", [P('sum(increase(fritz_dsl_crc_errors_count_total[$__range])) or vector(0)', instant=True)], 15, 3, h=5,
           decimals=0, th=thr(GOOD, 100, WARN, 1000, BAD), color_mode="value", desc="CRC errors on the DSL line in the selected time.")
    D.ts("Internet traffic now (+ down / − up)", [
            P('max(rate(fritz_wan_data_bytes_total{direction="rx"}[$__rate_interval]))', "download"),
            P('-max(rate(fritz_wan_data_bytes_total{direction="tx"}[$__rate_interval]))', "upload", ref="B")],
         18, 6, 5, unit="Bps", mn=None)
    D.next_row(5)

    # ---- nodes --------------------------------------------------------------------------------
    D.row("Nodes")
    D.bargauge("CPU", [P(f'1 - avg by (node) (rate(node_cpu_seconds_total{{{NODE},mode="idle"}}[5m]))', legend="{{node}}", instant=True)],
               0, 6, 6, mode="lcd", links=host_link())
    D.bargauge("RAM", [P(f'1 - max by (node) (node_memory_MemAvailable_bytes{{{NODE}}} / node_memory_MemTotal_bytes{{{NODE}}})', legend="{{node}}", instant=True)],
               6, 6, 6, mode="lcd", links=host_link())
    D.bargauge("System disk ( / )", [P(f'max by (node) (1 - node_filesystem_avail_bytes{{{NODE},mountpoint="/"}} / node_filesystem_size_bytes{{{NODE},mountpoint="/"}})', legend="{{node}}", instant=True)],
               12, 6, 6, mode="lcd", links=host_link())
    D.bargauge("CPU temperature", [P('max by (node) (node_thermal_zone_temp{type="x86_pkg_temp"})', legend="{{node}}", instant=True)],
               18, 6, 6, mode="lcd", unit="celsius", th=TEMP, mx=100, links=host_link())
    D.next_row(6)
    D.table("Node details", [
        P(f'max by (node) (time() - node_boot_time_seconds{{{NODE}}})', ref="A", instant=True, fmt="table"),
        P(f'max by (node) (node_memory_MemTotal_bytes{{{NODE}}})', ref="B", instant=True, fmt="table"),
        P(f'max by (node) (node_load1{{{NODE}}}) / count by (node) (node_cpu_seconds_total{{{NODE},mode="idle"}})', ref="C", instant=True, fmt="table"),
        P('max by (node) (node_hwmon_temp_celsius{chip=~"nvme.*"})', ref="D", instant=True, fmt="table"),
        P(f'sum by (node) (rate(node_network_receive_bytes_total{{{NODE},device=~"nic[0-9]+|en.*"}}[5m]))', ref="E", instant=True, fmt="table"),
        P(f'sum by (node) (rate(node_network_transmit_bytes_total{{{NODE},device=~"nic[0-9]+|en.*"}}[5m]))', ref="F", instant=True, fmt="table"),
      ], 0, 24, 5, [("node", "Node", "string", None, None), ("A", "Uptime", "s", thr(WARN, 86400, GOOD), TXT_CELL),
                    ("B", "RAM", "bytes", None, None), ("C", "Load / core", "percentunit", thr(GOOD, 0.8, WARN, 1, BAD), BAR_CELL),
                    ("D", "NVMe temp", "celsius", TEMP, TXT_CELL), ("E", "Network in", "Bps", None, None),
                    ("F", "Network out", "Bps", None, None)], sort=[{"displayName": "Node"}],
            desc="Load/core above 100% = work is waiting for CPU. Orange uptime = rebooted in the last 24 h.")
    D.next_row(5)
    D.ts("CPU per node", [P(f'1 - avg by (node) (rate(node_cpu_seconds_total{{{NODE},mode="idle"}}[$__rate_interval]))', "{{node}}")],
         0, 8, 8, unit="percentunit", mn=0, mx=1, th=PCT)
    D.ts("RAM per node", [P(f'1 - node_memory_MemAvailable_bytes{{{NODE}}} / node_memory_MemTotal_bytes{{{NODE}}}', "{{node}}")],
         8, 8, 8, unit="percentunit", mn=0, mx=1, th=PCT)
    D.ts("Temperatures", [P('node_thermal_zone_temp{type="x86_pkg_temp"}', "{{node}} CPU"),
                          P('max by (node) (node_hwmon_temp_celsius{chip=~"nvme.*"})', "{{node}} NVMe", ref="B")],
         16, 8, 8, unit="celsius", th=TEMP)
    D.next_row(8)
    D.ts("Network per node (+ in / − out)", [
        P(f'sum by (node) (rate(node_network_receive_bytes_total{{{NODE},device=~"nic[0-9]+|en.*"}}[$__rate_interval]))', "{{node}} in"),
        P(f'-sum by (node) (rate(node_network_transmit_bytes_total{{{NODE},device=~"nic[0-9]+|en.*"}}[$__rate_interval]))', "{{node}} out", ref="B")],
        0, 12, 8, unit="Bps", mn=None)
    D.ts("Disk I/O per node (+ read / − write)", [
        P(f'sum by (node) (rate(node_disk_read_bytes_total{{{NODE},device=~"nvme.*n1|sd[a-z]"}}[$__rate_interval]))', "{{node}} read"),
        P(f'-sum by (node) (rate(node_disk_written_bytes_total{{{NODE},device=~"nvme.*n1|sd[a-z]"}}[$__rate_interval]))', "{{node}} write", ref="B")],
        12, 12, 8, unit="Bps", mn=None)
    D.next_row(8)

    # ---- Pi + NAS ---------------------------------------------------------------------------
    D.row("Raspberry Pi + NAS")
    OH = 'job="other-hosts"'
    D.stat("Pi / NAS", [P(f'max by (node) (up{{{OH}}})', legend="{{node}}", instant=True)], 0, 4, h=7,
           mappings=UPDOWN, th=thr(BAD, 1, GOOD), text_mode="value_and_name", links=host_link(),
           desc="Click for details. Pi = DNS (AdGuard) + reverse proxy (NPM). NAS = storage, Jellyfin, backups target.")
    D.bargauge("CPU", [P(f'1 - avg by (node) (rate(node_cpu_seconds_total{{{OH},mode="idle"}}[5m]))', legend="{{node}}", instant=True)],
               4, 5, 7, mode="lcd", links=host_link())
    D.bargauge("RAM", [P(f'1 - max by (node) (node_memory_MemAvailable_bytes{{{OH}}} / node_memory_MemTotal_bytes{{{OH}}})', legend="{{node}}", instant=True)],
               9, 5, 7, mode="lcd", links=host_link())
    D.bargauge("Temperature", [P(f'max by (node) (node_thermal_zone_temp{{{OH}}})', legend="{{node}} CPU", instant=True)],
               14, 5, 7, mode="lcd", unit="celsius", th=TEMP, mx=100, links=host_link())
    D.bargauge("Disks / NAS volumes", [
        P(f'max by (node) (1 - node_filesystem_avail_bytes{{{OH},node="pi",mountpoint="/"}} / node_filesystem_size_bytes{{{OH},node="pi",mountpoint="/"}})', legend="pi /", instant=True),
        P(f'max by (volume) (label_replace(1 - node_filesystem_avail_bytes{{{OH},node="nas",mountpoint=~"/disks/.+"}} / node_filesystem_size_bytes{{{OH},node="nas",mountpoint=~"/disks/.+"}}, "volume", "$1", "mountpoint", "/disks/(.+)"))', legend="nas {{volume}}", ref="B", instant=True)],
               19, 5, 7, mode="lcd", desc="How full the Pi's disk and each NAS volume are (NAS: one read-only folder per volume).")
    D.next_row(7)
    D.ts("Network (+ in / − out)", [
        P(f'sum by (node) (rate(node_network_receive_bytes_total{{{OH},device=~"eth[0-9]+|en.*|bond[0-9]+"}}[$__rate_interval]))', "{{node}} in"),
        P(f'-sum by (node) (rate(node_network_transmit_bytes_total{{{OH},device=~"eth[0-9]+|en.*|bond[0-9]+"}}[$__rate_interval]))', "{{node}} out", ref="B")],
        0, 12, 7, unit="Bps", mn=None, desc="The NAS exporter runs in bridge mode, so the NAS line shows only the exporter's own traffic.")
    D.ts("Disk I/O (+ read / − write)", [
        P(f'sum by (node) (rate(node_disk_read_bytes_total{{{OH},device=~"nvme.*n1|sd[a-z]|mmcblk[0-9]"}}[$__rate_interval]))', "{{node}} read"),
        P(f'-sum by (node) (rate(node_disk_written_bytes_total{{{OH},device=~"nvme.*n1|sd[a-z]|mmcblk[0-9]"}}[$__rate_interval]))', "{{node}} write", ref="B")],
        12, 12, 7, unit="Bps", mn=None)
    D.next_row(7)

    # ---- game servers -----------------------------------------------------------------------
    D.row("Game servers (AMP + Pterodactyl)")
    D.state_timeline("When did they run?", [P('max by (server, platform) (game_server_up)', "{{server}} ({{platform}})")],
                     0, 16, 7, mappings=[{"type": "value", "options": {
                         "0": {"text": "stopped", "color": "#555555", "index": 0},
                         "1": {"text": "running", "color": GOOD, "index": 1}}}],
                     desc="Green = game running and ready. Empty = panel not reachable (pve2 off).")
    D.table("Now", [P('max by (server, platform, state) (game_server_state)', instant=True, fmt="table")], 16, 8, 7,
            [("server", "Server", "string", None, None), ("platform", "Panel", "string", None, None, 100),
             ("state", "State", "string", None, None, 110)], sort=[{"displayName": "Server"}],
            desc="Live state from the AMP / Pterodactyl APIs. Alerts: Telegram 🎮 when a running server stops.")
    for o in D.d["panels"][-1]["fieldConfig"]["overrides"]:
        if o["matcher"]["options"] == "State":
            o["properties"].append({"id": "mappings", "value": [{"type": "value", "options": {
                "ready": {"color": GOOD, "index": 0}, "running": {"color": GOOD, "index": 1},
                "starting": {"color": INFO, "index": 2}, "failed": {"color": BAD, "index": 3}}}]})
            o["properties"].append({"id": "custom.cellOptions", "value": TXT_CELL})
    D.next_row(7)

    # ---- guests -------------------------------------------------------------------------------
    D.row("Guests (VMs + LXCs)")
    D.state_timeline("Up / down history", [P(J('pve_up{id=~"(qemu|lxc)/.*"}'), "{{name}}")], 0, 24, 9,
                     mappings=[{"type": "value", "options": {"0": {"text": "stopped", "color": "#555555", "index": 0},
                                                             "1": {"text": "running", "color": GOOD, "index": 1}}}],
                     desc="Green = running, grey = stopped. Gaps = no data.")
    D.next_row(9)
    D.bargauge("CPU now (cores used)", [P('topk(10, ' + J('pve_cpu_usage_ratio * pve_cpu_usage_limit') + ')', "{{name}}", instant=True)],
               0, 8, 9, unit="none", mn=0, mx=None, th=thr(INFO), color={"mode": "continuous-BlPu"}, decimals=2)
    D.bargauge("RAM now", [P('topk(10, ' + J('pve_memory_usage_bytes / pve_memory_size_bytes') + ')', "{{name}}", instant=True)],
               8, 8, 9, mode="lcd", desc="Share of the RAM given to each guest. VMs can show >100% (QEMU overhead).")
    D.bargauge("LXC disk", [P('topk(10, ' + J('pve_disk_usage_bytes{id=~"lxc/.*"} / pve_disk_size_bytes{id=~"lxc/.*"}') + ')', "{{name}}", instant=True)],
               16, 8, 9, mode="lcd", desc="Root disk of each LXC. (VM disks are not visible from Proxmox.)")
    D.next_row(9)
    D.table("All guests", [
        P(J('pve_up{id=~"(qemu|lxc)/.*"}'), ref="A", instant=True, fmt="table"),
        P(J('pve_cpu_usage_ratio'), ref="B", instant=True, fmt="table"),
        P(J('pve_cpu_usage_limit'), ref="C", instant=True, fmt="table"),
        P(J('pve_memory_usage_bytes / pve_memory_size_bytes'), ref="D", instant=True, fmt="table"),
        P(J('pve_memory_size_bytes'), ref="E", instant=True, fmt="table"),
        P(J('pve_uptime_seconds'), ref="F", instant=True, fmt="table"),
        P(J('pve_not_backed_up_info') + ' or 0 * ' + GI, ref="G", instant=True, fmt="table"),
        P(J('pve_onboot_status'), ref="H", instant=True, fmt="table"),
      ], 0, 24, 12, [
        ("id", "ID", "string", None, None, 90), ("name", "Name", "string", None, None), ("type", "Type", "string", None, None, 70),
        ("node", "Node", "string", None, None, 70),
        ("A", "State", "string", thr(BAD, 1, GOOD), BG_CELL, 90),
        ("B", "CPU", "percentunit", PCT, BAR_CELL), ("C", "vCPUs", "none", None, None, 70),
        ("D", "RAM", "percentunit", PCT, BAR_CELL), ("E", "RAM size", "bytes", None, None, 90),
        ("F", "Uptime", "s", None, None, 100), ("G", "Backup", "string", thr(GOOD, 1, BAD), BG_CELL, 90),
        ("H", "Autostart", "string", None, None, 90)],
        sort=[{"displayName": "ID"}])
    # value text for the coloured cells
    for o in D.d["panels"][-1]["fieldConfig"]["overrides"]:
        n = o["matcher"]["options"]
        if n == "State":
            o["properties"].append({"id": "mappings", "value": [{"type": "value", "options": {
                "0": {"text": "stopped", "index": 0}, "1": {"text": "running", "index": 1}}}]})
        if n == "Backup":
            o["properties"].append({"id": "mappings", "value": [{"type": "value", "options": {
                "0": {"text": "yes", "index": 0}, "1": {"text": "NONE", "index": 1}}}]})
        if n == "Autostart":
            o["properties"].append({"id": "mappings", "value": [{"type": "value", "options": {
                "0": {"text": "no", "index": 0}, "1": {"text": "yes", "index": 1}}}]})
    D.next_row(12)

    # ---- storage ------------------------------------------------------------------------------
    D.row("Storage")
    SV = 'max by (id) (pve_disk_usage_bytes{id=~"storage/.*"} / pve_disk_size_bytes{id=~"storage/.*"})'
    SI = 'max by (id, node, storage) (pve_storage_info)'
    SH = 'max by (id) (pve_storage_shared)'
    D.bargauge("How full", [
        P(f'max by (node, storage) ({SV} * on (id) group_left(node, storage) {SI} * on (id) group_left() ({SH} == 0))', "{{node}} · {{storage}}", instant=True),
        P(f'max by (storage) ({SV} * on (id) group_left(storage) {SI} * on (id) group_left() ({SH} == 1))', "{{storage}} (NAS, shared)", ref="B", instant=True)],
        0, 12, 9, mode="lcd", desc="Used space of every Proxmox storage. The NAS share is shown once.")
    D.table("Storage details", [
        P('max by (id) (pve_disk_size_bytes{id=~"storage/.*"})', ref="A", instant=True, fmt="table"),
        P('max by (id) (pve_disk_usage_bytes{id=~"storage/.*"})', ref="B", instant=True, fmt="table"),
        P('max by (id) ((pve_disk_size_bytes{id=~"storage/.*"} - pve_disk_usage_bytes{id=~"storage/.*"}) / (deriv(pve_disk_usage_bytes{id=~"storage/.*"}[1d]) > 0) / 86400)', ref="C", instant=True, fmt="table"),
      ], 12, 12, 9, [("id", "Storage", "string", None, None), ("A", "Size", "bytes", None, None), ("B", "Used", "bytes", None, None),
                     ("C", "Full in (days)", "d", thr(BAD, 14, WARN, 60, GOOD), TXT_CELL)],
        desc="'Full in' guesses from the growth of the last day. Empty = not growing.", sort=[{"displayName": "Storage"}])
    D.next_row(9)

    # ---- security summary ------------------------------------------------------------------
    D.row("Security (selected time range) — details on the Security dashboard")
    sec_link = [{"title": "Open Security dashboard", "url": "/d/homelab-security", "targetBlank": False}]
    D.stat("Connections from the internet", [L(cnt(INET), instant=True)], 0, 4, th=thr(INFO), links=sec_link)
    D.stat("Countries", [L(uniq(INET + ' | country!=""', by="country"), instant=True)], 4, 4, th=thr("purple"), links=sec_link)
    D.stat("Website requests", [L(cnt(WEB), instant=True)], 8, 4, th=thr(WEB_C), links=sec_link)
    D.stat("CrowdSec alerts", [P("sum(cs_alerts) or vector(0)", instant=True)], 12, 4, th=thr(GOOD, 1, BAD), links=sec_link)
    D.stat("Failed SSH logins", [L(cnt(SSH_FAIL), instant=True)], 16, 4, th=thr(GOOD, 1, WARN, 20, BAD), links=sec_link)
    D.stat("DNS lookups blocked", [P("sum(adguard_queries_blocked) / sum(adguard_queries)", instant=True)], 20, 4,
           unit="percentunit", decimals=1, th=thr(INFO), links=sec_link)
    D.next_row(4)
    return D.save(path)
