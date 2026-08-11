# Runbook 05 · Glance dashboard

**Goal** One page that answers "is anything broken?" in one second.

**Time** 15 minutes, then a minute per service added.
**Prerequisites** Docker on LXC 102.

![Glance](../assets/screenshots/glance-dashboard.png)

---

## Why this exists next to Grafana

They look like duplicates and they are not.

**Glance is checked. Grafana is consulted.**

Glance answers "is anything red" from a phone, in one second, which means it
gets opened daily. Grafana answers "why was the disk slow last Tuesday", which
is a question you ask five times a year. A dashboard nobody opens has monitored
nothing, so both earn their place.

---

## 1 · Start it

```bash
mkdir -p /opt/glance && cd /opt/glance
cp /path/to/compose/glance/docker-compose.example.yml docker-compose.yml
cp /path/to/compose/glance/glance.example.yml glance.yml
$EDITOR glance.yml                # replace example.com with the real domain
docker compose up -d
```

Full config, published verbatim because it contains no credentials at all:
[`compose/glance/glance.example.yml`](../compose/glance/glance.example.yml)

---

## 2 · Add a service

```yaml
- type: monitor
  title: Management
  cache: 1m
  sites:
    - title: Grafana
      url: https://grafana.theminddev.com
      icon: si:grafana
```

```bash
docker compose restart glance     # config is a read-only bind mount
```

### Split `url` from `check-url`

The single most useful thing in this config:

```yaml
- title: Grafana
  url: https://grafana.theminddev.com          # where clicking the tile goes
  check-url: http://192.168.178.87:3000/api/health   # what is actually probed
```

`url` is the friendly name, through DNS and through the reverse proxy.
`check-url` hits the service **directly, by address and port**.

Without the split, a red tile means "the service is down **or** DNS is broken
**or** the proxy is down **or** the certificate expired". A health check that
can fail for four unrelated reasons has told you nothing. With the split, red
means the service.

Use a real health endpoint where the service has one — `/api/health`,
`/-/ready`, `/alive` — rather than the login page. Those return 200 only if the
service can also reach its own database.

### The two settings behind every Glance support question

**`allow-insecure: true`** for anything with a self-signed certificate —
Proxmox on `:8006` and Portainer on `:9443`.

**A 401 is healthy.** Nginx Proxy Manager's admin UI returns 401 when you are
not logged in. Without accounting for that, the tile is permanently red, and a
dashboard with a permanently red tile trains you to ignore red tiles. That
defeats the entire purpose.

### What a monitor tile actually proves

It issues an HTTP request and colours the tile by the response. That is a
**liveness** check, not a correctness check: a service can return 200 while
being completely broken inside.

It catches the failure that actually happens in a homelab, which is a container
that stopped and nobody noticed for two weeks. That is a low bar and it is worth
far more than it sounds.

---

## 3 · Bookmarks: the addresses you need when DNS is down

```yaml
- type: bookmarks
  groups:
    - title: Hardware
      links:
        - title: P1
          url: https://192.168.178.20:8006
```

Raw IPs on purpose. **The moment DNS breaks is the moment you need the IP**, and
that is exactly the moment a dashboard of friendly names becomes useless.

Which means the page should also be reachable by IP:
`http://192.168.178.87:8080`. Bookmark that, not the pretty name.

---

## 4 · How to extract your live config

For publishing it, or backing it up. Glance runs as a Docker container inside
LXC 102, so the file is two layers down.

```bash
# from the Proxmox host
pct enter 102

# find the container and where its config comes from
docker ps | grep glance
docker inspect glance --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
```

That prints the host-side path of the bind mount, typically
`/opt/glance/glance.yml`. Then:

```bash
cat /opt/glance/glance.yml
```

Or copy it straight out of the container, without needing to know the path:

```bash
docker cp glance:/app/config/glance.yml /tmp/glance.yml
cat /tmp/glance.yml
```

To get it all the way to your workstation:

```bash
# on the Proxmox host, pull the file out of the container
pct pull 102 /opt/glance/glance.yml /tmp/glance.yml

# then, from the workstation
scp root@192.168.178.20:/tmp/glance.yml .
```

**Before publishing it**, run it past the secret scanner:

```bash
./scripts/check-secrets.sh --all
```

Glance configs sometimes contain API keys for weather or calendar widgets. Those
are credentials.

---

## Other widgets worth having

```yaml
- type: dns-stats
  service: adguard
  url: http://192.168.178.178:8000
  username: ${ADGUARD_USER}
  password: ${ADGUARD_PASSWORD}

- type: docker-containers
  hide-by-default: false

- type: server-stats
  servers:
    - type: local
      name: LXC 102
```

`dns-stats` needs credentials, which means a `.env` file, which means the config
is no longer publishable as-is. That is the reason
[`glance.example.yml`](../compose/glance/glance.example.yml) does not include it.
