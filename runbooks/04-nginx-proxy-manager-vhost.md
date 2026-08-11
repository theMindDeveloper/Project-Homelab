# Runbook 04 · Put a service behind Nginx Proxy Manager

**Goal** Turn `http://192.168.178.87:3000` into
`https://grafana.theminddev.com`, with a real certificate.

**Time** 3 minutes per service, after the first.
**Prerequisites** NPM running, a wildcard certificate issued, the service
answering on its own port.
**Reverses cleanly?** Yes — delete the proxy host.

This is the most repeated procedure in the lab.

---

## 1 · DNS: usually nothing to do

The wildcard `A` record `*.theminddev.com → 192.168.178.178` covers every
subdomain that will ever exist. A new service needs **no DNS change**.

```bash
dig +short grafana.theminddev.com        # expect 192.168.178.178
```

---

## 2 · The wildcard certificate, if it does not exist yet

Once, in NPM: **SSL Certificates → Add SSL Certificate → Let's Encrypt**

| Field | Value |
|---|---|
| Domain Names | `theminddev.com` **and** `*.theminddev.com` |
| Use a DNS Challenge | **on** |
| DNS Provider | Cloudflare |
| Credentials | `dns_cloudflare_api_token = <token>` |

**Both names.** A wildcard does not cover the apex; `*.example.com` matches
`a.example.com` and not `example.com`, and it does not match `a.b.example.com`
either.

**The DNS challenge is the whole point.** HTTP-01 would need port 80 reachable
from the internet. DNS-01 creates a TXT record instead, so nothing inbound is
needed for issuance or for renewal, ever.

The Cloudflare token needs exactly `Zone → DNS → Edit` on this zone and nothing
else. It is a credential; it lives in NPM's data directory and never in git.

---

## 3 · Add the proxy host

**Hosts → Proxy Hosts → Add Proxy Host**

**Details**

| Field | Value | Note |
|---|---|---|
| Domain Names | `grafana.theminddev.com` | |
| Scheme | `http` | `https` **only** if the backend itself speaks TLS |
| Forward Hostname / IP | `192.168.178.87` | the internal address, never a public name |
| Forward Port | `3000` | the port the service actually listens on |
| Block Common Exploits | on | |
| Websockets Support | **on** for anything with a live UI | |

**SSL**

| Field | Value |
|---|---|
| SSL Certificate | the `*.theminddev.com` wildcard |
| Force SSL | on |
| HTTP/2 Support | on |
| HSTS Enabled | on |

**HSTS is sticky.** It tells the browser "never use http for this name again",
and browsers honour it for the max-age. Turning it on for a host you later want
to serve over plain http means clearing the setting in each browser. Fine for a
permanent service, annoying for an experiment.

---

## 4 · Headers, when the backend misbehaves

NPM sets the common ones. When an application still gets it wrong, the fix goes
in **Advanced**:

```nginx
proxy_set_header Host              $host;
proxy_set_header X-Real-IP         $remote_addr;
proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Upgrade           $http_upgrade;
proxy_set_header Connection        "upgrade";

client_max_body_size 0;      # no upload size limit - needed by Nextcloud
proxy_read_timeout 3600s;    # long-running requests
```

| Symptom | Missing header |
|---|---|
| infinite redirect loop | `X-Forwarded-Proto` |
| every log line shows the proxy's IP | `X-Forwarded-For` |
| login redirects to the wrong hostname | `Host` |
| WebSockets disconnect immediately | `Upgrade` / `Connection` |
| "413 Request Entity Too Large" on upload | `client_max_body_size` |

---

## 5 · Verify

![The proxy host list, sixteen entries, all online](../assets/screenshots/npm-proxy-hosts.png)

*The result after repeating this procedure sixteen times. Every SSL column reads
Let's Encrypt and every one of those certificates came from the single wildcard
in step 2 — there is no per-service certificate request and no inbound port was
opened for any of them.*

```bash
curl -I http://192.168.178.87:3000            # backend answers directly
dig +short grafana.theminddev.com             # name resolves
curl -I https://grafana.theminddev.com        # answers through the proxy
openssl s_client -connect grafana.theminddev.com:443 \
  -servername grafana.theminddev.com </dev/null 2>/dev/null \
  | openssl x509 -noout -dates -subject
```

---

## 6 · Record it

Add it to [`inventory/inventory.yml`](../inventory/inventory.yml), to Glance as
a monitor tile, and to
[`scripts/health-check.sh`](../scripts/health-check.sh).

---

## If it goes wrong

| Symptom | Cause |
|---|---|
| **502 Bad Gateway** | wrong scheme (http vs https), wrong port, or the backend is down |
| **504 Gateway Timeout** | the backend is reachable but not answering — check it directly |
| **certificate warning** | wrong certificate selected, or the name is not covered by the wildcard |
| **redirect loop** | `X-Forwarded-Proto` — see step 4 |
| **works by IP, not by name** | DNS, or a browser using DNS-over-HTTPS |
| **certificate will not issue** | Cloudflare token expired or under-scoped; NPM's log says which |

502 is by far the most common, and the cause is almost always the **scheme**:
Portainer and Proxmox need `https`, most things need `http`.
