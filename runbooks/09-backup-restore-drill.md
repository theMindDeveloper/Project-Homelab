# Runbook 09 · The backup restore drill

**Goal** Prove that a backup restores, and know how long it takes.

**Time** 30 minutes.
**Frequency** Quarterly, and after any change to backup configuration.
**Prerequisites** A recent `vzdump` archive. A free container ID. Enough free
space for a second copy of the guest.

---

## Why

**A backup you have never restored is not a backup. It is a hope with a
filename.**

Backups fail silently and in ways that only appear at restore time: a job that
has been erroring for six weeks, an archive that is truncated, a database that
was mid-write, a guest that boots with an empty schema. Every one of those looks
completely fine from the backup log.

The drill also produces a number you should have before you need it: **how long
does recovery take?** That is the first question anyone asks during an outage,
and "I do not know" is a bad answer.

---

## Before you start

Open a text file. You are going to write down times and observations as you go.
The record is half the point of the exercise.

```
DRILL: 2026-08-11
Guest:
Archive date:
Archive size:
Start:
```

---

## 1 · Pick a guest

**Rotate.** Do not restore the easy one every time. Over a year, cover:

- the one with a database (Vaultwarden, Pterodactyl panel)
- the one with the most data
- the one you understand least
- the one you would miss most

Note which you picked and why.

---

## 2 · Find the archive

```bash
pvesm list backup
ls -lh /var/lib/vz/dump/

# check the archive is not truncated, WITHOUT extracting it
zstd -t /var/lib/vz/dump/vzdump-lxc-102-2026_08_11-03_15_01.tar.zst
```

Record the archive's date and size. **If the newest archive is older than the
schedule says it should be, the drill has already found something** and that is
a successful drill.

---

## 3 · Restore to a NEW id, with networking off

```bash
pct restore 999 /var/lib/vz/dump/vzdump-lxc-102-2026_08_11-03_15_01.tar.zst \
    --storage local-lvm \
    --hostname restore-test \
    --start 0
```

**A new ID, never `--force` over the original.** `--force` turns a test into an
outage if the archive is bad.

**Networking off until you have changed the address.** The restored guest has
the same IP as the original. Two hosts with one address is its own kind of bad
day, and it happens the instant you start it.

```bash
pct set 999 --net0 name=eth0,bridge=vmbr0,ip=192.168.178.250/24,gw=192.168.178.1
pct start 999
```

Note the time the restore itself took.

---

## 4 · Verify it actually works

This is the step that matters and the step people skip.

```bash
pct enter 999

systemctl --failed
df -h
docker ps                          # if it is a Docker host
docker compose -f /opt/*/docker-compose.yml ps
```

Then check the **data**, not just the process:

| Guest type | The check that proves it |
|---|---|
| Vaultwarden | open the web vault, log in, **read an actual password** |
| a database | `psql -c "SELECT count(*) FROM users;"` — a real row count |
| a file server | open a file you recognise and check its contents |
| a game panel | log in, see the server list, look at a console |
| a web service | load a page that requires the database, not the login page |

**"It booted" is not verification.** A database can start with an empty schema.
An application can start with its configuration missing. People have trusted
broken backups for years on the strength of a guest that booted.

Write down what you checked and what you saw.

---

## 5 · Record the numbers

```
Archive size:        4.2 GB
Restore command:     6 min
Boot to service up:  1 min
Data verified:       12 min
TOTAL:               19 min
Problems found:      -
```

**Total recovery time is the number to remember.** It is what you will be asked
during a real outage, and it is what tells you whether the backup strategy is
adequate for the service.

---

## 6 · Clean up

```bash
pct stop 999
pct destroy 999
```

Check the space came back:

```bash
lvs -o +data_percent
```

---

## 7 · Write down what you learned

Even when it went perfectly. Especially the things that were not in this
runbook: a step you had to look up, a password you could not find, a
dependency you had forgotten about.

Add those to this file. That is how a runbook stops being aspirational.

---

## Also drill this, once a year

**Restoring to a different node.** Proves the archive is not silently dependent
on P1's storage configuration.

```bash
# copy the archive to another node, then restore there
scp /var/lib/vz/dump/vzdump-lxc-102-*.tar.zst root@192.168.178.50:/var/lib/vz/dump/
ssh root@192.168.178.50 'pct restore 999 /var/lib/vz/dump/vzdump-lxc-102-*.tar.zst --storage local-lvm --start 0'
```

**Restoring a single file** without restoring the guest:

```bash
tar --zstd -tvf vzdump-lxc-102-*.tar.zst | grep nginx.conf
tar --zstd -xvf vzdump-lxc-102-*.tar.zst ./etc/nginx/nginx.conf
```

**Rebuilding from the runbooks instead of from a backup.** Pick a service, do
not restore it, and rebuild it from
[`runbooks/`](.) and [`compose/`](../compose/) alone. That is the real test of
whether this repository does what it claims.

---

## Drill log

| Date | Guest | Archive | Total | Problems found |
|---|---|---|---|---|
| | | | | |

Fill this in. An empty table after a year is the finding.
