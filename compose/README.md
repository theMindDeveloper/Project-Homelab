# Compose files

One directory per service. Every file here is an **example**: it has the real
structure, the real comments and the real reasoning, with values replaced by
variables. The live file with values is never committed.

```
compose/<service>/
  docker-compose.example.yml   tracked
  .env.example                 tracked
  docker-compose.yml           gitignored  <- what actually runs
  .env                         gitignored  <- the values
```

## Using one

```bash
cd compose/vaultwarden
cp docker-compose.example.yml docker-compose.yml
cp .env.example .env
$EDITOR .env                 # fill in every empty value
docker compose config        # renders the file with variables substituted
docker compose up -d
docker compose logs -f
```

`docker compose config` before `up` is the habit worth building. It expands
every variable and fails loudly on a typo, instead of silently starting a
container with an empty password because `${FOO}` was never set.

## Why examples instead of real files

Three reasons, in order of how often each one bites people.

**A leaked secret is permanent.** Git history is not a place you can delete
from. Removing a token in a later commit leaves it in `git log -p` forever, and
the only real fix is rewriting history and rotating the credential. Keeping the
real file untracked from the first commit avoids the whole situation.

**The example is the documentation.** A compose file with `${POSTGRES_PASSWORD}`
in it tells the reader what has to be decided. A compose file with a redacted
`REDACTED` in it tells them nothing.

**It survives being copied.** Someone cloning this repository gets a file that
works after filling in `.env`, not a file that silently points at addresses on
somebody else's network.

## Inventory

| Directory | Runs on | Public? |
|---|---|---|
| [`portainer/`](portainer/) | LXC 102, Raspberry Pi | LAN |
| [`glance/`](glance/) | LXC 102 | LAN |
| [`vaultwarden/`](vaultwarden/) | LXC 102 | LAN |
| [`monitoring/`](monitoring/) | LXC 102 | LAN |
| [`cloudflared/`](cloudflared/) | LXC 102 | outbound only |
| [`apache/`](apache/) | LXC 102 | **internet, via tunnel** |
| [`nginx-proxy-manager/`](nginx-proxy-manager/) | Raspberry Pi | LAN |
| [`adguard/`](adguard/) | Raspberry Pi | LAN |
| [`nas-media/`](nas-media/) | NAS | LAN |
| [`nextcloud/`](nextcloud/) | P2 | *planned* |

## Conventions applied to every file here

- **`restart: unless-stopped`**, not `always`. `always` restarts a container you
  deliberately stopped when the daemon comes back, which is almost never what
  you wanted at 2 a.m.
- **`security_opt: no-new-privileges:true`** wherever the image tolerates it. It
  stops a process inside the container from gaining privileges through setuid
  binaries.
- **Named volumes for state, bind mounts for configuration.** Named volumes
  survive `docker compose down`; a bind-mounted config file can be edited with
  a normal editor and lives next to the compose file that references it.
- **No `version:` key.** It has been obsolete since Compose v2 and current
  versions print a warning for it.
- **No `latest` on anything that stores data**, where a pinned major exists.
  `postgres:16-alpine`, not `postgres:latest`: a silent major upgrade of a
  database on `docker compose pull` is a genuinely bad day.
