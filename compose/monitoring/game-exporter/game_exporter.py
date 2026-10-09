#!/usr/bin/env python3
"""game-exporter: tells Prometheus which game servers run (AMP + Pterodactyl). READ-ONLY.

Metrics (port 9788):
  game_server_up{platform, server}            1 = game is running and ready, 0 = not
  game_server_state{platform, server, state}  1 for the current state (e.g. ready, starting, stopped, failed, offline)
  game_exporter_api_up{platform}              1 = the panel API answered, 0 = it didn't (e.g. pve2 is off)
  game_server_players{platform, server}       players online (AMP only; Pterodactyl has no player count)
  game_server_players_max{platform, server}   player slots (AMP only)
  game_server_cpu_percent{platform, server}   CPU use of the game (AMP: % of its limit, Pterodactyl: % of one core)
  game_server_memory_bytes{platform, server}  RAM use of the game
  game_server_disk_bytes{platform, server}    disk use (Pterodactyl only)
  game_server_uptime_seconds{platform, server} running for (Pterodactyl: from the panel; AMP: since this exporter saw it start)
  game_server_port_info{platform, server, host, port} 1 = the game listens on this address
If a panel can't be reached (pve2 switched off), its servers are simply left out -> no "stopped" alerts.
Only Python's standard library. Config via environment (see game-exporter.env, not in Git).
"""
import json, os, time, urllib.parse, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AMP_URL = os.environ.get("AMP_URL", "").rstrip("/")          # e.g. http://10.10.10.21:8080
AMP_USER, AMP_PASS = os.environ.get("AMP_USER", ""), os.environ.get("AMP_PASS", "")
PTERO_URL = os.environ.get("PTERO_URL", "").rstrip("/")      # e.g. http://10.10.10.22
PTERO_KEY = os.environ.get("PTERO_KEY", "")
TIMEOUT = 10
UA = "homelab-game-exporter/1"   # the panel blocks Python's default user agent

# AMP AppState numbers -> words (from AMP's API docs)
AMP_STATES = {-1: "undefined", 0: "stopped", 5: "pre_start", 7: "configuring", 10: "starting", 20: "ready",
              30: "restarting", 40: "stopping", 45: "preparing_sleep", 50: "sleeping", 60: "waiting",
              70: "installing", 75: "updating", 80: "awaiting_input", 100: "failed", 200: "suspended",
              250: "maintenance", 999: "indeterminate"}
AMP_READY = {20}

_amp_session = None


def _req(url, data=None, headers=None):
    h = {"Accept": "application/json", "User-Agent": UA, **(headers or {})}
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        h["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url, data=body, headers=h), timeout=TIMEOUT) as r:
        return json.load(r)


def _amp_call(method, payload):
    global _amp_session
    for attempt in (1, 2):
        if not _amp_session:
            login = _req(f"{AMP_URL}/API/Core/Login",
                         {"username": AMP_USER, "password": AMP_PASS, "token": "", "rememberMe": False})
            _amp_session = login.get("sessionID")
            if not _amp_session:
                raise RuntimeError("AMP login failed")
        res = _req(f"{AMP_URL}/API/{method}", {"SESSIONID": _amp_session, **payload})
        if isinstance(res, dict) and res.get("Title") == "Unauthorized Access" and attempt == 1:
            _amp_session = None          # session expired -> log in again once
            continue
        return res.get("result", res) if isinstance(res, dict) else res


_amp_started = {}   # server -> time we first saw it "ready" (AMP's list has no uptime)


def amp_servers():
    out = []
    amp_host = urllib.parse.urlparse(AMP_URL).hostname
    for target in _amp_call("ADSModule/GetInstances", {}):
        for i in target.get("AvailableInstances", []):
            if i.get("Module") == "ADS":
                continue                  # the controller itself, not a game
            name = i.get("FriendlyName") or i.get("InstanceName")
            code = i.get("AppState", -1) if i.get("Running") else 0
            up = code in AMP_READY
            if up:
                _amp_started.setdefault(name, time.time())
            else:
                _amp_started.pop(name, None)
            m = i.get("Metrics") or {}
            users, cpu, mem = m.get("Active Users") or {}, m.get("CPU Usage") or {}, m.get("Memory Usage") or {}
            ports = sorted({int(e["Endpoint"].rsplit(":", 1)[1]) for e in i.get("ApplicationEndpoints", [])
                            if e.get("DisplayName") != "SFTP Server" and ":" in e.get("Endpoint", "")})
            out.append({"name": name, "state": AMP_STATES.get(code, f"code_{code}"), "up": up,
                        "players": users.get("RawValue") if up else 0, "players_max": users.get("MaxValue"),
                        "cpu": cpu.get("Percent") if up else 0,
                        "mem": (mem.get("RawValue") or 0) * 1024 * 1024 if up else 0,   # AMP reports MB
                        "uptime": time.time() - _amp_started[name] if up else 0,
                        "host": amp_host, "ports": ports})
    return out


def ptero_servers():
    hdr = {"Authorization": f"Bearer {PTERO_KEY}"}
    out = []
    for s in _req(f"{PTERO_URL}/api/client?include=allocations", headers=hdr)["data"]:
        a = s["attributes"]
        r = _req(f"{PTERO_URL}/api/client/servers/{a['identifier']}/resources", headers=hdr)["attributes"]
        res, st = r.get("resources", {}), r["current_state"]
        allocs = [x["attributes"] for x in a.get("relationships", {}).get("allocations", {}).get("data", [])]
        out.append({"name": a["name"], "state": st, "up": st == "running", "players": None, "players_max": None,
                    "cpu": res.get("cpu_absolute"), "mem": res.get("memory_bytes"), "disk": res.get("disk_bytes"),
                    "uptime": (res.get("uptime") or 0) / 1000,
                    "host": allocs[0]["ip"] if allocs else "", "ports": sorted({x["port"] for x in allocs})})
    return out


def _esc(v):
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def collect():
    lines = ["# HELP game_server_up 1 = game server running and ready.", "# TYPE game_server_up gauge",
             "# HELP game_server_state Current state of the game server (value 1).", "# TYPE game_server_state gauge",
             "# HELP game_exporter_api_up 1 = panel API answered.", "# TYPE game_exporter_api_up gauge"]
    for platform, fn, enabled in (("amp", amp_servers, AMP_URL), ("pterodactyl", ptero_servers, PTERO_URL)):
        if not enabled:
            continue
        try:
            servers = fn()
            lines.append(f'game_exporter_api_up{{platform="{platform}"}} 1')
        except Exception as e:  # panel down / pve2 off / timeout
            lines.append(f'game_exporter_api_up{{platform="{platform}"}} 0')
            print(f"{time.strftime('%F %T')} {platform}: {type(e).__name__}: {e}", flush=True)
            continue
        for g in servers:
            lab = f'platform="{platform}",server="{_esc(g["name"])}"'
            lines.append(f"game_server_up{{{lab}}} {1 if g['up'] else 0}")
            lines.append(f'game_server_state{{{lab},state="{_esc(g["state"])}"}} 1')
            for metric, key in (("players", "players"), ("players_max", "players_max"), ("cpu_percent", "cpu"),
                                ("memory_bytes", "mem"), ("disk_bytes", "disk"), ("uptime_seconds", "uptime")):
                if g.get(key) is not None:
                    lines.append(f"game_server_{metric}{{{lab}}} {float(g[key])}")
            for port in g["ports"]:
                lines.append(f'game_server_port_info{{{lab},host="{_esc(g["host"])}",port="{port}"}} 1')
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/metrics":
            self.send_response(404); self.end_headers(); return
        body = collect().encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass  # no access log spam


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "9788"))
    print(f"game-exporter listening on :{port}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
