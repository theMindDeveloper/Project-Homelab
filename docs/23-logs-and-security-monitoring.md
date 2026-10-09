# Logs and security monitoring

**Who is knocking on the door, from where, and did anything look like an
attack.** Built in October 2026 on top of the existing Prometheus and Grafana
(see [08 · Monitoring](08-monitoring.md)). It **only watches and reports.
Nothing in it blocks traffic.**

Step by step: [runbook 21](../runbooks/21-logs-and-crowdsec.md) (Loki, Alloy,
CrowdSec, OPNsense remote log) and [runbook 22](../runbooks/22-real-visitor-ip-behind-a-tunnel.md)
(real visitor IPs for the website). Files:
[`compose/security/`](../compose/security/).

---

## Why logs, when there are already metrics

Prometheus answers *how much*: "the firewall passed 41 connections in the last
hour". It cannot answer *who*: which address, from which city, to which game,
with what result. Those are single events with many details each, and that is
what a log line is.

Storing every visitor IP as a Prometheus label would be the cardinality
explosion described in [docs/08](08-monitoring.md#the-data-model). Logs are the
right tool for "who", metrics for "how much", and Grafana puts both on one
dashboard.

---

## The pieces

| Container | Job | Memory cap |
|---|---|---:|
| **Loki** | the log database. Keeps 30 days, reachable only on the Docker network | 512 MB |
| **Alloy** | the log collector. Reads the LXC 102 journal and the OPNsense firewall log, splits lines into fields, adds country and city | 320 MB |
| **CrowdSec** | reads those logs back from Loki and recognises attack patterns. Watch only | 256 MB |
| **adguard-exporter** | AdGuard DNS statistics as Prometheus numbers | 64 MB |

Real use is roughly a third of the caps (~190 MB together on a quiet day).

All four run from [`compose/security/docker-compose.example.yml`](../compose/security/docker-compose.example.yml),
started in the **same compose project** as the monitoring stack, so Grafana,
Prometheus, Loki and CrowdSec find each other by name.

**Keep internet-facing containers off that network.** Loki has no login, and
pve-exporter has a property worth knowing: it sends its Proxmox API token to
**whatever host** a caller names in `/pve?target=...`. Anything that can reach
pve-exporter can therefore make it hand the token to a server of its choice.
That is fine on a network that only holds the monitoring containers. It is not
fine if the public website or the tunnel connector sits on the same Docker
network, because then a compromised website is one HTTP request away from the
Proxmox token. Give the monitoring containers their own network (the compose
examples do: `networks: [monitoring]`).

Check that the separation really holds (run on the Docker host; the names are
from this lab, the project is called `stacks`):

```bash
docker network inspect stacks_default -f '{{range .Containers}}{{.Name}} {{end}}'
# -> only the website, the tunnel connector and FTP
docker network inspect stacks_monitoring -f '{{range .Containers}}{{.Name}} {{end}}'
# -> Prometheus, Grafana, Loki, Alloy, CrowdSec and the exporters
docker exec stacks-webserver-1 getent hosts pve-exporter loki
# -> prints nothing: the website cannot even find them by name
```

Moving the containers to the new network recreates them (`docker compose up -d`);
the data volumes stay, and monitoring is blind for about a minute.

**Anyone on the LAN can send syslog to UDP 1514.** Alloy cannot check who sent
a line, so a device on the LAN could inject fake firewall lines (fake visitors
on the map, a fake CrowdSec alert). Low impact for a watch-only setup; a host
firewall rule that only accepts 1514 from the OPNsense address closes it.

---

## Where the logs come from

### 1 · The LXC 102 journal (SSH and every container)

Docker on LXC 102 uses the **journald logging driver**: everything a container
prints ends up in the systemd journal, tagged with the container's name. So one
source, the journal, covers SSH logins (`ssh.service`) **and** the output of
every container, including Apache.

Alloy reads the journal directly (`loki.source.journal`, with `/var/log/journal`
and `/etc/machine-id` mounted read-only) and gives each line a few labels:
`unit`, `container`, `host`, `level`.

### 2 · The OPNsense firewall log

OPNsense sends its packet-filter log (`filterlog`) as syslog to LXC 102, UDP port
1514, which is the only port of the whole security stack published on the LAN.

Each `filterlog` line is CSV. An IPv4 example, split by Alloy into fields:

```
57,,,fae5...,vtnet1,match,pass,out,4,0x0,,64,0,0,DF,17,udp,61,<src>,10.10.10.21,10467,<dst port>
 |              |        |    |   |                    |      |     |           |     |
rule         interface action dir ipver            proto  src   dst      src port  dst port
```

Alloy's two regular expressions (one for IPv4, one for IPv6) are in
[`config.alloy`](../compose/security/config.alloy), with the field order
from the OPNsense documentation in a comment above them.

**Where the game traffic shows up is not where you would guess.** A player's
connection arrives at OPNsense's WAN side from the FRITZ!Box forward, is
translated, and leaves on the DMZ side towards the game server. OPNsense logs
it **on the DMZ interface (`vtnet1`), direction `out`**, by the rule that lets
DMZ traffic out. That line has the player's real address as source and the
game server as destination, so that is the line to count.

Ticking "log" on the WAN rules as well would log every connection a second
time. Don't.

### 3 · The website, with the real visitor address

The one website is reached through a Cloudflare tunnel. Without help, Apache
only ever sees the cloudflared container as the visitor, so every request
"comes from" `172.19.0.4`. Apache's `mod_remoteip` fixes that by reading the
real address from the `CF-Connecting-IP` header Cloudflare adds, **but only when
the request comes from a Docker network** (where cloudflared lives). From the LAN
the header is ignored, so nobody can fake their address by sending the header
themselves.

How, in three lines of `httpd.conf`: [runbook 22](../runbooks/22-real-visitor-ip-behind-a-tunnel.md).
Alloy then splits each Apache line (`combined` format) into IP, method, path,
status and user agent, labels it `job="apache"`, and adds the location.

---

## Loki: labels small, details in metadata

Loki indexes **labels only**. Every unique combination of labels is one
*stream*, and like Prometheus series, too many streams kill it. So:

| Kept as a **label** (few values) | Kept as **structured metadata** (any value) |
|---|---|
| `job` (opnsense, apache), `host`, `unit`, `container` | `src_ip`, `dst_ip`, `src_port`, `dst_port` |
| `action` (pass, block), `dir` (in, out), `iface`, `proto` | `country`, `city`, `lat`, `lon` |
| `level` | `method`, `path`, `status`, `user_agent` |

Structured metadata is stored with each line and is filterable, but does not
create streams. A busy day of scanners from 400 addresses is 400 values in
metadata and still a handful of streams.

### LogQL, the parts actually used

LogQL looks like PromQL with a log selector in front:

```logql
# every firewall line from the internet (private, loopback and CGNAT sources dropped)
{job="opnsense"} | src_ip!~"(10|127)\\..*|192\\.168\\..*|172\\.(1[6-9]|2[0-9]|3[01])\\..*|100\\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\\..*|"

# internet -> game servers (the DMZ-side line, see above)
{job="opnsense", action="pass", iface="vtnet1", dir="out"} | dst_ip=~"10\\.10\\.10\\.(20|21)"

# how many in the selected time range, as a number for a stat panel
sum(count_over_time({job="opnsense", action="block"} [$__range]))

# per country, for a bar chart
topk(12, sum by (country) (count_over_time({job="apache"} | country!="" [$__range])))

# failed SSH logins on LXC 102
{host="lxc102", unit="ssh.service"} |~ "Failed password|Invalid user|authentication failure"

# a readable live feed
{job="apache"} | line_format "{{ .status }} {{ .method }} {{ .path }} · {{ .src_ip }} ({{ .city }}, {{ .country }})"
```

**Drop private sources, or "blocked" fills with your own house.** OPNsense's
WAN side sits in the house LAN (it is a firewall *inside* the home network, see
[docs/12](12-network-segmentation.md)), so it sees every broadcast from every
home device: NetBIOS, mDNS, Syncthing discovery. All of that is "blocked
inbound". It is harmless and it is noise; every security panel filters it out
with the `src_ip!~` pattern above.

---

## Locations: GeoIP

Alloy's `stage.geoip` looks every source address up in a local database and adds
`country`, `country_iso`, `city`, `lat`, `lon`. The database is the free
**DB-IP "IP to City Lite"** (CC BY 4.0, no account needed), one `.mmdb` file of
about 125 MB:

```bash
curl -fsSL https://download.db-ip.com/free/dbip-city-lite-$(date +%Y-%m).mmdb.gz \
  | gunzip > /opt/security/geoip/dbip-city-lite.mmdb
```

- It is **not in Git** (size, and it changes monthly).
- DB-IP publishes a new file every month. An old file keeps working and slowly
  gets less accurate. Refreshing it is a manual step today.
- Private addresses get no location, which is correct.
- "City" for a cloud server is the data centre, not a person. A dot in Frankfurt
  is very often a rented server, not a player in Frankfurt.

MaxMind's GeoLite2 is the better-known alternative; it needs a free account and
a licence key. DB-IP needs neither, which is why it was chosen.

---

## The world map

The Security and Games dashboards show every internet connection as a dot on a
dark world map (Grafana's *Geomap* panel, markers sized by number of
connections). Two lessons from building it:

- **The default map tiles now need an API key.** Grafana's default basemap is
  CARTO, which since 2026 answers without a key with tiles that just say "API
  KEY REQUIRED". OpenStreetMap tiles (`osm-standard`) work without a key but are
  bright. The dashboards use ESRI's free "World Dark Gray Base" as an XYZ tile
  layer, no key, dark.
- **3D was considered and dropped.** A spinning globe exists as a plugin, looks
  great and is harder to read. Flat map, bars and tables answer the questions.

---

## CrowdSec, watch only

CrowdSec reads log lines, runs them through **parsers** (turn a line into fields)
and **scenarios** (a pattern over time: "10 failed SSH logins from one address
within a minute is brute force"). When a scenario matches, it raises an **alert**
and writes a **decision** ("ban this address for 4 hours").

A decision does nothing on its own. Something has to enforce it: a **bouncer**,
which is a separate component that plugs into a firewall, a web server or a
reverse proxy. **This lab installs no bouncer**, on purpose:

- A wrong ban can lock out a player or yourself. Watching first shows how often
  it would be wrong.
- Blocking is a decision for later, with data from weeks of watching.

What is set up:

| Setting | Value | Why |
|---|---|---|
| Acquisition | from **Loki** (`source: loki`) | no second log agent, no file mounts; CrowdSec reads what Alloy already collected |
| Collections | `crowdsecurity/sshd`, `crowdsecurity/apache2`, `firewallservices/pf` | SSH brute force, web scans and exploits, port scans in the firewall log |
| Online API | off (`DISABLE_ONLINE_API=true`) | nothing is sent to crowdsec.net |
| Private addresses | whitelisted (CrowdSec default) | LAN mistakes never count as attacks |
| Metrics | `:6060`, scraped by Prometheus | lines read, parsed, alerts, would-block decisions |

The acquisition file is [`acquis.yaml`](../compose/security/acquis.yaml): three
Loki queries, one per log type, each tagged with the parser to use.

**Without the real visitor IP, CrowdSec is blind for the website.** Behind a
tunnel every request comes from the same Docker address, which is private and
whitelisted, so no web scenario can ever fire. The `mod_remoteip` change above
is what makes the Apache collection useful at all.

---

## DNS and the home network as security signals

Two cheap sources that are easy to forget:

- **AdGuard Home** (via `adguard-exporter`): which device asks for what, which
  share is blocked, which domains are blocked most. A device that suddenly
  makes thousands of lookups, or asks for strange domains, shows here first.
- **The FRITZ!Box** (via `fritz-exporter`, see
  [runbook 24](../runbooks/24-fritzbox-monitoring.md)): **new devices** (the
  router's "known devices" count goes up), Wi-Fi clients right now, whether
  **remote access (MyFRITZ)** is on, whether a **firmware update** waits,
  reconnects, and download vs upload. A long upload spike nobody can explain is
  worth a look. A new device joining raises a 🟠 alert.

---

## What the dashboards show

**Homelab · Security** (top to bottom): six numbers (connections from the
internet, unique IPs, countries, website requests, blocked, CrowdSec alerts) ·
the dark world map with game traffic in blue and website visitors in orange ·
top countries · traffic over time · what they reach · top visitors · a live feed
· "guards" (failed SSH, web attack probes, CrowdSec, DNS) · home network &
router. Folded **"Details ·"** sections: Firewall, Website, SSH logins,
CrowdSec, DNS, Log pipeline health.

**Homelab · Games**: the same map and tables for the game servers only, with
the game named per connection. See [runbook 25](../runbooks/25-game-server-monitoring.md).

### How to read it

- **Many addresses with one or two connections each** are scanners and
  server-list pings. Every open game port gets them, all day, from everywhere.
- **One address coming back again and again over an evening** is a player.
- **"Blocked from internet: 0"** is normal: the FRITZ!Box only forwards the game
  ports, so almost nothing else ever reaches OPNsense from outside.
- **Web attack probes** (`wp-login.php`, `.env`, `.git`, `phpmyadmin`) on a
  site that has none of these are bots trying their luck. They are the reason
  the website runs in a container with nothing else of value on it.

---

## Country blocking: possible, deliberately not done

Asked and decided in October 2026. It is possible in two places: OPNsense
(GeoIP aliases plus one block rule, needs a free MaxMind account) for the game
ports, and Cloudflare (a WAF custom rule, two minutes, free plan) for the
website. The FRITZ!Box cannot do it.

It was not done, because:

- It is **noise reduction, not protection**. Anyone serious rents a server in
  the country you allow. One "attacker" in the data was a cloud server in
  Frankfurt.
- Blocking the US can **break game server lists** (Steam's master servers) and
  friends on VPNs.
- It needs new accounts, and the dashboards already show the traffic clearly.

The data to decide later is collecting itself.

---

## What is not covered

- **Logins on the Proxmox nodes, the Pi and the NAS.** Only LXC 102's journal is
  collected. A Proxmox web-UI brute force would not show up. A small log
  shipper per machine (Alloy or `rsyslog` forwarding) would close this.
- **Blocking.** By design, see above.
- **Traffic between devices inside the house.** OPNsense only sees what crosses
  it, which is the DMZ. The house network is flat (see the README's known
  limitations).
- **GeoIP refresh** is manual, monthly.

---

**Next:** [24 · Alerting](24-alerting.md) — turning all of this into a message
on your phone, without crying wolf.
