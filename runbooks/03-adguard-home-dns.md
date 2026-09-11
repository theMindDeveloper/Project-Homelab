# Runbook 03 · AdGuard Home as the LAN resolver

**Goal** One DNS server that every device on the network uses, filtering ads and
trackers, with no configuration on any client.

**Time** 20 minutes.
**Prerequisites** Docker on the Raspberry Pi. Admin access to the FRITZ!Box.
**Reverses cleanly?** Yes, but read the warning first.

---

## Read this before starting

**When this container is down, nothing on the network can resolve a name.** Not
the internet, not the internal services, nothing. Every phone, laptop and TV
depends on it the moment step 4 is done.

Do this at a time when a ten-minute outage is acceptable, and know the manual
escape route: set a client's DNS to `1.1.1.1` by hand. Internal names stop
working, the internet comes back.

This single point of failure is written into the README's known limitations. It
is the price of network-wide filtering with zero client configuration.

---

## 1 · Free port 53

`systemd-resolved` listens on 53 by default and will refuse to give it up
silently, producing "address already in use" from Docker.

```bash
ss -tulnp | grep :53

sudo mkdir -p /etc/systemd/resolved.conf.d
printf '[Resolve]\nDNSStubListener=no\n' \
  | sudo tee /etc/systemd/resolved.conf.d/adguard.conf
sudo systemctl restart systemd-resolved

ss -tulnp | grep :53          # expect nothing
```

Disabling the stub listener does not break the Pi's own resolution;
`/etc/resolv.conf` still points at `127.0.0.53` and resolved still answers there.

---

## 2 · Start the container

Compose file:
[`compose/adguard/docker-compose.example.yml`](../compose/adguard/docker-compose.example.yml)

```bash
mkdir -p /opt/adguard && cd /opt/adguard
cp /path/to/docker-compose.example.yml docker-compose.yml
docker compose up -d
docker compose logs -f
```

---

## 3 · Run the setup wizard

```
http://192.168.178.178:3001
```

The wizard runs on 3000 inside the container (published as 3001 here) and
**moves to the port you choose** once setup is done. Pick 80 inside the
container, published as 8000, so the admin UI ends up at
`http://192.168.178.178:8000`.

| Setting | Value |
|---|---|
| Admin web interface | port 80 (published as 8000) |
| DNS server | port 53 |
| Username | not `admin` |
| Password | generated, stored in Vaultwarden |

### Upstream resolvers

Settings → DNS settings. Updated September 2026, see
[the privacy update](../docs/reports/2026-09-11-privacy-update.md):

```
https://dns.quad9.net/dns-query
tls://dns.quad9.net
[/fritz.box/]192.168.178.1
```

| Line / field | Value | Why |
|---|---|---|
| line 1 | Quad9 over **DoH** (port 443) | encrypted upstream |
| line 2 | Quad9 over **DoT** (port 853) | encrypted backup, AdGuard uses the faster one |
| line 3 | `[/fritz.box/]192.168.178.1` | conditional upstream: router names go to the router, not to Quad9 |
| Bootstrap DNS | `9.9.9.9`, `149.112.112.112` | plain lookup of `dns.quad9.net` itself, only used for that |
| Private reverse DNS | `192.168.178.1` | device names in the query log |
| DNSSEC | on | rejects forged answers |

Click **Test upstreams**, then **Apply**.

The upstream leg is encrypted, so the ISP sees that AdGuard talks to Quad9 but
not which names. Queries from devices *to* AdGuard stay plain UDP on the LAN,
which is fine because they never leave the house. Blocking is unaffected:
AdGuard checks its blocklists before anything goes upstream.

Not Mullvad's public DNS: it shuts down on 2 November 2026. Background in
[`docs/21-encrypted-dns.md`](../docs/21-encrypted-dns.md).

### Blocklists

AdGuard DNS filter and the AdAway list are enough. Adding six aggressive lists
produces false positives, and false positives on a network-wide resolver mean
somebody's banking app stops working and nobody connects it to the DNS server.

---

## 4 · Point the whole network at it

FRITZ!Box → **Home Network → Network → Network Settings → IPv4 Configuration**

| Field | Value |
|---|---|
| Local DNSv4 server | `192.168.178.178` |

Clients pick it up as their DHCP lease renews. Force it on one device to test:

```bash
# Linux
sudo dhclient -r && sudo dhclient
resolvectl status | grep "DNS Servers"
```

**Do not** set the DNS server in the FRITZ!Box's *internet* settings instead.
That changes what the router itself uses upstream, not what it hands to clients,
and the difference is easy to miss.

---

## 5 · Verify

![AdGuard Home dashboard after a day of real traffic](../assets/screenshots/adguard-dashboard.png)

*What "working" looks like after 24 hours: 123,095 queries, 38,598 blocked,
15 ms average, and a top-clients list containing every device on the network.
If the client list has one entry, the router is still resolving on behalf of
everyone and step 4 did not take effect.*

```bash
dig @192.168.178.178 example.com                 # resolves
dig @192.168.178.178 doubleclick.net             # expect 0.0.0.0 or NXDOMAIN
dig @192.168.178.178 grafana.theminddev.com      # expect 192.168.178.178
```

Then open the query log in the UI. Every device on the network should be
appearing within a few minutes.

### Is the upstream really encrypted?

The dashboard's **Top upstreams** card (or the Upstream field of a query log
entry) shows which line answered. The real proof is on the Pi:

```bash
sudo apt install -y tcpdump

# plain DNS leaving the house: should stay (almost) empty while browsing
sudo tcpdump -ni any 'port 53 and not net 192.168.178.0/24'

# encrypted DNS to Quad9: should show packets on .443 (DoH) and/or .853 (DoT)
sudo tcpdump -ni any 'host 9.9.9.9 or host 149.112.112.112'
```

From a client, an extended test on dnsleaktest.com should list only Quad9
resolvers. That proves *who* answers, not that it is encrypted.

---

## If it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| "address already in use" on 53 | `systemd-resolved` | step 1 |
| clients still use the old DNS | DHCP lease not renewed | renew, or reboot the client |
| one device ignores it | DNS-over-HTTPS in the browser, or the FRITZ!Box handing out itself as IPv6 DNS | disable it in browser settings, check the DNSv6 setting on the router |
| "could not be used" in Test upstreams | clock, bootstrap, blocked port, or typo | [troubleshooting](../docs/10-troubleshooting.md#adguard-says-an-upstream-could-not-be-used) |
| `*.fritz.box` names stop resolving | conditional upstream line missing | add `[/fritz.box/]192.168.178.1` |
| a site is broken | over-aggressive blocklist | find it in the query log, add an exception |
| nothing resolves anywhere | this container | `docker compose ps`, and set a client to 1.1.1.1 meanwhile |

---

## Undo

```bash
docker compose down
sudo rm /etc/systemd/resolved.conf.d/adguard.conf
sudo systemctl restart systemd-resolved
```

Set the FRITZ!Box's local DNS server back to blank, so it hands out its own
address again.
