# Docker

What it actually is, the mental model that makes the commands obvious, and the
commands themselves.

If you only read one section, read [The mental model](#the-mental-model). Every
command below follows from it, and the errors people get stuck on are almost
always a broken mental model rather than a wrong flag.

---

## What Docker is

**Docker runs a process on your kernel with a lie about what it can see.**

That is the whole thing. A container is not a small virtual machine. There is no
guest kernel, no emulated hardware, no boot sequence. When you run
`docker run nginx`, the nginx process starts on *your* kernel, as a normal
process. `ps aux` on the host will show it.

What makes it a container is that the kernel has been told to lie to that
process about six or seven things:

| Kernel feature | The lie it tells |
|---|---|
| **PID namespace** | "you are process 1 and there are no other processes" |
| **Mount namespace** | "this image is the entire filesystem" |
| **Network namespace** | "you have your own network card and IP address" |
| **UTS namespace** | "the hostname is `a3f9c2b1`" |
| **User namespace** | "you are root" (while being UID 100000 on the host) |
| **Cgroups** | not a lie: a hard limit on CPU, memory and I/O |
| **Capabilities** | root, but without most of the things root can do |

Namespaces control **what a process can see**. Cgroups control **how much it can
use**. Capabilities control **what it is allowed to do**. Docker is a convenient
front end over all three, plus a packaging format and a distribution mechanism.

None of this is Docker's invention. The kernel features predate it. What Docker
contributed, and the reason it took over, is the image format and the registry:
a reproducible, layered, content-addressed tarball that you can `push` and
`pull`. The isolation was already there. The *distribution* was the hard part.

### The consequences

Because there is no guest kernel:

- A container starts in **milliseconds**, because nothing boots.
- It uses **no memory it is not using**. A VM given 4 GB holds 4 GB.
- It can only run **Linux**. There is no such thing as a Windows container on a
  Linux host, and "Docker on macOS/Windows" is Docker inside a hidden Linux VM.
- A **kernel exploit from inside the container is a host compromise**. This is
  the security difference from a VM and the reason untrusted workloads belong
  in a VM. See [`04-lxc-vs-vm.md`](04-lxc-vs-vm.md).
- It **cannot load kernel modules** or run a different kernel version.

---

## The mental model

Four nouns. Confusing any two of them causes most Docker frustration.

```
Dockerfile  --build-->  Image  --run-->  Container  --commit--> (a new image)
                          |                  |
                       read-only       thin writable layer
                        layers          DELETED on removal
```

**Dockerfile** — a recipe. Text. Not involved at runtime at all.

**Image** — a stack of read-only filesystem layers plus metadata (which command
to run, which ports, which user). Immutable. Shared between containers: ten
containers from `nginx:alpine` store the image once.

**Container** — a running (or stopped) instance of an image, plus one thin
**writable layer** on top. Everything the process writes goes into that layer.

**Volume** — storage that lives *outside* the container's writable layer and
survives the container being deleted.

### The single most important consequence

**A container's filesystem is disposable. If you did not put it in a volume, it
is gone when the container is removed.**

Not when it stops. When it is *removed*, which `docker compose down`,
`docker rm`, `docker compose pull && up -d` and every upgrade all do.

This is not a flaw. It is the point: it forces you to be explicit about what is
state and what is not, which is exactly the discipline that makes a service
rebuildable. But it catches everyone once, usually with a database.

### Images are layered, and layers are cached

Each instruction in a Dockerfile creates a layer. Layers are content-addressed
and shared. That is why:

- Pulling a second image from the same base is fast: the base layers are there.
- Changing the last line of a Dockerfile rebuilds fast; changing the first line
  rebuilds everything.
- **Deleting a secret in a later layer does not remove it.** `RUN wget` a token,
  `RUN rm` the token, and the token is still in the earlier layer, readable by
  anyone who pulls the image. Same problem as git history, same non-solution.

---

## Docker vs LXC vs VM

The comparison people actually want, in one table. The long version, with the
decision rule used in this lab, is in [`04-lxc-vs-vm.md`](04-lxc-vs-vm.md).

| | Docker container | LXC container | Virtual machine |
|---|---|---|---|
| Kernel | shared with host | shared with host | its own |
| Contains | **one process** | **a whole OS userland** | a whole OS |
| Init system | none (PID 1 is your app) | systemd | systemd |
| Analogy | a packaged application | a lightweight server | a computer |
| Lifetime | seconds to months, disposable | months to years, pet | months to years, pet |
| You update it by | pulling a new image and recreating | `apt upgrade` inside it | `apt upgrade` inside it |
| State | in volumes, explicitly | on its filesystem, implicitly | on its disk |
| Boot | milliseconds | under a second | 10 to 60 seconds |
| Managed by | Docker / Compose / Kubernetes | Proxmox, LXD | Proxmox, ESXi, KVM |

**The distinction that matters:** LXC gives you *a machine*. Docker gives you
*an application*. You SSH into an LXC container and it behaves like a small
Debian server, because it is one. You do not SSH into a Docker container,
because there is nothing in there except your application; `docker exec` gets
you a shell only if the image happens to contain one.

**In this lab both are used, deliberately layered.** LXC 102 is a Debian
container that acts as a Docker *host*: it has systemd, an IP address, apt, and
a lifetime measured in years. Inside it run a dozen Docker containers that are
replaced whenever a new image is published. The LXC is the machine, the Docker
containers are the applications.

---

## Installing

Use Docker's own repository, never Debian's `docker.io` package. The distro
package lags badly and does not ship the `docker compose` plugin, which leaves
you on the old standalone `docker-compose` binary with subtly different
behaviour.

The full script, with the log-rotation configuration that everyone forgets, is
[`scripts/install-docker.sh`](../scripts/install-docker.sh).

**Inside an LXC container**, the container needs `nesting=1` first, or the
daemon starts and immediately dies with a cgroup error that reads like a kernel
bug:

```bash
pct set 102 --features nesting=1,keyctl=1
pct reboot 102
```

---

## Commands, grouped by intent

### Running something

```bash
docker run hello-world                     # pull if needed, run, exit
docker run -d --name web -p 8080:80 nginx  # detached, named, port published
docker run -it --rm debian:12 bash         # interactive, delete on exit
docker run -d --restart unless-stopped ... # survive a daemon restart
```

The flags worth understanding rather than memorising:

| Flag | Meaning | Trap |
|---|---|---|
| `-d` | detached, run in the background | without it your terminal is the container's console; Ctrl-C stops it |
| `--rm` | delete the container when it exits | do not use with anything that has state |
| `-p 8080:80` | **host** 8080 to **container** 80 | the order is `host:container` and getting it backwards is a rite of passage |
| `-v /host:/ctr` | bind mount a host path | the host path is created as an empty **directory** if it does not exist, which is why "my config file became a folder" |
| `-e KEY=val` | environment variable | appears in `docker inspect` and in `ps`, so it is not a good place for a secret |
| `-it` | interactive terminal | pointless with `-d` |
| `--network` | attach to a network | see [Networking](#networking) |

### Looking at what is happening

```bash
docker ps                        # running containers
docker ps -a                     # including stopped and exited ones
docker logs -f web               # follow the logs
docker logs --tail 100 web
docker logs --since 30m web
docker stats                     # live CPU, memory, network, per container
docker top web                   # processes inside the container
docker inspect web               # everything, as JSON
docker inspect -f '{{.State.Health.Status}}' web
docker port web                  # what is actually published
```

`docker ps -a` is the one people forget. A container that crashed on start does
not appear in `docker ps`, so it looks like nothing happened. It is in
`docker ps -a` with `Exited (1)` and its logs explain why.

### Getting inside

```bash
docker exec -it web bash         # a shell in a RUNNING container
docker exec -it web sh           # alpine images have no bash
docker exec -u root -it web sh   # as root, when the image drops privileges
docker cp web:/etc/nginx/nginx.conf ./   # copy a file out
docker cp ./nginx.conf web:/etc/nginx/   # and back in
```

`docker exec` needs the container to be **running**. If it exited, there is
nothing to exec into. To inspect a container that will not start, override the
entrypoint:

```bash
docker run -it --rm --entrypoint sh myimage
```

That is the debugging trick worth remembering.

### Stopping and removing

```bash
docker stop web                  # SIGTERM, then SIGKILL after 10 s
docker stop -t 30 web            # give it 30 s to shut down cleanly
docker kill web                  # SIGKILL immediately
docker restart web
docker rm web                    # remove a stopped container
docker rm -f web                 # stop and remove in one go
```

`docker stop` sends `SIGTERM` to PID 1 in the container. If your application
ignores `SIGTERM`, it gets killed 10 seconds later, mid-write. Databases care
about this. `-t 30` is cheap insurance.

### Images

```bash
docker images                    # what is stored locally
docker pull nginx:alpine
docker rmi nginx:alpine
docker history nginx:alpine      # the layers and their sizes
docker build -t myapp:1.0 .
docker tag myapp:1.0 myapp:latest
docker save myapp:1.0 | gzip > myapp.tar.gz    # export without a registry
docker load < myapp.tar.gz
```

**On tags:** `latest` is not a special tag. It is a default string with no
meaning. `nginx:latest` today and `nginx:latest` in six months are different
images with no warning between them. Pin anything that stores data.

### Volumes and data

```bash
docker volume ls
docker volume create appdata
docker volume inspect appdata     # shows the real path on the host
docker volume rm appdata
docker volume prune               # delete every volume no container uses
```

Two ways to keep data, and they are not interchangeable:

| | Named volume | Bind mount |
|---|---|---|
| Syntax | `-v appdata:/data` | `-v /srv/app:/data` |
| Lives in | `/var/lib/docker/volumes/` | wherever you said |
| Managed by | Docker | you |
| Permissions | Docker sets them | yours, and they will be wrong at least once |
| Backup | `docker run --rm -v appdata:/d -v $PWD:/b alpine tar czf /b/x.tgz /d` | copy the directory |
| Use for | **application state**: databases, uploads | **configuration**: files you want to edit with a normal editor |

The rule applied throughout this lab: **named volumes for state, bind mounts for
config.** State should not be something you can accidentally `rm -rf`, and
config should be something you can open in an editor.

### Cleaning up

```bash
docker system df                 # where the disk went
docker container prune           # remove stopped containers
docker image prune               # remove dangling images
docker image prune -a            # remove every image no container uses
docker system prune              # containers + networks + dangling images
docker system prune -a --volumes # everything unused, INCLUDING VOLUMES
```

**`--volumes` deletes data.** A volume belonging to a stopped container counts
as unused. Read `docker volume ls` before running it, every time.

`docker system df` is the first command to run when a disk fills up. Usually the
answer is build cache or old images, not anything interesting.

---

## Networking

Docker creates a bridge and gives each container an address on it. Four modes
matter:

| Mode | What it does | When to use it |
|---|---|---|
| **bridge** (default) | private network per compose project, NAT to the outside | almost always |
| **host** | no network namespace, the container uses the host's stack directly | when broadcast or mDNS discovery must work, e.g. Syncthing |
| **none** | no networking at all | a batch job that only touches mounted files |
| **container:X** | share another container's stack | sidecars, VPN gateways |

### The rule that solves most connection problems

**Containers on the same user-defined network reach each other by service
name.** Containers on the default bridge do not.

```yaml
services:
  app:
    # connects to postgres at hostname "db", port 5432 - the INTERNAL port
  db:
    image: postgres:16
    ports:
      - "5433:5432"   # this is for YOU, from the host. app does not use it.
```

`app` talks to `db:5432`, not `db:5433` and not `localhost:5432`. The published
port is a door from the host into the container; it has nothing to do with
container-to-container traffic. Compose creates a user-defined network for the
project automatically, which is why service names resolve.

**`localhost` inside a container means the container.** Not the host. A config
pointing a web app at `localhost:5432` for its database will fail with
"connection refused" and the fix is to use the service name.

To reach the host from inside a container, `host.docker.gateway` is not portable
on Linux; add `extra_hosts: ["host.docker.internal:host-gateway"]`.

### Publishing ports safely

```yaml
ports:
  - "8080:80"              # 0.0.0.0:8080 - every interface, including WAN-facing
  - "127.0.0.1:8080:80"    # localhost only
  - "192.168.178.87:8080:80"  # one specific interface
```

The first form binds to **all** interfaces. On a machine with a public address
that publishes the service to the internet, and **Docker writes its own iptables
rules that bypass ufw**, so a firewall that says the port is closed will be
wrong. This surprises people badly. If a service should be LAN-only, bind it to
a specific address or keep the host off the public internet.

---

## Security, in the order that matters

**1. Do not mount the Docker socket unless you mean it.**
`/var/run/docker.sock` is root on the host. Anyone who can talk to it can start
a privileged container that mounts `/`. Portainer and similar tools need it;
mount it `:ro` and understand that read-only reduces, not removes, the risk.

**2. Do not run `--privileged`.** It disables essentially every protection at
once. If something needs one capability, grant that one capability:

```yaml
cap_drop: [ALL]
cap_add:  [NET_BIND_SERVICE]
```

**3. Run as a non-root user.** Most official images still run as root by
default. `user: "1000:1000"` in compose, or `USER` in the Dockerfile.

**4. `no-new-privileges`.** One line, stops privilege escalation through setuid
binaries inside the container:

```yaml
security_opt:
  - no-new-privileges:true
```

**5. Read-only root filesystem** where the image tolerates it, with `tmpfs` for
the paths it must write:

```yaml
read_only: true
tmpfs:
  - /tmp
  - /var/run
```

**6. Secrets are not environment variables.** `-e PASSWORD=hunter2` shows up in
`docker inspect`, in the daemon logs and in `ps` on the host. Compose `secrets`,
or a file mounted read-only, are better. In a homelab an `.env` file with
restrictive permissions is a reasonable compromise, as long as it is gitignored.

**7. Update images.** A container running `nginx:alpine` from a year ago has a
year of unpatched CVEs. `docker compose pull && docker compose up -d` is the
whole update process and it should be a monthly habit.

---

## Things that will bite you

**The port order.** `-p host:container`. Always. `-p 80:8080` when you meant
`-p 8080:80` produces a service that is inexplicably unreachable.

**A bind mount to a path that does not exist** creates an empty **directory**
there, then mounts it over the file you wanted. Symptom: the application starts
with default configuration and swears your config file is not there. Create the
file first.

**Logs fill the disk.** The default `json-file` driver has **no size limit**.
One chatty container will eat a 90 GB disk. Set it globally in
`/etc/docker/daemon.json`:

```json
{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}
```

**`docker compose down -v` deletes your volumes.** `down` alone does not.
The `-v` is a single character between "restart the stack" and "delete the
database".

**The build context is uploaded.** `docker build .` sends the entire directory
to the daemon. A `.git` directory or a stray backup makes builds slow and can
bake secrets into the image. Use `.dockerignore`.

**`latest` is not "the newest".** It is whatever the publisher last tagged
`latest`, which may be older than a numbered tag, and it changes silently.

**Time drift inside containers.** Containers use the host clock, so a host with
a wrong clock breaks TLS everywhere at once. Symptom: certificate errors in
every container simultaneously.

**Docker bypasses ufw.** Publishing a port punches through the firewall via
Docker's own iptables chain. `ufw status` will happily report the port as
denied while the world can reach it.

**Alpine images have no bash.** `docker exec -it x bash` fails with
"executable file not found". Use `sh`.

---

## Where this lab uses Docker

| Host | Containers |
|---|---|
| LXC 102 on P1 | Glance, Vaultwarden, Portainer, Grafana, Prometheus, Apache, cloudflared |
| Raspberry Pi 5 | Nginx Proxy Manager, AdGuard Home, Portainer |
| NAS (UGOS Pro) | Jellyfin, Immich, Syncthing |
| LXC 105 | Pterodactyl Wings, which runs each game server as its own container |

Every compose file is in [`compose/`](../compose/), as an example with variables
instead of values. The reasoning for that is in
[`99-security-notes.md`](99-security-notes.md).

---

**Next:** [Docker Compose](02-docker-compose.md) — the file format, the commands
and why `up -d` is not the same as `restart`.
