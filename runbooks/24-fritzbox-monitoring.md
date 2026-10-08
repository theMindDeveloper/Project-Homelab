# Runbook 24 · FRITZ!Box monitoring

**Goal** The router's numbers in Prometheus: internet up/down, DSL speed and line
quality, traffic, Wi-Fi clients, new devices, remote access and firmware status,
with an "Internet" row on the Overview and a "Home network & router" section on
the Security dashboard.

**Time** 15 minutes.
**Prerequisites** [Runbook 10](10-monitoring-stack.md). Admin access to the
FRITZ!Box web UI (`http://fritz.box` or `192.168.178.1`).
**Reverses cleanly?** Yes: delete the router user and the container.

Concepts: [docs/23](../docs/23-logs-and-security-monitoring.md#dns-and-the-home-network-as-security-signals).

---

## 0 · How it works

The FRITZ!Box has an API for apps called **TR-064** (port 49000 on the LAN).
[`fritz_exporter`](https://github.com/pdreker/fritz_exporter), a maintained
open-source exporter, asks it once a minute and turns the answers into
Prometheus numbers. It needs a FRITZ!Box user. That user gets **one** right and
no internet access.

---

## 1 · Check that TR-064 is on

Usually it already is. From any machine on the LAN:

```bash
curl -s http://192.168.178.1:49000/tr64desc.xml | grep -o '<modelName>[^<]*'
```

Prints the model name → on. Nothing → in the FRITZ!Box: **Heimnetz → Netzwerk →
Netzwerkeinstellungen → "Zugriff für Anwendungen zulassen"** (*Home Network →
Network → Network Settings → Allow access for applications*), tick, apply.

---

## 2 · A FRITZ!Box user just for monitoring

In the FRITZ!Box UI (German menu names, English in brackets):

1. **System → FRITZ!Box-Benutzer** (*FRITZ!Box Users*) → **Benutzer hinzufügen**
   (*Add User*).
2. Benutzername (*user name*): `monitoring`. Kennwort (*password*): a long random
   one, saved in your password manager.
3. **Zugang auch aus dem Internet erlaubt** (*access from the internet*): **off**.
4. **Berechtigungen** (*rights*): tick **only "FRITZ!Box Einstellungen"**
   (*FRITZ!Box settings*). Everything else off: voice messages, smart home,
   NAS contents, VPN.
5. **Übernehmen** (*Apply*). The box may ask for a confirmation by pressing a
   button on the box or on a connected phone. **Rights only take effect after
   that confirmation.**

"FRITZ!Box settings" sounds like a lot. Through TR-064 the exporter only ever
*reads*; it never calls a setter. The right is needed because the box treats
reading status as part of that permission.

---

## 3 · Test the login before involving Docker

```bash
U=monitoring; P='change-me'
curl -s --anyauth -u "$U:$P" http://192.168.178.1:49000/upnp/control/deviceinfo \
  -H 'Content-Type: text/xml; charset="utf-8"' \
  -H 'SoapAction: urn:dslforum-org:service:DeviceInfo:1#GetInfo' \
  -d '<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><u:GetInfo xmlns:u="urn:dslforum-org:service:DeviceInfo:1"/></s:Body></s:Envelope>' \
  | grep -oE '<NewModelName>[^<]*|<NewUpTime>[^<]*|errorDescription>[^<]*'
```

| Answer | Meaning |
|---|---|
| `NewModelName`, `NewUpTime` | works |
| HTTP 401 / nothing | wrong user name or password |
| `errorDescription>Action Not Authorized` (error 606) | password right, but the user lacks the right, **or the confirmation in step 2.5 was not done** |

---

## 4 · Start the exporter

On LXC 102, in `/opt/monitoring`:

```bash
cat > fritz.env <<'EOF'
FRITZ_HOSTNAME=192.168.178.1
FRITZ_USERNAME=monitoring
FRITZ_PASSWORD=change-me
EOF
chmod 600 fritz.env
docker compose -p stacks up -d fritz-exporter
docker logs stacks-fritz-exporter-1 2>&1 | tail -3
```

The log must end with `Starting listener at 0.0.0.0:9787` and `Exporter is ready`.

**It must say `0.0.0.0`.** Version 3.x listens on `127.0.0.1` by default, which
inside a container means only the container itself can ask it. The compose file
sets `FRITZ_LISTEN_ADDRESS=0.0.0.0` for this reason. The port is still not
published, so it is reachable on the Docker network only.

The `fritzbox` job is already in `prometheus.yml` (once a minute, 30 s timeout:
TR-064 is slow). Reload Prometheus if it was not running yet:

```bash
docker kill -s HUP stacks-prometheus-1
```

---

## 5 · Verify

Prometheus → *Status → Targets*: `fritzbox` **UP**. Then in *Explore*:

```promql
fritz_wan_phys_link_status                   # 1 = internet line up
fritz_dsl_datarate_kbps{type="curr"}         # sync speed, rx = down, tx = up
fritz_dsl_noise_margin_dB                    # line quality, higher is better (6+ dB)
fritz_known_devices_count                    # every device the box has ever seen
sum(fritz_wifi_associations_count)           # on Wi-Fi now
fritz_usp_myfritz_enabled                    # 1 = MyFRITZ remote access is on
fritz_update_available                       # 1 = firmware update waiting
```

Grafana: **Overview → Internet (FRITZ!Box)** and **Security → Home network &
router** are filled.

Alerts that use this (runbook 23): 🔴 *Internet down*, 🟠 *New device joined
the network*, 🟠 *FRITZ!Box update available*.

---

## If it goes wrong

| Symptom | Cause |
|---|---|
| target DOWN, "connection refused" | exporter listening on 127.0.0.1: `FRITZ_LISTEN_ADDRESS=0.0.0.0` missing |
| target DOWN, timeout | scrape took longer than the timeout; keep `scrape_timeout: 30s` |
| exporter log: 606 / not authorized | user right missing or not confirmed (step 2.5) |
| DSL metrics missing | the box is on cable or fibre: those have their own metrics (`fritz_docsis_*`, `fritz_fiber_*`) |
| "internet down" alert while the internet works | the rule uses `or vector(0)` and the exporter died; see docs/24 trap 1 |

---

## Undo

```bash
cd /opt/monitoring && docker compose -p stacks rm -s -f fritz-exporter && rm fritz.env
```

FRITZ!Box: **System → FRITZ!Box-Benutzer**, delete `monitoring`.
