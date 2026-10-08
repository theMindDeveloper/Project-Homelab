"""Homelab · Hosts: one detailed page per machine, switch at the top (pve, pve2, pve3, pi, nas)."""
from lib import *

H = 'node="$host", job=~"proxmox-host|other-hosts"'
DISK = 'device=~"nvme[0-9]+n[0-9]+|sd[a-z]+|mmcblk[0-9]+"'
NET = 'device!~"lo|veth.*|tap.*|fw.*|docker.*|br-.*|vmbr.*tap.*|tailscale.*"'
FS = 'fstype!~"tmpfs|overlay|squashfs|ramfs|devtmpfs|nsfs|fuse.*|autofs|proc|sysfs", mountpoint!~"/etc/.*|/boot/efi|/run.*"'
CORES = f'count(node_cpu_seconds_total{{{H},mode="idle"}})'

def build(path):
    D = Dash("Homelab · Hosts", "homelab-hosts", ["homelab", "hosts"], links=NAV, refresh="30s", time_from="now-6h",
             desc="Everything about one machine. Pick it with the Host switch at the top.")
    D.var_custom("host", "Host", ["pve", "pve2", "pve3", "pi", "nas"], "pve")
    P = Dash.prom

    # ---- status -------------------------------------------------------------------------------
    D.row("$host — status")
    D.stat("State", [P(f'max(up{{{H}}}) or vector(0)', instant=True)], 0, 3, mappings=UPDOWN, th=thr(BAD, 1, GOOD))
    D.stat("Uptime", [P(f'max(time() - node_boot_time_seconds{{{H}}})', instant=True)], 3, 3, unit="s",
           th=thr(WARN, 86400, GOOD), desc="Orange = rebooted in the last 24 h.")
    D.stat("CPU cores", [P(CORES, instant=True)], 6, 3, th=thr(INFO), color_mode="value")
    D.stat("RAM", [P(f'max(node_memory_MemTotal_bytes{{{H}}})', instant=True)], 9, 3, unit="bytes", th=thr(INFO),
           color_mode="value", decimals=1)
    D.stat("System", [P(f'max by (machine, release) (node_uname_info{{{H}}})', legend="{{machine}} · kernel {{release}}", instant=True)],
           12, 12, th=thr(NEUTRAL), color_mode="none", text_mode="name")
    D.next_row(4)
    D.gauge("CPU", [P(f'1 - avg(rate(node_cpu_seconds_total{{{H},mode="idle"}}[5m]))', instant=True)], 0, 4, h=6)
    D.gauge("RAM", [P(f'1 - max(node_memory_MemAvailable_bytes{{{H}}} / node_memory_MemTotal_bytes{{{H}}})', instant=True)], 4, 4, h=6)
    D.gauge("Swap", [P(f'max(1 - node_memory_SwapFree_bytes{{{H}}} / (node_memory_SwapTotal_bytes{{{H}}} > 0)) or vector(0)', instant=True)],
            8, 4, h=6, desc="0% if the machine has no swap.")
    D.gauge("Fullest disk", [P(f'max(1 - node_filesystem_avail_bytes{{{H},{FS}}} / node_filesystem_size_bytes{{{H},{FS}}})', instant=True)],
            12, 4, h=6)
    D.gauge("Hottest sensor", [P(f'max(node_thermal_zone_temp{{{H}}} or node_hwmon_temp_celsius{{{H}}})', instant=True)],
            16, 4, h=6, unit="celsius", th=TEMP, mx=100, decimals=0)
    D.gauge("Load per core", [P(f'max(node_load5{{{H}}}) / {CORES}', instant=True)], 20, 4, h=6,
            th=thr(GOOD, 0.8, WARN, 1, BAD), mx=1.5, desc="5-min load ÷ cores. Above 100% = work waits for the CPU.")
    D.next_row(6)

    # ---- CPU --------------------------------------------------------------------------------
    D.row("CPU")
    D.ts("CPU by type of work", [P(f'sum by (mode) (rate(node_cpu_seconds_total{{{H},mode!="idle"}}[$__rate_interval])) / scalar({CORES})', "{{mode}}")],
         0, 12, 8, unit="percentunit", stack=True, mn=0, fill=60,
         desc="user = programs, system = kernel, iowait = waiting for disks, steal = taken by the hypervisor.")
    D.ts("Load vs cores", [P(f'max(node_load1{{{H}}})', "load 1 min"), P(f'max(node_load5{{{H}}})', "load 5 min", ref="B"),
                           P(f'max(node_load15{{{H}}})', "load 15 min", ref="C"), P(CORES, "cores", ref="D")],
         12, 12, 8, desc="Load above the 'cores' line = more work than the CPU can do.",
         overrides=[{"matcher": {"id": "byName", "options": "cores"}, "properties": [
             {"id": "custom.lineStyle", "value": {"fill": "dash", "dash": [10, 10]}},
             {"id": "color", "value": {"mode": "fixed", "fixedColor": BAD}}, {"id": "custom.fillOpacity", "value": 0}]}])
    D.next_row(8)
    D.ts("Is it struggling? (pressure)", [
            P(f'max(rate(node_pressure_cpu_waiting_seconds_total{{{H}}}[$__rate_interval]))', "CPU"),
            P(f'max(rate(node_pressure_memory_waiting_seconds_total{{{H}}}[$__rate_interval]))', "memory", ref="B"),
            P(f'max(rate(node_pressure_io_waiting_seconds_total{{{H}}}[$__rate_interval]))', "disk I/O", ref="C")],
         0, 12, 8, unit="percentunit", mn=0, th=thr(GOOD, 0.1, WARN, 0.3, BAD),
         desc="Share of time tasks had to WAIT for CPU, memory or disk. Near 0 = relaxed. Over 10% = something is short.")
    D.ts("Processes", [P(f'max(node_procs_running{{{H}}})', "running"), P(f'max(node_procs_blocked{{{H}}})', "blocked (waiting for I/O)", ref="B")],
         12, 12, 8, mn=0)
    D.next_row(8)

    # ---- memory -----------------------------------------------------------------------------
    D.row("Memory")
    M = lambda m: f'max(node_memory_{m}_bytes{{{H}}})'
    D.ts("Where the RAM goes", [
            P(f'{M("MemTotal")} - {M("MemFree")} - {M("Buffers")} - {M("Cached")} - {M("SReclaimable")}', "used by programs"),
            P(f'{M("Cached")} + {M("SReclaimable")}', "cache (freed when needed)", ref="B"),
            P(M("Buffers"), "buffers", ref="C"), P(M("MemFree"), "free", ref="D")],
         0, 16, 8, unit="bytes", stack=True, fill=60, mn=0,
         overrides=[{"matcher": {"id": "byName", "options": n}, "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]}
                    for n, c in (("used by programs", "#F2495C"), ("cache (freed when needed)", "#5794F2"), ("buffers", "#8AB8FF"), ("free", "#73BF69"))])
    D.ts("Swap used", [P(f'{M("SwapTotal")} - {M("SwapFree")}', "swap used")], 16, 8, 8, unit="bytes", mn=0,
         desc="Swap growing = RAM is too small for what runs.")
    D.next_row(8)

    # ---- disks --------------------------------------------------------------------------------
    D.row("Disks")
    D.bargauge("How full (per filesystem)", [P(f'max by (mountpoint) (1 - node_filesystem_avail_bytes{{{H},{FS}}} / node_filesystem_size_bytes{{{H},{FS}}})', "{{mountpoint}}", instant=True)],
               0, 8, 9, mode="lcd", desc="NAS: one entry per volume (/disks/volumeN).")
    D.ts("Throughput (+ read / − write)", [
            P(f'sum by (device) (rate(node_disk_read_bytes_total{{{H},{DISK}}}[$__rate_interval]))', "{{device}} read"),
            P(f'-sum by (device) (rate(node_disk_written_bytes_total{{{H},{DISK}}}[$__rate_interval]))', "{{device}} write", ref="B")],
         8, 8, 9, unit="Bps", mn=None)
    D.ts("Busy time per disk", [P(f'sum by (device) (rate(node_disk_io_time_seconds_total{{{H},{DISK}}}[$__rate_interval]))', "{{device}}")],
         16, 8, 9, unit="percentunit", mn=0, mx=1, th=thr(GOOD, 0.6, WARN, 0.9, BAD),
         desc="How much of the time the disk was busy. Near 100% = the disk is the bottleneck.")
    D.next_row(9)
    D.ts("Operations per second", [
            P(f'sum by (device) (rate(node_disk_reads_completed_total{{{H},{DISK}}}[$__rate_interval]))', "{{device}} reads"),
            P(f'-sum by (device) (rate(node_disk_writes_completed_total{{{H},{DISK}}}[$__rate_interval]))', "{{device}} writes", ref="B")],
         0, 12, 8, unit="iops", mn=None)
    D.ts("Average wait per operation", [
            P(f'sum by (device) (rate(node_disk_read_time_seconds_total{{{H},{DISK}}}[$__rate_interval])) / sum by (device) (rate(node_disk_reads_completed_total{{{H},{DISK}}}[$__rate_interval]) > 0)', "{{device}} read"),
            P(f'sum by (device) (rate(node_disk_write_time_seconds_total{{{H},{DISK}}}[$__rate_interval])) / sum by (device) (rate(node_disk_writes_completed_total{{{H},{DISK}}}[$__rate_interval]) > 0)', "{{device}} write", ref="B")],
         12, 12, 8, unit="s", mn=0, th=thr(GOOD, 0.02, WARN, 0.1, BAD),
         desc="Milliseconds per read/write. SSD: under 1 ms. HDD: under 20 ms. Higher = slow or dying disk.")
    D.next_row(8)

    # ---- network ------------------------------------------------------------------------------
    D.row("Network")
    D.ts("Traffic per interface (+ in / − out)", [
            P(f'sum by (device) (rate(node_network_receive_bytes_total{{{H},{NET}}}[$__rate_interval]))', "{{device}} in"),
            P(f'-sum by (device) (rate(node_network_transmit_bytes_total{{{H},{NET}}}[$__rate_interval]))', "{{device}} out", ref="B")],
         0, 12, 8, unit="Bps", mn=None, desc="NAS: exporter runs in bridge mode, so this shows only its own traffic.")
    D.ts("Errors and drops", [
            P(f'sum by (device) (rate(node_network_receive_errs_total{{{H},{NET}}}[$__rate_interval]) + rate(node_network_transmit_errs_total{{{H},{NET}}}[$__rate_interval]))', "{{device}} errors"),
            P(f'sum by (device) (rate(node_network_receive_drop_total{{{H},{NET}}}[$__rate_interval]) + rate(node_network_transmit_drop_total{{{H},{NET}}}[$__rate_interval]))', "{{device}} drops", ref="B")],
         12, 6, 8, unit="pps", mn=0, desc="Should be flat at 0. Errors = cable/port problems.")
    D.ts("Open TCP connections", [P(f'max(node_netstat_Tcp_CurrEstab{{{H}}})', "established")], 18, 6, 8, mn=0)
    D.next_row(8)

    # ---- temperatures -------------------------------------------------------------------------
    D.row("Temperatures")
    D.ts("All sensors", [P(f'max by (chip, sensor) (node_hwmon_temp_celsius{{{H}}})', "{{chip}} {{sensor}}"),
                         P(f'max by (type) (node_thermal_zone_temp{{{H}}})', "{{type}}", ref="B")],
         0, 16, 8, unit="celsius", th=TEMP)
    D.bargauge("Now", [P(f'max by (chip) (node_hwmon_temp_celsius{{{H}}})', "{{chip}}", instant=True),
                       P(f'max by (type) (node_thermal_zone_temp{{{H}}})', "{{type}}", ref="B", instant=True)],
               16, 8, 8, mode="lcd", unit="celsius", th=TEMP, mx=100)
    D.next_row(8)

    # ---- Proxmox guests on this host ----------------------------------------------------------
    D.row("Proxmox guests on $host (empty for pi / nas)")
    GI = 'max by (id, name, type) (pve_guest_info{template="0", node="$host"})'
    J = lambda e: f'max by (id, name, type) (max by (id) ({e}) * on (id) group_left(name, type) {GI})'
    D.table("Guests", [P(J('pve_up'), ref="A", instant=True, fmt="table"),
                       P(J('pve_cpu_usage_ratio'), ref="B", instant=True, fmt="table"),
                       P(J('pve_memory_usage_bytes'), ref="C", instant=True, fmt="table"),
                       P(J('pve_memory_size_bytes'), ref="D", instant=True, fmt="table"),
                       P(J('pve_uptime_seconds'), ref="E", instant=True, fmt="table")],
            0, 12, 8, [("id", "ID", "string", None, None, 90), ("name", "Name", "string", None, None),
                       ("type", "Type", "string", None, None, 70),
                       ("A", "State", "string", thr(BAD, 1, GOOD), BG_CELL, 90), ("B", "CPU", "percentunit", PCT, BAR_CELL),
                       ("C", "RAM used", "bytes", None, None, 100), ("D", "RAM size", "bytes", None, None, 100),
                       ("E", "Uptime", "s", None, None, 100)], sort=[{"displayName": "ID"}])
    for o in D.d["panels"][-1]["fieldConfig"]["overrides"]:
        if o["matcher"]["options"] == "State":
            o["properties"].append({"id": "mappings", "value": [{"type": "value", "options": {
                "0": {"text": "stopped", "index": 0}, "1": {"text": "running", "index": 1}}}]})
    D.ts("Guest CPU (cores used)", [P('topk(8, ' + J('pve_cpu_usage_ratio * pve_cpu_usage_limit') + ')', "{{name}}")], 12, 12, 8, mn=0)
    D.next_row(8)
    return D.save(path)
