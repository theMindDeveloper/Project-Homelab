# Linux administration

The commands underneath everything else on a Debian-family system, grouped by
what you are trying to find out. Written as the page I want open when something
is wrong and I am not thinking clearly.

---

## systemd

Almost everything that runs at boot is a systemd unit. Understanding four verbs
covers 95% of the work.

```bash
systemctl status  docker          # is it running, since when, last log lines
systemctl start   docker
systemctl stop    docker
systemctl restart docker
systemctl reload  docker          # re-read config WITHOUT dropping connections
systemctl enable  docker          # start at boot
systemctl disable docker
systemctl enable --now docker     # enable and start in one command
```

**`enable` and `start` are different and both are needed.** `start` runs it now
and forgets. `enable` creates the boot-time symlink and does not run it. A
service that works perfectly until the machine reboots was started but never
enabled.

**`reload` beats `restart` where it is supported.** nginx, sshd and Prometheus
all re-read configuration without dropping connections.

### Finding out what is going on

```bash
systemctl list-units --type=service --state=running
systemctl list-units --failed        # the first command after an odd boot
systemctl --failed                   # same thing, shorter
systemctl list-timers                # cron replacement: what runs when
systemctl cat docker                 # the actual unit file, plus overrides
systemctl show docker -p Restart     # one property
systemd-analyze blame                # what made the boot slow
systemd-analyze critical-chain
```

`systemctl --failed` after any unexplained behaviour. It is the single most
useful diagnostic on a systemd machine and it takes one second.

### Editing a unit properly

Never edit a file in `/lib/systemd/system/`. A package update overwrites it.

```bash
systemctl edit docker           # creates a drop-in override
systemctl edit --full docker    # copies the whole unit to /etc, then edits
systemctl daemon-reload         # ALWAYS after touching a unit file
```

A drop-in lives at `/etc/systemd/system/docker.service.d/override.conf` and only
contains what you changed. Package updates leave it alone.

**`daemon-reload` is not optional.** systemd caches unit files. Editing one and
restarting the service without reloading restarts the *old* definition, which
produces ten minutes of "my change had no effect".

### Writing one

```ini
# /etc/systemd/system/health-check.service
[Unit]
Description=Homelab health check
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/root/health-check.sh --quiet
User=root

[Install]
WantedBy=multi-user.target
```

```ini
# /etc/systemd/system/health-check.timer
[Unit]
Description=Run the health check every 15 minutes

[Timer]
OnCalendar=*:0/15
Persistent=true          # run immediately if a scheduled run was missed

[Install]
WantedBy=timers.target
```

```bash
systemctl daemon-reload
systemctl enable --now health-check.timer
systemctl list-timers health-check.timer
```

Timers over cron, on a systemd machine: they log to the journal, they have
dependencies, `Persistent=true` handles a missed run after downtime, and
`systemctl list-timers` shows you the whole schedule in one place. Cron gives
you none of that and mails you output nobody reads.

---

## journalctl

```bash
journalctl -u docker              # one unit
journalctl -u docker -f           # follow
journalctl -u docker -n 100       # last 100 lines
journalctl -u docker --since "1 hour ago"
journalctl --since "2026-08-11 03:00" --until "2026-08-11 04:00"
journalctl -p err -b              # errors only, this boot
journalctl -b -1                  # the PREVIOUS boot
journalctl -k                     # kernel messages (dmesg)
journalctl -f -u docker -u nginx  # several units at once
journalctl --disk-usage
journalctl --vacuum-size=200M
journalctl --vacuum-time=30d
```

**`journalctl -b -1` is the command for "it crashed and rebooted".** The current
boot's log starts after the crash and tells you nothing. The previous boot's log
ends at the moment it died.

**`journalctl -p err -b`** is the fastest first look at a machine behaving oddly:
every error-or-worse message since boot, in one screen.

Make the journal persistent if it is not; by default some systems keep it in RAM
and lose it on reboot, which is exactly when you needed it:

```bash
mkdir -p /var/log/journal && systemd-tmpfiles --create --prefix /var/log/journal
```

---

## Processes, CPU, memory

```bash
htop                              # install it, use it
ps aux --sort=-%mem | head -15    # top memory consumers
ps aux --sort=-%cpu  | head -15
ps -ef --forest                   # the process tree
pgrep -a nginx                    # PIDs plus command line
pkill -f "python.*worker"         # kill by command line pattern

uptime                            # load average: 1, 5, 15 minutes
free -h
vmstat 1 5
```

**Load average is not CPU percentage.** It is the number of processes running or
waiting, including waiting on disk. On a 4-core machine, a load of 4.0 is fully
busy; 8.0 means twice as much work as capacity. A high load with idle CPU means
processes are blocked on I/O, which is a completely different problem.

**`free -h` and the `available` column.** Linux uses all spare RAM for page
cache, so `free` looks alarmingly low on a healthy machine. `available` is the
number that matters: memory that could be given to a new process right now.

### Signals

```bash
kill -TERM <pid>     # 15: please stop  (the default)
kill -HUP  <pid>     #  1: re-read your configuration
kill -KILL <pid>     #  9: die now, no cleanup
kill -QUIT <pid>     #  3: stop and dump core
```

`kill -9` is not the first thing to try, it is the last. It gives the process no
chance to flush buffers or close files. That is how a database gets corrupted.

---

## Disk and filesystems

```bash
df -h                             # usage per filesystem
df -i                             # INODES - full inodes look like a full disk
du -xh --max-depth=1 / | sort -h | tail -20
lsblk -f                          # devices, filesystems, UUIDs, mountpoints
mount | column -t
findmnt

ncdu /                            # interactive, worth installing
lsof +L1                          # deleted files still held open
```

**`df -i`.** A filesystem with free space but no free inodes reports
"No space left on device" and `df -h` shows 40% used. Millions of tiny files,
usually a mail queue or a cache, is the cause.

`lsof +L1` explains the other version of that puzzle: `du` says 20 GB, `df` says
80 GB. A process is holding a deleted file open and the space is not released
until it restarts.

### fstab

```bash
blkid                             # get the UUID
# /etc/fstab
UUID=xxxx-xxxx  /srv/data  ext4  defaults,noatime  0  2
mount -a                          # TEST IT before rebooting
```

**Always `mount -a` before rebooting.** A typo in `/etc/fstab` drops the machine
into emergency mode at boot, and a headless machine that boots into emergency
mode looks exactly like a dead machine.

Use `UUID=`, never `/dev/sdb1`. Device names are assigned in detection order and
adding a disk renames the others.

---

## Networking

```bash
ip a                              # addresses
ip r                              # routing table
ip -br a                          # brief, readable
ip link set eth0 up

ss -tlnp                          # what is LISTENING (replaces netstat)
ss -tunap                         # everything, TCP and UDP
ss -tp state established

ping -c4 192.168.178.1
traceroute 1.1.1.1
mtr 1.1.1.1                       # traceroute plus ping, continuously
nc -zv 192.168.178.87 3000        # is that port open
curl -I https://grafana.theminddev.com
curl -v telnet://192.168.178.87:3000

dig +short grafana.theminddev.com
resolvectl status
```

**`ss -tlnp` is the command.** `t` TCP, `l` listening, `n` numeric, `p`
processes. It answers "what is on port 3000 and why".

The distinction that matters in the output: `0.0.0.0:3000` is listening on every
interface. `127.0.0.1:3000` is listening on loopback only, which works perfectly
from the machine itself and is invisible from everywhere else. That is the most
common cause of "the service is running but I cannot reach it".

---

## Users and permissions

```bash
adduser deploy                    # interactive, sets up home and shell
usermod -aG docker deploy         # -a is ESSENTIAL: append, do not replace
groups deploy
id deploy

chown -R user:group /path
chmod 640 /etc/service/config     # rw for owner, r for group, nothing for others
chmod +x script.sh
```

**`usermod -G` without `-a` removes every other group.** Doing that to your own
account and losing `sudo` is a classic. Always `-aG`.

Numeric permissions: read 4, write 2, execute 1, in owner-group-other order.
`644` = owner rw, everyone r. `600` = owner only. `755` = everyone can execute.

```bash
# the two that matter for secrets
chmod 600 .env
chmod 700 ~/.ssh
chmod 600 ~/.ssh/authorized_keys
```

SSH refuses to use keys with loose permissions, silently falls back to password
authentication, and the failure message says nothing useful.

---

## SSH

```bash
ssh-keygen -t ed25519 -C "laptop"
ssh-copy-id root@192.168.178.20
ssh -i ~/.ssh/id_ed25519 root@192.168.178.20
ssh -J jump@host target           # through a jump host
ssh -L 8006:192.168.178.20:8006 user@host   # local port forward
```

`ed25519`, not RSA. Shorter, faster, and 4096-bit RSA has no advantage over it.

### `~/.ssh/config`

Worth writing once for a lab with several hosts:

```
Host p1
    HostName 192.168.178.20
    User root
    IdentityFile ~/.ssh/id_ed25519

Host p2
    HostName 192.168.178.50
    User root

Host *
    ServerAliveInterval 60
    ServerAliveCountMax 3
```

Now `ssh p1` works. `ServerAliveInterval` stops idle sessions from being dropped
by a NAT timeout, which is the reason terminals freeze after a coffee break.

### Hardening sshd

```
# /etc/ssh/sshd_config
PermitRootLogin prohibit-password    # keys only for root
PasswordAuthentication no
PubkeyAuthentication yes
```

**Verify a key login works in a second terminal before you close the first
one.** Locking yourself out of a headless machine means physical access.

---

## Packages

```bash
apt update && apt upgrade
apt full-upgrade                  # allows removing packages to resolve deps
apt install --no-install-recommends pkg
apt list --upgradable
apt search nginx
apt show nginx
apt autoremove
apt-mark hold pve-kernel          # pin a package

dpkg -l | grep nginx
dpkg -L nginx                     # every file the package installed
dpkg -S /usr/sbin/nginx           # which package owns this file
```

Unattended security updates, worth enabling on every machine here:

```bash
apt install unattended-upgrades
dpkg-reconfigure -plow unattended-upgrades
```

---

## Text and log wrangling

```bash
grep -r "pattern" /etc            # recursive
grep -i -n -C3 "error" file.log   # case-insensitive, line numbers, 3 lines context
grep -v "^#" config | grep -v "^$" # strip comments and blank lines

tail -f /var/log/syslog
tail -f file | grep --line-buffered ERROR   # --line-buffered or grep buffers

awk '{print $1}' access.log | sort | uniq -c | sort -rn | head
sed -i 's/old/new/g' file
sed -i.bak 's/old/new/g' file     # keeps a .bak
find /var/log -name "*.gz" -mtime +30 -delete
```

`grep -v "^#" config | grep -v "^$"` is the one worth memorising. A 400-line
configuration file with 380 lines of comments becomes twenty lines you can
actually read.

---

## Time

```bash
timedatectl                       # time, timezone, is NTP synced
timedatectl set-timezone Europe/Berlin
timedatectl set-ntp true
chronyc sources                   # if chrony is used
```

**A wrong clock breaks TLS everywhere at once.** Certificates have validity
windows. A host whose clock is a week off gets certificate errors from every
service simultaneously, which looks like a catastrophic failure and is a
one-line fix. `timedatectl` is worth checking early when several unrelated
things break together.

---

## The order to check things in

When a machine is misbehaving and you do not know why:

```bash
systemctl --failed                # 1. did something fail to start
journalctl -p err -b --no-pager | tail -40   # 2. what errored since boot
df -h ; df -i                     # 3. is a disk or inode table full
free -h                           # 4. is memory exhausted
uptime                            # 5. is it overloaded, or blocked on I/O
ss -tlnp                          # 6. is the thing listening
timedatectl                       # 7. is the clock right
dmesg -T | tail -40               # 8. did the kernel complain (OOM killer)
```

Eight commands, thirty seconds, and they cover the overwhelming majority of
"the server is being weird". Step 8 is where you find `Out of memory: Killed
process`, which explains a service that vanished without logging anything.

---

**Next:** [Troubleshooting](10-troubleshooting.md) — the same idea, organised by
symptom.
