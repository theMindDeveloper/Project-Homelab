# Runbook 22 · The real visitor IP behind a Cloudflare tunnel

**Goal** Apache logs the real address of each website visitor instead of the
tunnel's, so visitors appear on the world map and CrowdSec can recognise web
attacks.

**Time** 15 minutes.
**Prerequisites** The website published through a Cloudflare tunnel
([runbook 06](06-cloudflare-tunnel.md)), Apache from
[`compose/apache/`](../compose/apache/), logs collected ([runbook 21](21-logs-and-crowdsec.md)).
**Reverses cleanly?** Yes: remove one volume line and restart Apache.

Concepts: [docs/23](../docs/23-logs-and-security-monitoring.md#3--the-website-with-the-real-visitor-address).

---

## 0 · The problem, in one picture

```
visitor 203.0.113.10 ──> Cloudflare ──tunnel──> cloudflared (172.19.0.4) ──> Apache
                         adds header                                         sees: 172.19.0.4
                         CF-Connecting-IP: 203.0.113.10
```

Apache logs who connected **to it**, and that is always cloudflared. Every visitor
in the log has the same private address, CrowdSec ignores private addresses, and
the world map has no website dots.

Cloudflare does send the real address along, in the `CF-Connecting-IP` header.
Apache's **`mod_remoteip`** can use it, with one rule that matters for security:
**only believe that header when the request comes from cloudflared.** Otherwise
anyone on the LAN could send `CF-Connecting-IP: 198.51.100.10` and appear as someone
else.

---

## 1 · Get Apache's default configuration

The official `httpd` image ships a full `httpd.conf`. Copy it out once:

```bash
cd /path/to/apache          # the folder with Apache's docker-compose.yml
docker run --rm httpd:2.4-alpine cat /usr/local/apache2/conf/httpd.conf > httpd.conf
```

---

## 2 · Three changes to `httpd.conf`

All three are in [`compose/apache/httpd-remoteip.conf`](../compose/apache/httpd-remoteip.conf).

**a)** Find the commented line and remove the `#`:

```apache
LoadModule remoteip_module modules/mod_remoteip.so
```

**b)** In the `LogFormat` lines, change `%h` to `%a` in the `combined` format, and
log `combined` instead of `common`:

```apache
LogFormat "%a %l %u %t \"%r\" %>s %b \"%{Referer}i\" \"%{User-Agent}i\"" combined
CustomLog /proc/self/fd/1 combined
```

`%h` is "who connected" (cloudflared). `%a` is "the client address after
`mod_remoteip`" (the visitor). `combined` adds referer and user agent, which
CrowdSec's Apache parser expects and the dashboards use (bots, attack probes).

**c)** At the very end of the file:

```apache
<IfModule remoteip_module>
    RemoteIPHeader CF-Connecting-IP
    RemoteIPInternalProxy 172.16.0.0/12
</IfModule>
```

`172.16.0.0/12` covers Docker's networks, where cloudflared lives. A request from
the LAN (`192.168.178.x`) is not from a trusted proxy, so its header is ignored.

---

## 3 · Test the syntax before restarting

A broken `httpd.conf` takes the website down. Test the new directives against the
running Apache, without changing it:

```bash
docker exec apache httpd -t \
  -C 'LoadModule remoteip_module modules/mod_remoteip.so' \
  -c 'RemoteIPHeader CF-Connecting-IP' \
  -c 'RemoteIPInternalProxy 172.16.0.0/12'
```

`Syntax OK` (plus a harmless "could not determine the server's fully qualified
domain name") is what you want. Also check the module is in the image:
`docker exec apache ls /usr/local/apache2/modules/mod_remoteip.so`.

---

## 4 · Mount the file and restart Apache

In Apache's compose file, mount the edited config read-only:

```yaml
    volumes:
      - ./httpd.conf:/usr/local/apache2/conf/httpd.conf:ro
```

```bash
docker compose up -d apache       # recreates only Apache; the site is gone for ~2 s
docker logs --tail 5 apache       # no errors
```

---

## 5 · Verify from outside

Open the website **from outside your network** (a phone on mobile data, Wi-Fi
off), then:

```bash
docker logs --tail 3 apache
```

The first field must now be your phone's public address, not `172.x`. In Grafana
(*Explore* → Loki):

```logql
{job="apache"} | country != ""
```

shows the visit with a country and city, and the Security dashboard's map gets
an orange dot.

---

## If it goes wrong

| Symptom | Cause |
|---|---|
| website down after restart | syntax error; `docker logs apache`, go back to the old config |
| still `172.x` in the log | `%h` still in the `combined` LogFormat, or `common` still used in `CustomLog` |
| still `172.x`, format right | the tunnel does not point at Apache through Docker (e.g. via the LAN IP): then the proxy is not in `172.16.0.0/12`; trust its real address instead, nothing broader |
| visits from inside the LAN show a LAN IP | correct: they don't go through Cloudflare |

---

## Undo

Remove the `httpd.conf` volume line from the compose file and
`docker compose up -d apache`. The image's default config is back.
