# Troubleshooting

Organised by **symptom**, because that is what you have when something breaks.
Each entry: what you see, the likely causes in order of probability, and the
command that distinguishes them.

---

## Method

Before the specific cases, the general approach, which is worth more than any of
them.

**1. What changed?** Nothing breaks spontaneously. An update, a reboot, a
configuration edit, a certificate expiring, a disk filling. If nothing changed
on your side, something changed on a schedule: a renewal, a rotation, a cron
job, a lease.

**2. Work up the stack, not down.** Power, link, IP, port, service, name,
certificate, application. Checking the application first when the host is down
wastes the most time.

**3. Change one thing at a time.** Two simultaneous changes that fix it leave
you not knowing which, and therefore not knowing what to write down.

**4. Write down what fixed it.** That is what this page is. Every entry below
was a real evening.

---

## Proxmox

### Grey question marks on every guest in the web UI

The guests are almost certainly running fine. The node has lost **quorum** and
`/etc/pve` is read-only, so the UI cannot read their status.

```bash
pvecm status                     # look at "Quorate: Yes/No" and the vote count
systemctl status corosync pve-cluster
journalctl -u corosync -n 50
```

Causes, in order:

- another node is genuinely down, or two of three are
- corosync's network path is broken (switch, cable, or a bridge change)
- the node's clock drifted far enough to break corosync's token exchange

With three nodes, quorum is two. One node down is fine. Two down and the third
goes read-only, which is the whole point of quorum: a minority does not get to
act alone.

If you are deliberately running one node and need it writable:

```bash
pvecm expected 1                 # TEMPORARY. Never leave this set.
```

That command tells corosync to expect one vote. Leaving it set on a cluster that
comes back up is how you get a split brain and two nodes disagreeing about
`/etc/pve`.

### "apt update" fails with 401 on the enterprise repository

A fresh install without a subscription cannot reach the enterprise repository.

```bash
# disable enterprise
sed -i 's/^deb/#deb/' /etc/apt/sources.list.d/pve-enterprise.list
sed -i 's/^deb/#deb/' /etc/apt/sources.list.d/ceph.list 2>/dev/null

# add no-subscription
echo "deb http://download.proxmox.com/debian/pve $(. /etc/os-release && echo "$VERSION_CODENAME") pve-no-subscription" \
  > /etc/apt/sources.list.d/pve-no-subscription.list

apt update
```

### A container will not start

```bash
pct start 102                    # read the error, it is usually explicit
lxc-start -n 102 -F -l DEBUG     # foreground, verbose - the real diagnosis
pct config 102
cat /etc/pve/lxc/102.conf
```

`lxc-start -F -l DEBUG` is the command that actually tells you. `pct start`
often reports "exited with status 1" and nothing more.

Common causes:

| Cause | Sign |
|---|---|
| storage full | `lvs` shows the thin pool at 100% |
| the mount point does not exist on this node | a `mp0` pointing at a path only P1 has |
| a stale lock from a killed operation | `pct unlock 102` |
| the template or disk is gone | `pvesm list local-lvm` |

### "cannot lock file - got timeout"

An earlier operation was interrupted and left a lock.

```bash
pct unlock 102
qm unlock 100
# if that is not enough:
rm /var/lock/qemu-server/lock-100.conf
```

Confirm no operation is genuinely still running first: `tail -f
/var/log/pve/tasks/active`.

### The node is up but the web UI does not load

```bash
systemctl status pveproxy pvedaemon pve-cluster
journalctl -u pveproxy -n 50
systemctl restart pveproxy
```

If `pve-cluster` is dead, `/etc/pve` is not mounted and nothing works. Start it
first; `pveproxy` depends on it.

### Migration fails

```bash
pct migrate 102 pve2 --restart
qm migrate 100 pve2 --online
```

- **LXC cannot live-migrate.** `--restart` is mandatory. There is no way around
  this; a container is a process on a kernel and processes do not move between
  kernels.
- **Local storage means the disk is copied**, which is slow but works. It fails
  if the target storage name does not exist on the target node.
- **A mount point on a path the target node lacks** fails the migration. Check
  `pct config` for `mp0` lines.

---

## Docker

### The container exits immediately

```bash
docker ps -a                     # it IS there, with "Exited (1)"
docker logs <name>               # the reason is almost always here
```

If the logs are empty, the process died before writing anything. Override the
entrypoint and look around:

```bash
docker run -it --rm --entrypoint sh <image>
```

Frequent causes: a required environment variable is unset, a bind-mounted config
file is missing (and Docker created a *directory* in its place), or a permission
error on a volume.

### "port is already allocated"

```bash
ss -tlnp | grep 8080
docker ps --format '{{.Names}}\t{{.Ports}}' | grep 8080
```

Either another container has it, or a host process does. Change the host side of
the mapping; the container side does not matter to anyone but the container.

### A container cannot reach another container

The rule: **service names resolve only on user-defined networks, and you connect
to the container's INTERNAL port.**

```bash
docker network ls
docker network inspect <project>_default
docker compose exec app ping db
docker compose exec app getent hosts db
```

| Mistake | Fix |
|---|---|
| `localhost:5432` | `db:5432` — `localhost` inside a container is the container |
| the published port `5433` | the internal port `5432` |
| containers in different compose projects | put them on a shared external network |

### A container cannot reach the internet

```bash
docker exec <name> ping -c2 1.1.1.1        # is it routing at all
docker exec <name> cat /etc/resolv.conf    # is DNS configured
docker exec <name> getent hosts github.com # does resolution work
```

Ping works but names do not: DNS. Inside an LXC on this network, the container
inherits the LXC's resolver, which is AdGuard. If AdGuard is down, every
container on every host loses name resolution simultaneously, which looks like a
much bigger failure than it is.

### The disk filled up

```bash
docker system df -v
docker image prune -a
docker builder prune
journalctl --vacuum-size=200M
```

Almost always old images or build cache. If it is logs, the daemon has no log
limit configured:

```json
// /etc/docker/daemon.json
{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}
```

Then `systemctl restart docker`. Existing containers keep their old settings
until recreated.

### Docker will not start inside an LXC

```
failed to start daemon: Devices cgroup isn't mounted
```

The container is missing `nesting=1`:

```bash
pct set 102 --features nesting=1,keyctl=1
pct reboot 102
```

`keyctl=1` is additionally needed by some workloads in unprivileged containers.

### Changes to docker-compose.yml have no effect

`docker compose restart` restarts the process in the **existing** container,
built from the old configuration.

```bash
docker compose up -d              # recreates what changed
docker compose up -d --force-recreate
```

---

## Networking and DNS

### A service works by IP but not by name

```bash
dig +short grafana.theminddev.com
dig @192.168.178.178 grafana.theminddev.com   # ask AdGuard directly
dig @1.1.1.1 grafana.theminddev.com           # ask upstream directly
```

If AdGuard and upstream disagree, the problem is AdGuard: a blocklist entry or a
DNS rewrite. If they agree and the browser still fails, the browser is using
DNS-over-HTTPS and bypassing your resolver entirely. Check
`about:networking#dns` in Firefox, `chrome://net-internals/#dns` in Chrome.

### Nothing on the network can resolve anything

The Raspberry Pi is down, and it is the only DNS server the router hands out.

```bash
ping 192.168.178.178
ssh dietpi@192.168.178.178
docker ps | grep adguard
```

Immediate workaround on one machine: set DNS to `1.1.1.1` manually. Internal
names stop working, the internet comes back.

The real fix is a second resolver, which is on the list.

### The certificate expired

```bash
openssl s_client -connect grafana.theminddev.com:443 \
  -servername grafana.theminddev.com </dev/null 2>/dev/null \
  | openssl x509 -noout -dates -subject
```

With DNS-01, renewal fails when the Cloudflare API token expired or lost its
permissions, not because a port is closed. Check NPM's logs, then the token's
scope in the Cloudflare dashboard: it needs `Zone:DNS:Edit` on the zone.

### Infinite redirect loop behind the proxy

The application sees `http`, redirects to `https`, the proxy forwards as `http`
again, repeat.

Missing `X-Forwarded-Proto`. In Nginx Proxy Manager, enable the relevant
advanced options; in a raw nginx config:

```nginx
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Host $host;
```

### "Access through untrusted domain" (Nextcloud)

The `Host` header arriving does not match `trusted_domains`.

```bash
docker compose exec -u www-data app php occ config:system:get trusted_domains
docker compose exec -u www-data app php occ config:system:set trusted_domains 1 --value=cloud.example.com
```

### WebSockets disconnect immediately

The proxy is not passing the upgrade headers. NPM has a **Websockets Support**
toggle per proxy host; it is off by default and it is the answer for Portainer,
Vaultwarden's sync and Jellyfin's playback session.

---

## Hosts

### The machine ran out of memory and a service vanished

```bash
dmesg -T | grep -i -E "out of memory|killed process"
journalctl -k | grep -i "killed process"
```

The OOM killer picks a victim by score, not by guilt. The process that gets
killed is usually the largest, not the one that leaked. In an LXC, the
container's memory limit triggers this while the host has plenty free, which
makes it look inexplicable from the host's point of view.

```bash
pct set 102 --memory 4096
```

### "No space left on device" but df shows free space

Two candidates:

```bash
df -i                            # inodes exhausted
lsof +L1                         # deleted files held open by a running process
```

And on Proxmox, the third:

```bash
lvs -o +data_percent,metadata_percent    # the thin pool, which df cannot see
```

### The machine is slow, CPU is idle

Load average counts processes blocked on I/O, not just on CPU.

```bash
uptime
iostat -x 2 5                    # %util near 100 means the disk is saturated
iotop -o                         # which process is doing the I/O
vmstat 1 5                       # high "wa" column = waiting on I/O
```

### Everything broke at once, all with certificate errors

Check the clock before anything else.

```bash
timedatectl
```

A host whose clock is days off fails TLS validation against every service
simultaneously. It looks catastrophic and it is one command to fix.

### It rebooted and I do not know why

```bash
journalctl -b -1 -n 100          # the END of the previous boot's log
last -x | head                   # reboot and shutdown records
uptime -s                        # when it came up
```

`journalctl -b -1` is the whole trick. The current boot's log begins after the
event.

---

## When you are properly stuck

1. **Read the error again, slowly.** Out loud. The number of times the message
   said exactly what was wrong is embarrassing.
2. **Check the clock and the disk.** Two commands, and between them they explain
   a surprising share of "impossible" failures.
3. **Reproduce it deliberately.** A problem you can trigger on demand is a
   problem you can solve. An intermittent one is a problem you can only guess at.
4. **Change one thing.** Then re-test.
5. **Write it down here.** Including what did *not* work. A page of dead ends
   you have already walked is worth as much as the answer.

---

**Next:** [Hardening](11-hardening.md) — the practices, as opposed to
[`99-security-notes.md`](99-security-notes.md), which is about what this
repository publishes.
