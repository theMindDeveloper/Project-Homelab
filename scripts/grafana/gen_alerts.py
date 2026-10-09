"""Grafana alert rules -> hosts/lxc102/opt/monitoring/grafana/provisioning/alerting/rules.yml
Each rule's query returns 1 = problem, 0 = fine (PromQL "bool" comparisons), so the threshold is simply "> 0".
severity=critical -> Telegram any time; severity=warning -> not at night (see policies.yml)."""
import json, os

PROM, LOKI = "prometheus-homelab", "loki-homelab"
FS = 'fstype!~"tmpfs|overlay|squashfs|ramfs|devtmpfs|nsfs|fuse.*|autofs|proc|sysfs", mountpoint!~"/etc/.*|/boot/efi|/run.*"'
GI = 'max by (id, name, node) (pve_guest_info{template="0"})'
HOSTS = 'job=~"proxmox-host|other-hosts"'

def rule(uid, title, expr, summary, desc, sev, for_="5m", ds=PROM, nodata="OK", extra=None, math=None):
    """extra: [(refId, datasource uid, expr)] more queries; math: Grafana math expression instead of "A > 0".
    Alert rule files are NOT env-expanded by Grafana (tested), so write $A as-is."""
    q = {"refId": "A", "expr": expr, "instant": True, "intervalMs": 60000, "maxDataPoints": 43200}
    if ds == LOKI:
        q = {"refId": "A", "expr": expr, "queryType": "instant"}
    return {"uid": uid, "title": title, "condition": "C", "for": for_, "noDataState": nodata, "execErrState": "Error",
            "labels": {"severity": sev}, "annotations": {"summary": summary, "description": desc}, "isPaused": False,
            "data": [{"refId": "A", "relativeTimeRange": {"from": 900, "to": 0}, "datasourceUid": ds, "model": q}]
                    + [{"refId": r, "relativeTimeRange": {"from": 900, "to": 0}, "datasourceUid": d,
                        "model": ({"refId": r, "expr": e, "instant": True, "intervalMs": 60000, "maxDataPoints": 43200} if d == PROM
                                  else {"refId": r, "expr": e, "queryType": "instant"})} for r, d, e in (extra or [])]
                    + [{"refId": "C", "datasourceUid": "__expr__", "model": (
                        {"refId": "C", "type": "math", "expression": math} if math else
                        {"refId": "C", "type": "threshold", "expression": "A",
                         "conditions": [{"evaluator": {"type": "gt", "params": [0]}}]})}]}

CRIT = [
    # pve2 + pve3 are switched off on purpose to save power -> no "down" alert for them.
    rule("host-down", "Host down", f'max by (node) (up{{{HOSTS}, node!~"pve2|pve3"}}) < bool 1',
         "{{ .Labels.node }} is DOWN", "Prometheus can't reach {{ .Labels.node }} for 2 minutes.", "critical", "2m"),
    rule("guest-stopped", "Guest with autostart stopped",
         # lxc/101: autostart on but stopped on purpose -> excluded until decided (docs/24, trap 7)
         # ... and only while its node is on (pve2/pve3 get switched off on purpose)
         f'((max by (id) (pve_up{{id=~"(qemu|lxc)/.*", id!="lxc/101"}}) == bool 0) * on (id) (max by (id) (pve_onboot_status) == 1) * on (id) group_left(name, node) {GI}) and on (node) (max by (node) (up{{job="proxmox-host"}}) == 1)',
         "{{ .Labels.name }} ({{ .Labels.id }}) stopped", "Set to start on boot, but not running on {{ .Labels.node }}.", "critical", "5m"),
    rule("adguard-down", "AdGuard (house DNS) down", '(max(adguard_running) or vector(0)) < bool 1',
         "AdGuard DNS on the Pi is DOWN", "Devices in the house may not resolve names.", "critical", "3m"),
    rule("disk-90", "Disk over 90%", f'max by (node, mountpoint) (1 - node_filesystem_avail_bytes{{{HOSTS},{FS}}} / node_filesystem_size_bytes{{{HOSTS},{FS}}}) > bool 0.9',
         "{{ .Labels.node }} {{ .Labels.mountpoint }} is over 90% full", "Free space soon or things start failing.", "critical", "10m"),
    rule("storage-90", "Proxmox storage over 90%", 'max by (id) (pve_disk_usage_bytes{id=~"storage/.*"} / pve_disk_size_bytes{id=~"storage/.*"}) > bool 0.9',
         "Storage {{ .Labels.id }} is over 90% full", "Proxmox storage almost full.", "critical", "10m"),
    rule("cpu-hot", "CPU over 85 °C", f'max by (node) (node_thermal_zone_temp{{{HOSTS}}}) > bool 85',
         "{{ .Labels.node }} CPU is over 85 °C", "Check fan/dust/airflow.", "critical", "5m"),
    # No "or vector(0)": if the exporter itself is down that's "Monitoring target down", not "internet down".
    rule("internet-down", "Internet down (FRITZ!Box)", 'max(fritz_wan_phys_link_status) < bool 1',
         "Internet is DOWN (FRITZ!Box)", "The DSL/WAN link is down. You get this message once it's back.", "critical", "3m"),
]
WARN = [
    rule("disk-80", "Disk over 80%", f'max by (node, mountpoint) (1 - node_filesystem_avail_bytes{{{HOSTS},{FS}}} / node_filesystem_size_bytes{{{HOSTS},{FS}}}) > bool 0.8',
         "{{ .Labels.node }} {{ .Labels.mountpoint }} is over 80% full", "Time to clean up.", "warning", "30m"),
    rule("storage-80", "Proxmox storage over 80%", 'max by (id) (pve_disk_usage_bytes{id=~"storage/.*"} / pve_disk_size_bytes{id=~"storage/.*"}) > bool 0.8',
         "Storage {{ .Labels.id }} is over 80% full", "Time to clean up.", "warning", "30m"),
    rule("disk-full-7d", "Disk full within 7 days", f'max by (node, mountpoint) (predict_linear(node_filesystem_avail_bytes{{{HOSTS},{FS},node!=""}}[6h], 7*86400) < bool 0)',
         "{{ .Labels.node }} {{ .Labels.mountpoint }} will be full in < 7 days", "Based on the last 6 hours of growth.", "warning", "2h"),
    rule("ram-90", "RAM over 90%", f'max by (node) (1 - node_memory_MemAvailable_bytes{{{HOSTS}}} / node_memory_MemTotal_bytes{{{HOSTS}}}) > bool 0.9',
         "{{ .Labels.node }} RAM is over 90%", "For 15 minutes. Something uses too much memory.", "warning", "15m"),
    rule("crowdsec", "CrowdSec detected an attack", '(sum by (name) (increase(cs_bucket_overflowed_total[10m])) or vector(0)) > bool 0',
         "CrowdSec: {{ .Labels.name }}", "An attack pattern matched (watch only, nothing was blocked). See Grafana → Security.", "warning", "0s"),
    rule("ssh-bruteforce", "Many failed SSH logins", 'sum(count_over_time({host="lxc102", unit="ssh.service"} |~ "Failed password|Invalid user|authentication failure" [10m])) > 10',
         "More than 10 failed SSH logins on LXC 102 in 10 min", "Someone is guessing passwords.", "warning", "0s", ds=LOKI),
    # OPNsense runs on pve2, which is often off on purpose -> only alert while pve2 is up.
    rule("opnsense-logs", "OPNsense stopped sending logs", 'sum(count_over_time({job="opnsense"}[30m])) or vector(0)',
         "OPNsense sent no firewall logs for 30 min", "pve2 is on, but OPNsense sends no logs. Check OPNsense remote logging / Alloy.",
         "warning", "5m", ds=LOKI, extra=[("B", PROM, 'max(up{job="proxmox-host", node="pve2"}) or vector(0)')],
         math="$A < 1 && $B == 1"),
    # "< bool 1" gives 1 = no logs, 0 = fine (a plain "< 1" returned 0 when broken, so it could never fire)
    rule("logs-stopped", "Log collection stopped", '(sum(count_over_time({job=~".+"}[15m])) or vector(0)) < bool 1',
         "No logs stored for 15 min", "Loki or Alloy is down.", "warning", "5m", ds=LOKI),
    rule("target-down", "Monitoring target down", f'max by (job) (up{{job!~"proxmox-host|other-hosts"}}) < bool 1',
         "Monitoring part '{{ .Labels.job }}' is down", "An exporter is not answering (pve, crowdsec, adguard, fritzbox, ...).", "warning", "10m"),
    rule("new-device", "New device joined the network",
         '(max(fritz_known_devices_count) - max(fritz_known_devices_count offset 15m)) > bool 0',
         "A new device joined your home network", "The FRITZ!Box saw a device for the first time. Yours? If not: FRITZ!Box → Heimnetz → Netzwerk.",
         "warning", "0s"),
    rule("fritz-update", "FRITZ!Box update available", '(max(fritz_update_available) or vector(0)) > bool 0',
         "FRITZ!Box update available", "Install it in the FRITZ!Box UI (System → Update).", "warning", "1h"),
]

GAMES = [
    # 1 = was running in the last 10 min AND is not running now. Ends by itself after 10 min (no "OK again").
    # Servers whose panel is unreachable (pve2 off) have no data -> no alert.
    rule("game-stopped", "Game server stopped",
         'max by (platform, server) ((max_over_time(game_server_up[10m]) == bool 1) * (game_server_up == bool 0))',
         "{{ .Labels.server }} stopped ({{ .Labels.platform }})",
         "It was running and is not anymore. If you stopped it yourself, ignore this.", "game", "1m"),
]

doc = {"apiVersion": 1, "groups": [
    {"orgId": 1, "name": "critical", "folder": "Homelab", "interval": "1m", "rules": CRIT},
    {"orgId": 1, "name": "warning", "folder": "Homelab", "interval": "1m", "rules": WARN},
    {"orgId": 1, "name": "games", "folder": "Homelab", "interval": "30s", "rules": GAMES}]}
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "compose", "monitoring",
                   "grafana", "provisioning", "alerting", "rules.yml")
with open(out, "w") as f:
    f.write("# GENERATED by scripts/grafana/gen_alerts.py - edit that, not this file.\n")
    json.dump(doc, f, indent=2, ensure_ascii=False)   # JSON is valid YAML
    f.write("\n")
print(len(CRIT), "critical +", len(WARN), "warning +", len(GAMES), "game rules")
