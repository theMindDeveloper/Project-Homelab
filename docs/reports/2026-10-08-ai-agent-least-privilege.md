# An AI agent in the homelab, with least privilege

**Date** 8 October 2026
**Author** TheMindDev
**Scope** Giving an AI agent (OpenClaw, running on VM 103 `agents`) access to the
lab so it can do the editing work, without handing it the keys to everything,
and putting every change it makes through Git
**Outcome** Access is live, read-only checks are done, and the Git workflow is set up.
No change to the lab has been applied yet.

> **Redaction.** No tokens, no public addresses. The SSH key below is the
> *public* half, which is safe to publish by design. Same rule as always,
> [`docs/99-security-notes.md`](../99-security-notes.md).

---

## 1 · What I wanted

I was tired of going down the rabbit hole every time something in the lab needed
editing. I wanted the agent to do that work, with three conditions:

1. **Least privilege.** It gets what it needs, not root on everything.
2. **Every change in Git,** with a PR I can read before anything happens.
3. **It never changes anything I didn't ask for.** Findings get reported, not fixed.

## 2 · The access model

The agent gets **its own identity everywhere**: never my account, never root on a
Proxmox node.

| Where | How | What it can do | What it cannot do |
|---|---|---|---|
| LXC 102 `docker`, the Pi | own user `openclaw`, own SSH key, sudo inside that machine | manage Docker, edit configs on that one machine | touch any other machine |
| Proxmox cluster | API token `openclaw@pve!agent`, custom role `OpenClaw` | see everything, start/stop guests, take and roll back snapshots | create or delete guests, change disks, network or firewall, users or permissions |
| pve / pve2 / pve3 shells | **none** | none | none |
| OPNsense, NAS, FRITZ!Box | **none** (for now) | none | none |
| GitHub | fine-grained token | branches and PRs | merge for me. Merging is my decision. |

Why no node shell: root on a Proxmox node can delete any guest, wipe disks and
reach into every container. The API token covers what the agent needs without
that.

Why one SSH key: one key is easy to audit and to revoke. It is restricted with
`from="192.168.178.91"`, so it only works from the agent's VM. A stolen copy is
useless anywhere else.

## 3 · The exact commands

**Containers.** Run as root on the node that hosts them (`pve` for 101/102/108,
`pve2` for 100/105/106/107). Change the ID list at the top:

```bash
for id in 102; do echo "== $id"; pct exec $id -- bash -s <<'EOF'
set -e
(command -v sudo && command -v sshd) >/dev/null || { apt-get update -qq && apt-get install -y -qq sudo openssh-server; }
id openclaw >/dev/null 2>&1 || useradd -m -s /bin/bash openclaw
getent group docker >/dev/null && usermod -aG docker openclaw
install -d -m 700 -o openclaw -g openclaw /home/openclaw/.ssh
echo 'from="192.168.178.91" ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJqgcNSwbiyhWSijOVgY0o7uGUR2HXluPlEuvBLAT2iF openclaw@vm103-agents' > /home/openclaw/.ssh/authorized_keys
chown openclaw:openclaw /home/openclaw/.ssh/authorized_keys; chmod 600 /home/openclaw/.ssh/authorized_keys
echo 'openclaw ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/openclaw; chmod 440 /etc/sudoers.d/openclaw
systemctl enable --now ssh 2>/dev/null || true
echo OK
EOF
done
```

**The Pi.** Run as `dietpi`. Same idea, without `pct`. The `from=` restriction is only
added when the Pi runs OpenSSH:

```bash
sudo bash -c 'set -e; id openclaw >/dev/null 2>&1 || useradd -m -s /bin/bash openclaw; usermod -aG docker openclaw; install -d -m 700 -o openclaw -g openclaw /home/openclaw/.ssh; K="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIJqgcNSwbiyhWSijOVgY0o7uGUR2HXluPlEuvBLAT2iF openclaw@vm103-agents"; pgrep -x sshd >/dev/null && K="from=\"192.168.178.91\" $K"; echo "$K" > /home/openclaw/.ssh/authorized_keys; chown openclaw:openclaw /home/openclaw/.ssh/authorized_keys; chmod 600 /home/openclaw/.ssh/authorized_keys; echo "openclaw ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/openclaw; chmod 440 /etc/sudoers.d/openclaw; echo OK-pi'
```

**Proxmox API.** Run as root on `pve`. It prints the token secret once:

```bash
pveum role add OpenClaw -privs "VM.Audit VM.PowerMgmt VM.Snapshot VM.Snapshot.Rollback Datastore.Audit Sys.Audit Pool.Audit SDN.Audit"
pveum user add openclaw@pve --comment "OpenClaw agent"
pveum acl modify / -user openclaw@pve -role OpenClaw
pveum user token add openclaw@pve agent --privsep 0
```

**Taking it all back:**

```bash
# in each container / on the Pi
userdel -r openclaw; rm /etc/sudoers.d/openclaw
# on any Proxmox node
pveum user delete openclaw@pve; pveum role delete OpenClaw
```

Plus: revoke the GitHub token in GitHub's settings.

### Honest notes on the privileges

- **Docker access is root-equivalent inside that machine.** There is no way to
  "manage Docker but not be admin". The blast radius is one unprivileged container.
- **`VM.Snapshot.Rollback`** can throw away recent changes on a guest. It's there
  because snapshots are the undo button, and rollbacks still need my OK.
- The GitHub token covers all my repositories. That was my choice. The agent only
  touches a repository when asked.

## 4 · Everything through Git

Git doesn't store machines. It stores the **config files** they run with, and
that is enough to see every change and undo it.

- A **private** repo (`homelab-ops`) holds the real config files, at their real
  paths: `hosts/lxc102/opt/glance/config/glance.yml` is
  `/opt/glance/config/glance.yml` on LXC 102. It stays private because it
  contains exact live configs.
- The first PR was a read-only **snapshot of the lab as it runs**, so every
  later change has a "before".
- **Every PR carries a change note** (`changes/YYYY-MM-DD-name.md`): what, where,
  the exact apply commands, how to verify, how to undo, and the result.
- **Merging a PR is the approval to apply it.** A watcher polls for merged PRs
  every two minutes. That costs nothing while idle, and the agent only wakes up
  when there is a merge. The agent then applies exactly what the change note
  says, backs up first, verifies, and reports.
- **Findings go into `REPORTS.md`**, numbered, each with an empty *Answer* line.
  Nothing in it gets fixed until I answer.
- **No AI in the contributor list.** Every commit is authored as me. No agent
  identity, no `Co-authored-by` trailers.
- Things that are safe to publish come back to this public repo as a separate
  PR. This report is the first one.

## 5 · What it found on the first look (read-only)

The first look already paid for itself:

- 🔴 **No backups exist.** There are no backup jobs and no backup files anywhere.
  The nightly job in [`docs/07`](../07-backup-and-recovery.md) is not actually
  running.
- 🟠 **AdGuard has no login.** Anyone on the LAN could change DNS for the house.
  *Update 2026-10-09: fixed. AdGuard now has a login, plus a separate user for
  the exporter, and locks out after 5 wrong tries. The steps are in
  [runbook 03](../../runbooks/03-adguard-home-dns.md#5--verify).*
- 🟡 **The NAS is `.79`.** The NFS storage points there, which settles the
  `.49`/`.79` disagreement in these docs.
- 🟡 **`check-secrets.sh` doesn't block in pre-commit mode.** Findings are
  counted inside a pipe subshell, so the count is lost. CI (`--all`) is unaffected.
- ✅ The temporary `10.10.10.254` address is gone from `vmbr1`.

None of these were changed. They're waiting for a decision.

## 6 · What I learned

- **Least privilege is a design choice, not a setting.** The agent's power is
  the sum of the keys you hand it. Three narrow keys beat one wide one.
- **"Merge = apply" only works with a written plan per change.** The change note
  is what makes a merge safe to automate.
- **An agent that only reports is still useful.** The biggest finding of the
  day, no backups, needed nobody to change anything to be found.

## 7 · Later the same day: the game managers

The agent can now manage the game servers through their own APIs, instead of poking at files.

**AMP.** I created a user `openclaw` in the AMP web UI (Configuration → User
Management) and gave it its own role. I kept the role broad on purpose
(settings, instance manager, file manager, instances). The agent logs in
through AMP's HTTP API.

**Pterodactyl.** The agent set this up itself, from inside the panel
container. It took a database backup first:

```bash
cd /opt/pterodactyl-panel
sudo -u www-data php artisan p:user:make --email=openclaw@theminddev.com \
  --username=openclaw --name-first=Open --name-last=Claw --admin=0
```

Then, in `php artisan tinker`, it added that user as a **subuser** on each
server with only `websocket.connect`, `control.*` (console, start, stop,
restart), `file.*` and `backup.*`, and created an account API key limited to
`192.168.178.91`.

The check that matters: with that key, the client API lists both servers,
and the admin API (`/api/application/...`) answers **403**. The agent can
run the games but cannot administer the panel.

**Undo:** delete the `openclaw` user in Pterodactyl (Admin → Users) and in AMP
(User Management).

---

**See also:** [`docs/99` · security notes](../99-security-notes.md) ·
[`docs/11` · hardening](../11-hardening.md) · [the wiki](../) ·
[repository root](../../README.md)
