# Runbook 02 · Docker and Portainer on a new LXC

**Goal** From an empty Proxmox node to Portainer running in a browser at
`https://port1.theminddev.com`, with TLS, in one sitting.

**Time** 20 minutes.
**Prerequisites** root on a Proxmox node. A free container ID and IP. Nginx
Proxy Manager already running (steps 6 and 7 only).
**Reverses cleanly?** Yes — `pct destroy` removes all of it.

This is the end-to-end walkthrough: create the container, install Docker,
harden it a little, start a service with Compose, put it behind the reverse
proxy with a real certificate, and log in.

Every other service in this lab is the same six steps with a different compose
file.

---

## The finished state

```
browser
  |  https://port1.theminddev.com
  v
AdGuard Home (.178:53)  --> returns 192.168.178.178
  |
  v
Nginx Proxy Manager (.178:443)   TLS terminates here
  |  proxy_pass https://192.168.178.91:9443
  v
LXC 111 "portainer-demo" (.91)
  |
  v
Docker container "portainer"  :9443
  |
  v
/var/run/docker.sock  (read-only)
```

---

## 1 · Create the container

Full detail in [Runbook 01](01-create-an-lxc-container.md). The short version,
with the two features Docker needs:

```bash
pct create 111 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
  --hostname     portainer-demo \
  --cores        2 \
  --memory       2048 \
  --swap         512 \
  --rootfs       local-lvm:16 \
  --net0         name=eth0,bridge=vmbr0,ip=192.168.178.91/24,gw=192.168.178.1 \
  --nameserver   192.168.178.178 \
  --onboot       1 \
  --unprivileged 1 \
  --features     nesting=1,keyctl=1

pct start 111
pct enter 111
```

**`nesting=1` is not optional and `keyctl=1` is not decoration.**

`nesting=1` permits a container runtime inside the container. Without it, the
Docker daemon starts and immediately exits with:

```
failed to start daemon: Devices cgroup isn't mounted
```

which reads like a broken kernel and is one `pct set` away from fixed.

`keyctl=1` gives the container access to the kernel keyring. Unprivileged
containers block it by default and some Docker workloads need it. It costs
nothing to include.

If you forgot either:

```bash
# on the HOST
pct set 111 --features nesting=1,keyctl=1
pct reboot 111
```

---

## 2 · Prepare the container

Everything from here runs **inside** the container.

```bash
apt update && apt upgrade -y
apt install -y --no-install-recommends ca-certificates curl gnupg
timedatectl set-timezone Europe/Berlin
```

Verify before continuing. If any of these fail, fix it now rather than debugging
it later through two layers of container:

```bash
ip a | grep 192.168.178.91          # the address is where you put it
getent hosts download.docker.com    # DNS works
timedatectl | grep "System clock"   # synchronised - TLS depends on it
```

---

## 3 · Install Docker

From Docker's own repository, **not** Debian's `docker.io`. The distro package
lags badly and ships no `docker compose` plugin, leaving you on the end-of-life
standalone binary with subtly different behaviour.

```bash
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg \
  | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

cat > /etc/apt/sources.list.d/docker.list <<EOF
deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable
EOF

apt update
apt install -y docker-ce docker-ce-cli containerd.io \
               docker-buildx-plugin docker-compose-plugin
systemctl enable --now docker
```

### Configure log rotation now, not after the disk fills

Docker's default `json-file` driver has **no size limit**. One chatty container
will fill the disk with a single log file. This is the most common cause of a
homelab running out of space and it is two minutes to prevent.

```bash
mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
systemctl restart docker
```

### Verify

```bash
docker --version
docker compose version
docker run --rm hello-world
```

`hello-world` exercises the whole path: pull from the registry, create a
container, run it, capture its output. If it works, Docker works.

The scripted version of this entire step is
[`scripts/install-docker.sh`](../scripts/install-docker.sh).

---

## 4 · Start Portainer with Compose

```bash
mkdir -p /opt/portainer && cd /opt/portainer
```

```yaml
# /opt/portainer/docker-compose.yml
services:
  portainer:
    image: portainer/portainer-ce:lts
    container_name: portainer
    restart: unless-stopped
    ports:
      - "9443:9443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - portainer_data:/data
    security_opt:
      - no-new-privileges:true

volumes:
  portainer_data:
```

```bash
docker compose config        # render and validate BEFORE starting
docker compose up -d
docker compose ps
docker compose logs -f
```

`docker compose config` first, every time. It expands every variable and fails
loudly on a typo, instead of quietly starting a container that is subtly wrong.

### The line worth stopping at

```yaml
- /var/run/docker.sock:/var/run/docker.sock:ro
```

That mount is what makes Portainer work, and it is the most dangerous line in
this repository.

**Write access to the Docker socket is root on the host.** Not root in the
container: root on the *host*. Anyone who can talk to that socket can start a
privileged container that bind-mounts `/` and do anything they like.

`:ro` makes the *socket file* read-only, which blocks some operations and
meaningfully reduces the surface. It does not make the mount safe in principle.
It is mounted here because container management is the entire purpose of
Portainer, and it is worth knowing exactly what is being traded rather than
copying the line from a tutorial.

The other lines:

- **`restart: unless-stopped`**, not `always` — `always` restarts a container
  you deliberately stopped, the next time the host reboots.
- **`portainer_data:/data`** is a named volume. Delete the container and the
  data survives; `docker compose down -v` deletes it.
- **`no-new-privileges:true`** blocks privilege escalation through setuid
  binaries inside the container. One line, no downside.

---

## 5 · First login

Portainer serves HTTPS on 9443 with its **own self-signed certificate**, so the
browser will warn. That is expected at this stage; step 7 replaces it with a
real one.

```
https://192.168.178.91:9443
```

1. **Create the admin user immediately.**
2. Choose **Get Started** to manage the local Docker environment.

### The timeout that catches everyone

**Portainer disables the setup form if nobody creates an admin user within a few
minutes of first start.** This is deliberate: an unclaimed Portainer on a
network is an open door to the Docker socket. The screen says the instance is
timed out for security purposes.

The fix is to restart the container, which restarts the window:

```bash
docker restart portainer
```

Then create the user straight away.

![Portainer container list for LXC 102](../assets/screenshots/portainer-lxc102-containers.png)

*What it looks like once the host has been in use for a while: every container
in LXC 102, its state, its stack and the exact image tag it is running. The
Stack column is Portainer's view of compose projects, which is why containers
started from a compose file group together and ones started with `docker run`
show `-`.*

### Password

Twelve characters minimum, enforced. Generate it in Vaultwarden and store it
there. This account controls every container on this host, which means it
controls the host.

---

## 6 · DNS

The wildcard `A` record for `*.theminddev.com` already points at
`192.168.178.178`, so a new subdomain needs **no DNS change at all**. It
resolves the moment you use it.

Confirm:

```bash
dig +short port1.theminddev.com          # expect 192.168.178.178
```

Worth restating what that means: the name resolves for the entire internet, and
the answer is an RFC1918 address nobody outside the LAN can route to. See
[`docs/05-networking-dns-tls.md`](../docs/05-networking-dns-tls.md).

---

## 7 · Put it behind Nginx Proxy Manager

In the NPM admin UI at `http://192.168.178.178:81`:

**Hosts → Proxy Hosts → Add Proxy Host**

| Field | Value |
|---|---|
| Domain Names | `port1.theminddev.com` |
| Scheme | **`https`** |
| Forward Hostname / IP | `192.168.178.91` |
| Forward Port | `9443` |
| Cache Assets | off |
| Block Common Exploits | on |
| **Websockets Support** | **on** |

**SSL tab**

| Field | Value |
|---|---|
| SSL Certificate | the existing `*.theminddev.com` wildcard |
| Force SSL | on |
| HTTP/2 Support | on |
| HSTS Enabled | on |

**Three settings that are not obvious:**

**Scheme must be `https`.** Portainer speaks TLS on 9443. Setting `http` gives a
502 and a confusing log line about an invalid response.

**Websockets Support must be on.** Portainer's console and live log views are
WebSockets. Without it, the UI loads perfectly and the terminal disconnects
instantly, which does not look like a proxy problem at all.

**The certificate is a wildcard**, issued once over DNS-01 and reused for every
subdomain. There is no per-service certificate request, and no inbound port is
opened for renewal.

If NPM refuses to connect upstream because Portainer's certificate is
self-signed, that is expected — NPM does not verify upstream certificates by
default, which is the right behaviour for a LAN backend it is already
authenticating by address.

---

## 8 · Verify the whole path

Work up the stack. Where it fails tells you who is at fault.

```bash
# 1. the container is alive
ping -c2 192.168.178.91

# 2. something is listening on 9443
nc -zv 192.168.178.91 9443

# 3. Portainer answers directly
curl -kI https://192.168.178.91:9443

# 4. the name resolves
dig +short port1.theminddev.com

# 5. it answers through the proxy, with a valid certificate
curl -I https://port1.theminddev.com

# 6. the certificate is real and covers the name
openssl s_client -connect port1.theminddev.com:443 \
  -servername port1.theminddev.com </dev/null 2>/dev/null \
  | openssl x509 -noout -dates -subject -issuer
```

| Fails at | Blame |
|---|---|
| 1 | container down, or the address is wrong |
| 2 | Docker container not running — `docker compose ps` |
| 3 | Portainer erroring — `docker compose logs` |
| 4 | DNS: AdGuard, or a browser using DNS-over-HTTPS |
| 5 | NPM: wrong scheme, wrong upstream, or no proxy host |
| 6 | certificate expired, or does not cover this name |

Then open `https://port1.theminddev.com` and log in. No browser warning.

---

## 9 · Record it

```yaml
# inventory/inventory.yml
  - vmid: 111
    name: portainer-demo
    node: pve
    type: lxc
    address: 192.168.178.91
    unprivileged: true
    features: nesting=1,keyctl=1
    purpose: Docker host, demonstration

  - name: Portainer demo
    host: lxc-111
    runtime: docker
    ports: {https: 9443}
    hostname: port1.theminddev.com
    exposure: lan
```

Add it to [`compose/glance/glance.yml`](../compose/glance/glance.example.yml) as
a monitor tile with `allow-insecure: true`, and to
[`scripts/health-check.sh`](../scripts/health-check.sh).

A service nobody is watching is a service that will be down for two weeks before
you notice.

---

## Maintaining it

```bash
cd /opt/portainer
docker compose pull
docker compose up -d
docker image prune -f
```

Three commands, monthly. That is the entire update process for every Docker
service in this lab.

---

## Undo

```bash
# just the service
cd /opt/portainer && docker compose down -v

# the whole container
pct stop 111 && pct destroy 111
```

Then delete the proxy host in NPM and the entry in the inventory.

---

## What this walkthrough demonstrates

Worth saying explicitly, because it is easy to read it as "install Portainer":

- **Two container technologies, deliberately layered.** LXC 111 is the
  *machine*: systemd, apt, an IP, a lifetime in years. Docker inside it is the
  *application*: replaced whenever a new image ships. That distinction is the
  subject of [`docs/01-docker.md`](../docs/01-docker.md).
- **Unprivileged by default**, with `nesting` and `keyctl` granted explicitly
  because a specific thing needs them, rather than reaching for a privileged
  container.
- **TLS on an internal service with nothing exposed**, via a wildcard
  certificate issued over DNS-01.
- **The dangerous line is called out**, not copied silently.
- **Verification is part of the procedure**, not an afterthought, and it is
  ordered so that a failure identifies its own cause.

---

**Next:** [Runbook 04 · Add a service to Nginx Proxy
Manager](04-nginx-proxy-manager-vhost.md)
