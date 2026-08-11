# Docker Compose

The file format, the commands, and the handful of behaviours that are not
obvious from the documentation.

---

## What it is, and what problem it solves

A `docker run` command for a real service is unreadable:

```bash
docker run -d --name nextcloud-app --restart unless-stopped \
  -p 8082:80 -v nextcloud_html:/var/www/html -v /srv/data:/var/www/html/data \
  -e POSTGRES_HOST=db -e POSTGRES_PASSWORD=... -e REDIS_HOST=redis \
  --network nextcloud nextcloud:29-apache
```

That command lives in your shell history until it does not. Nobody can review
it. Nobody can diff it. Reproducing it on another machine means finding it
again.

**Compose is that command written down as a file.** Same concepts, same flags,
declarative instead of imperative, and version-controllable.

It solves a second problem too: **multi-container services**. Nextcloud is not
one container, it is four (app, database, cache, cron). Starting them in the
right order, on a shared network, with consistent names, by hand, every time, is
not something a person should do.

**What Compose is not:** an orchestrator. It runs containers on *one* machine.
It does not schedule across nodes, reschedule after a node failure, or do
rolling updates. That is what Kubernetes (or k3s, planned for this lab) is for.
Compose is the right tool right up until you need something to survive a machine
dying.

---

## Anatomy of a file

```yaml
services:                          # the containers. the only required key.
  web:                             # service name -> also the DNS hostname
    image: nginx:alpine            # OR build: ./dir
    container_name: web            # optional; blocks scaling if set
    restart: unless-stopped
    ports:
      - "8080:80"                  # host:container
    volumes:
      - ./html:/usr/share/nginx/html:ro
      - web_cache:/var/cache/nginx
    environment:
      - TZ=Europe/Berlin
      - API_KEY=${API_KEY}         # from .env
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
    networks: [frontend]
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s
    security_opt:
      - no-new-privileges:true
    deploy:
      resources:
        limits:
          memory: 512M

networks:
  frontend:
    driver: bridge

volumes:
  web_cache:
```

**No `version:` key.** It has been obsolete since Compose v2 and current
releases warn about it. Files on the internet still have it; ignore that.

### The keys that are not self-explanatory

**`depends_on` does not wait for readiness.** By default it only controls start
*order*, and "started" means the process launched, not that it is accepting
connections. A web app will start, fail to reach a database that is still
initialising, and exit. The fix is a healthcheck plus a condition:

```yaml
depends_on:
  db:
    condition: service_healthy
```

Which requires `db` to actually define a `healthcheck`. This is the single most
common reason a stack works on the second `up` and not the first.

**`restart` policies:**

| Value | Behaviour |
|---|---|
| `no` | never restart (default) |
| `on-failure` | restart on non-zero exit |
| `unless-stopped` | restart always, **except** if you stopped it deliberately |
| `always` | restart always, including one you stopped, when the daemon restarts |

`unless-stopped` is the right default. `always` will restart the container you
stopped on purpose an hour ago, the next time the host reboots.

**`container_name` prevents scaling.** With it set, `docker compose up
--scale web=3` fails, because three containers cannot share one name. Leave it
off unless you need a predictable name for something external.

**Volume short syntax gotcha:** `- ./config.yml:/app/config.yml` where
`./config.yml` does not exist creates a **directory**. Always create the file
first.

---

## Commands

### Daily

```bash
docker compose up -d              # create and start, in the background
docker compose down               # stop and REMOVE containers and networks
docker compose down -v            # ... and DELETE THE VOLUMES
docker compose restart            # restart the processes, same containers
docker compose ps                 # what is in this project
docker compose logs -f            # follow all services
docker compose logs -f web        # follow one
docker compose exec web sh        # shell in a running service
```

### The distinction that matters

**`restart` restarts the process in the existing container.**
**`up -d` recreates the container if the configuration changed.**

Change a line in `docker-compose.yml`, run `docker compose restart`, and nothing
happens: the container is the old one, built from the old configuration. Compose
compares the desired state to what is running and only recreates what differs,
so `up -d` after an edit is both correct and cheap.

### Updating

```bash
docker compose pull               # fetch newer images
docker compose up -d              # recreate anything whose image changed
docker image prune -f             # reclaim the old ones
```

Three commands, and that is the entire update process for every Docker service
in this lab. `docker compose up -d --force-recreate` when you want to recreate
regardless.

### Validating before you break something

```bash
docker compose config             # render with variables substituted
docker compose config --services  # just the names
docker compose config -q          # quiet: exit non-zero on error
```

`docker compose config` is the habit worth building. It expands every `${VAR}`
and fails on a typo, instead of starting a database with an empty password
because `POSTGRES_PASSWORD` was misspelled in `.env`.

### Building

```bash
docker compose build
docker compose build --no-cache web
docker compose up -d --build      # build then start
```

### Everything else

```bash
docker compose stop               # stop, keep containers
docker compose start              # start stopped containers
docker compose top                # processes across all services
docker compose events             # live event stream
docker compose run --rm web sh    # one-off container, not the service
docker compose kill -s SIGHUP web # send a specific signal
docker compose -f a.yml -f b.yml up -d   # merge two files
docker compose -p myproj up -d    # explicit project name
```

`run` versus `exec`: `exec` enters the container that is already running. `run`
starts a **new** container from the same definition. `run` is for one-off tasks
(`docker compose run --rm app php occ maintenance:repair`), `exec` is for
looking at what is live.

---

## Variables and `.env`

Compose reads a file called `.env` in the same directory and substitutes
`${VAR}` in the compose file.

```
compose/nextcloud/
  docker-compose.yml     ${POSTGRES_PASSWORD}
  .env                   POSTGRES_PASSWORD=<the real value>  <- gitignored
  .env.example           POSTGRES_PASSWORD=                  <- committed
```

Two different mechanisms that look the same and are not:

| | Where it applies |
|---|---|
| **`.env` in the project directory** | substituted into the **compose file itself**, at parse time |
| **`env_file:` inside a service** | passed as environment **into the container**, at runtime |

A variable you only need inside the container does not need to be in the compose
file at all. A variable you use for an image tag or a port must be in `.env`.

Useful defaults:

```yaml
image: postgres:${PG_VERSION:-16}      # default if unset
data: ${DATA_DIR:?DATA_DIR must be set} # fail loudly if unset
```

The `:?` form is worth using for anything whose absence would silently produce a
broken container.

**A literal `$` in a compose file must be written `$$`**, or Compose tries to
substitute it. This bites in `command:` lines containing shell variables and in
Prometheus regexes.

---

## Healthchecks

A healthcheck is a command run inside the container on an interval. If it fails
enough times the container is marked `unhealthy`.

```yaml
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U postgres || exit 1"]
  interval: 10s        # how often
  timeout: 5s          # how long to wait for the command
  retries: 5           # failures before "unhealthy"
  start_period: 30s    # grace period at startup; failures here do not count
```

Two things people miss:

**`start_period` exists for slow starters.** Without it, a database that takes
40 seconds to initialise is marked unhealthy before it ever had a chance, and
everything with `condition: service_healthy` refuses to start.

**Unhealthy does not mean restarted.** Docker marks the container unhealthy and
does nothing else. Nothing acts on it unless you add something that does. In
this lab, Glance and Prometheus are what notice.

Check status with:

```bash
docker inspect -f '{{.State.Health.Status}}' nextcloud-db
docker ps    # the STATUS column shows (healthy) / (unhealthy)
```

---

## Resource limits

Without limits, one container can consume the whole host. In an LXC container
that means the LXC's memory limit, and the OOM killer picks a victim that is
usually not the guilty container.

```yaml
deploy:
  resources:
    limits:
      cpus: "1.5"
      memory: 512M
    reservations:
      memory: 256M
```

`deploy:` was originally a Swarm key, which is why it looks out of place. Modern
`docker compose` honours `limits` outside Swarm. `mem_limit: 512m` also works
and is the older syntax.

---

## Multiple files, and overrides

Compose automatically merges `docker-compose.yml` with
`docker-compose.override.yml` if the latter exists. That is a clean way to keep
machine-specific bits out of the shared file:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

Merge rules that surprise people: **scalars are replaced, lists are
concatenated.** Two files each defining `ports:` gives you both sets of ports,
not the second one. To replace a list you have to override the whole service in
a way Compose treats as a reset, which usually means restructuring rather than
fighting it.

---

## Things that will bite you

**`down -v` deletes volumes.** One character between "restart the stack" and
"delete the database". Muscle memory is dangerous here.

**`depends_on` without `condition: service_healthy` waits for nothing useful.**

**Editing the file and running `restart`** changes nothing. Use `up -d`.

**The project name comes from the directory name.** Two stacks in two
directories both called `docker` will collide on network and volume names. Set
`-p` or `name:` explicitly if that is a risk.

**Renaming the directory orphans your volumes.** Named volumes are prefixed with
the project name, so `docker` becomes `docker_appdata` and renaming the folder
to `services` makes Compose look for `services_appdata`, find nothing, and
create it empty. Your data is still there, under the old name. `docker volume
ls` and either rename the project back or migrate deliberately.

**YAML indentation is two spaces and tabs are a syntax error.** The error
message points at the wrong line often enough to waste ten minutes.

**Quoting ports.** `- 8080:80` unquoted is fine, but `- 22:22` is parsed as a
sexagesimal number by some YAML parsers and becomes `1342`. Quote your ports:
`- "22:22"`.

**`docker compose` versus `docker-compose`.** The hyphenated one is the old
standalone Python binary, now end-of-life. Behaviour differs in small ways
(project naming, `.env` handling). If a command from a tutorial behaves oddly,
check which one is installed.

---

## The conventions used in this lab

Every file in [`compose/`](../compose/) follows the same rules, and the reasoning
is written into the files themselves as comments:

- `restart: unless-stopped`, never `always`
- `security_opt: no-new-privileges:true` wherever the image tolerates it
- named volumes for state, bind mounts for configuration
- no `version:` key
- pinned major versions on anything that stores data
- every real value in `.env`, every file shipped as `.example`

---

**Next:** [Networking, DNS and TLS](05-networking-dns-tls.md) — how a request
actually reaches a service in this lab.
