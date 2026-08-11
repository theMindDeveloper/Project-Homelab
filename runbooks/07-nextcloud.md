# Runbook 07 · Nextcloud

> **Status: written, not yet deployed.** This is the deployment plan for P2,
> reviewed and ready to execute. It has not been run in this lab. Where a step
> is an expectation rather than an observation, it says so.

**Goal** Nextcloud on P2, with PostgreSQL, Redis and a working background job
runner, behind Nginx Proxy Manager with a real certificate, correctly configured
for a reverse proxy from the first boot.

**Time** 60 minutes, including the post-install configuration that most guides
skip and that determines whether the instance is usable at 500 GB.
**Prerequisites** A free container ID and IP on P2. Docker. NPM running with a
wildcard certificate.
**Reverses cleanly?** Yes — `pct destroy` removes all of it.

---

## Why four containers

Nextcloud is not one container, and understanding why each exists prevents most
of the problems people have with it.

| Container | Why it is there | What happens without it |
|---|---|---|
| **app** | Nextcloud itself, PHP under Apache | — |
| **db** | PostgreSQL | the default is SQLite, which locks under any concurrency and falls over at scale |
| **redis** | file locking and session cache | database-backed locking, and "file is locked" errors needing manual clearing |
| **cron** | runs background jobs every 5 minutes | AJAX cron only fires when someone loads a page, so on a lightly used instance previews, cleanups and file scans never run |

**PostgreSQL over MariaDB:** both are supported. PostgreSQL is chosen because
the Nextcloud project tests it hardest, `pg_dump` produces a clean restorable
file, and it avoids the `utf8mb4` / row-format migration that MariaDB instances
tend to hit years later.

**Redis is not optional in practice.** It is documented as optional and every
instance without it eventually produces file-locking errors that need manual
database intervention.

---

## 1 · Create the container

```bash
# on P2 (pve2)
pct create 210 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
  --hostname     nextcloud \
  --cores        4 \
  --memory       4096 \
  --swap         1024 \
  --rootfs       local-lvm:20 \
  --net0         name=eth0,bridge=vmbr0,ip=192.168.178.60/24,gw=192.168.178.1 \
  --nameserver   192.168.178.178 \
  --onboot       1 \
  --unprivileged 1 \
  --features     nesting=1,keyctl=1

pct start 210
```

**Separate the data from the root filesystem.** The 20 GB root holds the OS and
the application. User files go on their own mount point, on the big disk, so the
data can grow without threatening the container and can be backed up on a
different schedule.

```bash
pct set 210 --mp0 /mnt/hdd-1tb/nextcloud,mp=/srv/nextcloud,size=500G
```

Then install Docker inside:
[`scripts/install-docker.sh`](../scripts/install-docker.sh), or
[Runbook 02, step 3](02-portainer-on-a-new-lxc.md).

---

## 2 · Configure

```bash
pct enter 210
mkdir -p /opt/nextcloud && cd /opt/nextcloud
```

Copy in
[`compose/nextcloud/docker-compose.example.yml`](../compose/nextcloud/docker-compose.example.yml)
and its `.env.example`.

```bash
cp docker-compose.example.yml docker-compose.yml
cp .env.example .env

# generate every password, do not invent them
for v in POSTGRES_PASSWORD REDIS_PASSWORD NEXTCLOUD_ADMIN_PASSWORD; do
  echo "$v=$(openssl rand -base64 32)"
done

$EDITOR .env
chmod 600 .env
```

Store all three in Vaultwarden before continuing.

### The four settings that decide whether it works behind a proxy

This is the part that produces almost every first-boot problem.

```env
NEXTCLOUD_TRUSTED_DOMAINS=cloud.theminddev.com
NEXTCLOUD_URL=https://cloud.theminddev.com
TRUSTED_PROXIES=192.168.178.178
```

**`NEXTCLOUD_TRUSTED_DOMAINS`** — Nextcloud rejects any request whose `Host`
header is not in this list, with "You are accessing the server from an untrusted
domain". Comma separated, **no scheme, no trailing slash**.

**`OVERWRITEPROTOCOL=https`** — the app sees a plain HTTP request from the proxy
and would otherwise build every URL with `http://`, producing a redirect loop at
login and share links that do not work.

**`OVERWRITECLIURL`** — the base URL used by the command-line tool and by
background jobs for generating links.

**`TRUSTED_PROXIES`** — the address of the reverse proxy. Nextcloud only
believes `X-Forwarded-For` from a host in this list. Without it, every log entry
and rate limit sees the proxy's address instead of the client's; with it set to
something too broad, a client can spoof its own address. It should be exactly
the proxy.

---

## 3 · Start

```bash
docker compose config          # validate before starting
docker compose up -d
docker compose logs -f app
```

First start takes a few minutes: the app initialises the database schema and
installs the default apps. Wait for `Initializing finished`.

```bash
docker compose ps              # db and redis should show (healthy)
```

The compose file uses `depends_on: condition: service_healthy`, so the app waits
for PostgreSQL to actually accept connections rather than merely having started.
Without that, the app starts against a database still initialising, fails, and
exits — which is why so many stacks "work on the second `up`".

---

## 4 · Reverse proxy

Per [Runbook 04](04-nginx-proxy-manager-vhost.md):

| Field | Value |
|---|---|
| Domain Names | `cloud.theminddev.com` |
| Scheme | `http` |
| Forward Hostname / IP | `192.168.178.60` |
| Forward Port | `8082` |
| Websockets Support | on |
| SSL | wildcard, Force SSL, HTTP/2, HSTS |

**Advanced** — these are required, not optional:

```nginx
client_max_body_size 0;          # no upload limit. without it, large files 413
proxy_request_buffering off;     # stream uploads instead of buffering to disk
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;

# service discovery: clients look for these paths, Nextcloud serves them elsewhere
location = /.well-known/carddav { return 301 $scheme://$host/remote.php/dav; }
location = /.well-known/caldav  { return 301 $scheme://$host/remote.php/dav; }
```

The `.well-known` redirects are what the built-in security scan complains about,
and they are what makes CalDAV and CardDAV clients auto-configure.

---

## 5 · Post-install, the part guides skip

An instance that works and an instance that is *usable* differ here.

```bash
cd /opt/nextcloud
alias occ='docker compose exec -u www-data app php occ'
```

### Database indices and column types

```bash
occ db:add-missing-indices
occ db:add-missing-columns
occ db:add-missing-primary-keys
occ db:convert-filecache-bigint
```

**Do not skip these.** They are the difference between a file list that loads
instantly and one that takes ten seconds at 100,000 files. `bigint` conversion
in particular has to happen before the instance grows, and it needs the
instance in maintenance mode:

```bash
occ maintenance:mode --on
occ db:convert-filecache-bigint
occ maintenance:mode --off
```

### Caching

```bash
occ config:system:set memcache.local --value='\OC\Memcache\APCu'
occ config:system:set memcache.locking --value='\OC\Memcache\Redis'
occ config:system:set memcache.distributed --value='\OC\Memcache\Redis'
```

Two different caches: **APCu** is local, per-PHP-process, and fast. **Redis**
handles distributed locking, which is what actually prevents the file-locking
errors.

### Region and defaults

```bash
occ config:system:set default_phone_region --value="DE"
occ config:system:set maintenance_window_start --type=integer --value=1
```

`maintenance_window_start` tells Nextcloud when it may run heavy background
jobs. Setting it silences a warning and stops the instance doing database work
at the moment you want to use it.

### Verify the background jobs are actually running

```bash
occ background:cron
occ status
docker compose logs cron | tail
```

In the web UI, **Administration → Basic settings** should show *Last background
job execution* within the last five minutes and the method as **Cron**. If it
says AJAX, the cron container is not working and half of Nextcloud's
housekeeping is silently not happening.

### Run the built-in checks

```bash
occ setupchecks
```

Fix everything it reports. Every warning it raises is something that will
eventually cost you an evening.

---

## 6 · Verify

```bash
curl -I http://192.168.178.60:8082
curl -I https://cloud.theminddev.com
occ status
occ user:list
```

Then, in a browser:

1. Log in as admin.
2. **Administration → Overview** — expect no warnings.
3. Upload a large file, over 1 GB. This is what exercises
   `client_max_body_size`, `proxy_request_buffering` and the timeouts all at
   once, and it is the check that fails when the proxy is misconfigured.
4. Connect a desktop client and sync a folder both ways.
5. Add the CalDAV URL to a phone; it should auto-configure via `.well-known`.

---

## 7 · Backup

Nextcloud has **three** things to back up and missing any one makes the other
two useless.

```bash
# 1. the database
docker compose exec -T db pg_dump -U nextcloud nextcloud \
  | zstd > /srv/backup/nextcloud-db-$(date +%F).sql.zst

# 2. the config and apps
docker run --rm -v nextcloud_nextcloud_html:/data:ro -v /srv/backup:/b \
  alpine tar czf /b/nextcloud-html-$(date +%F).tar.gz -C /data .

# 3. user data - it is a bind mount, so copy it
rsync -a --delete /srv/nextcloud/ /mnt/backup/nextcloud-data/
```

Put the instance in maintenance mode first, so the database dump and the files
are consistent with each other:

```bash
occ maintenance:mode --on
# ... take all three backups ...
occ maintenance:mode --off
```

The `vzdump` of LXC 210 captures all of it too, crash-consistently. The dumps
above are for the case where you want to restore Nextcloud without restoring the
whole container. See
[`docs/07-backup-and-recovery.md`](../docs/07-backup-and-recovery.md).

---

## 8 · Updating

```bash
occ maintenance:mode --on
docker compose pull
docker compose up -d
occ upgrade
occ maintenance:mode --off
occ status
```

**Never skip a major version.** Nextcloud only supports upgrading one major at a
time: 28 → 29 → 30, never 28 → 30. Skipping produces a broken instance and the
recovery is a restore.

Snapshot the container first:

```bash
# on the Proxmox host
pct snapshot 210 pre-nextcloud-upgrade
```

---

## If it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| "Access through untrusted domain" | `Host` header not in trusted domains | `occ config:system:set trusted_domains 1 --value=cloud.theminddev.com` |
| infinite redirect at login | app sees `http` | `OVERWRITEPROTOCOL=https` |
| **413** on upload | proxy body size limit | `client_max_body_size 0;` in NPM Advanced |
| **504** on a large upload | proxy timeout | `proxy_read_timeout 3600s;` |
| "file is locked" | Redis not being used for locking | `memcache.locking`, then `occ maintenance:repair` |
| last cron is hours ago | the cron container is not running | `docker compose ps cron`, then its logs |
| every log line shows the proxy IP | `TRUSTED_PROXIES` wrong | set it to the proxy's address |
| app exits on first start | database not ready | check `db` is `(healthy)`; `depends_on` needs the healthcheck |
| the UI is very slow at scale | missing indices | `occ db:add-missing-indices` |

To clear a stuck lock properly:

```bash
occ maintenance:mode --on
occ maintenance:repair
occ maintenance:mode --off
```

---

## Undo

```bash
cd /opt/nextcloud && docker compose down -v      # -v DELETES the database
pct stop 210 && pct destroy 210
```

---

## Why this runbook exists before the service does

Because the deployment decisions are the interesting part, and they are made
before anything is installed: PostgreSQL over MariaDB and why, Redis for locking
rather than as an optional cache, a separate cron container because AJAX cron
silently does not run, `TRUSTED_PROXIES` scoped to exactly the proxy, indices
added before the instance grows.

Writing it down first also means the deployment is a review, not a discovery.
When it is actually running on P2, this page gets its status header removed and
the expectations become observations.
