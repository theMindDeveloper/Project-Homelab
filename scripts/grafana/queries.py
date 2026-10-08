"""LogQL / PromQL building blocks shared by the dashboards."""
# Only internet senders: drop private, loopback and "no IP" sources (house LAN broadcasts etc.).
PUB = r'src_ip!~"(10|127)\\..*|192\\.168\\..*|172\\.(1[6-9]|2[0-9]|3[01])\\..*|100\\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\\..*|0\\.0\\.0\\.0|"'
# Internet -> game servers. OPNsense logs it on the DMZ side (vtnet1, out) after the FRITZ!Box forward.
GAME = r'{job="opnsense", action="pass", iface="vtnet1", dir="out"} | dst_ip=~"10\\.10\\.10\\.(20|21)" | ' + PUB
# Internet -> website (Apache through the Cloudflare tunnel; real visitor IP via mod_remoteip).
WEB = r'{job="apache"} | ' + PUB
# Everything from the internet that reached something (game + web), with a "kind" label.
INET = (r'{job=~"opnsense|apache"} | job="apache" or (action="pass" and iface="vtnet1" and dir="out") | ' + PUB +
        r' | label_format kind=`{{ if eq .job "apache" }}website{{ else }}game servers{{ end }}`')
# Internet packets the firewall dropped.
BLOCK = r'{job="opnsense", action="block"} | ' + PUB
# Every firewall line from the internet.
FW_NET = r'{job="opnsense"} | ' + PUB
SSH = r'{host="lxc102", unit="ssh.service"}'
SSH_FAIL = SSH + r' |~ "Failed password|Invalid user|authentication failure|Connection closed by invalid user|maximum authentication attempts"'
SSH_OK = SSH + r' |= "Accepted "'
# Typical attack probes against websites.
WEB_PROBE = WEB + r' | path=~"(?i).*(wp-login|wp-admin|xmlrpc|\\.env|\\.git|phpmyadmin|/admin|/login|cgi-bin|\\.php|/shell|/boaform|/HNAP1|/actuator).*"'

def cnt(sel, rng="$__range"):
    return f"sum(count_over_time({sel} [{rng}])) or vector(0)"

def uniq(sel, by="src_ip", rng="$__range"):
    return f"count(sum by ({by}) (count_over_time({sel} [{rng}]))) or vector(0)"

# Which game listens on which port. FILL IN YOUR OWN. The game-exporter shows
# the real list live (game_server_port_info, and the "Ports" table on the Games
# dashboard), so a missing port is easy to spot: its connections show up as
# "other (port N)".
# The numbers below are EXAMPLES, not this lab's ports: game ports are never
# published (docs/99-security-notes.md), because a forward is usually one-to-one.
GAME_PORTS = {"11111": "Minecraft (AMP)", "22222": "Space Engineers (AMP)", "33333": "Terraria (AMP)",
              "44444": "Zomboid (Pterodactyl)", "44445": "Zomboid (Pterodactyl)", "55555": "Minecraft (Pterodactyl)"}

def _game_label():
    parts = "".join(f'{{{{ else if eq .dst_port "{p}" }}}}{g}' for p, g in GAME_PORTS.items())
    return "| label_format game=`{{ if false }}" + parts + "{{ else }}other (port {{ .dst_port }}){{ end }}`"

# Internet -> game servers, with a "game" label.
GAMEN = GAME + " " + _game_label()
