# Runbook 27 · An AI agent with least privilege

**Goal** An AI agent that can read and change the lab through its own narrow
accounts, proposes every change as a Git pull request, and applies a change only
after a human merged it.

**Time** An evening.
**Prerequisites** A Proxmox cluster, a GitHub account, Telegram. Root on one
Proxmox node (for the setup only).
**Reverses cleanly?** Yes. Every access is its own and revokes on its own, see *Undo*.

Architecture and the reasoning: [docs/26](../docs/26-ai-agent-devops.md).

---

## 0 · The shape of it

```
 you (Telegram / browser) ──> agent VM ──SSH user "openclaw"──> chosen containers
                                  │ ──API token, narrow role──> Proxmox
                                  │ ──own accounts──────────> app APIs (game panels, proxy, ...)
                                  └──fine-grained token────> GitHub: PRs to a private config repo
 you merge the PR ──> a watcher notices ──> the agent applies exactly the written plan
```

Three rules make it safe, and they are worth deciding before anything is installed:

1. **Its own identity everywhere.** Never your accounts. Every key revocable alone.
2. **Proposes, never decides.** Every change is a PR with a written plan. Merge is
   the approval.
3. **Reports, never fixes on its own.** A finding is written down and waits for an answer.

---

## 1 · A VM for the agent

A VM, not an LXC: the agent runs a shell with your keys in it, and a VM keeps a
mistake (or worse) away from the node's kernel.

- Ubuntu Server LTS, **2-4 vCPU, 4-6 GB RAM, 30 GB disk** is plenty. The heavy
  thinking happens at the model provider; the VM runs shells, Git and SSH.
  (Some checks, like starting a throwaway Grafana, want 1-2 GB free in `/tmp`.)
- Static LAN address (here `192.168.178.91`). **No port forward from the internet.**
- Include it in your backups: it holds the keys and the agent's memory.

---

## 2 · Install the agent runtime

This lab uses [OpenClaw](https://docs.openclaw.ai). Follow its installer for
Linux, then connect:

- **a model** (an API key of your model provider),
- **a chat channel** for your phone. For Telegram: create a bot with @BotFather
  **for the agent** (a different bot from any alert bot), and connect it as
  described in the OpenClaw channel docs,
- the **web Control UI**, which stays on the LAN.

From here on, you talk to the agent in the chat.

---

## 3 · An SSH key that only works from the agent VM

On the agent VM, as the agent's user:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/openclaw_homelab -N "" -C "openclaw@agent-vm"
cat ~/.ssh/openclaw_homelab.pub
```

That public key is what you install below, always prefixed with
`from="<agent VM address>"`, so a stolen copy of the private key is useless from
anywhere else.

---

## 4 · A user `openclaw` in each machine it may manage

Choose deliberately. Here: the Docker host (LXC 102), the Pi, and the three
game-hosting containers in the DMZ. **Not** the Proxmox nodes.

**Containers** (as root on the node that hosts them; change the IDs and the key):

```bash
KEY='from="192.168.178.91" ssh-ed25519 AAAA...your-public-key... openclaw@agent-vm'
for id in 102; do echo "== $id"; pct exec $id -- bash -s -- "$KEY" <<'EOF'
set -e
KEY="$1"
(command -v sudo && command -v sshd) >/dev/null || { apt-get update -qq && apt-get install -y -qq sudo openssh-server; }
id openclaw >/dev/null 2>&1 || useradd -m -s /bin/bash openclaw
getent group docker >/dev/null && usermod -aG docker openclaw
install -d -m 700 -o openclaw -g openclaw /home/openclaw/.ssh
echo "$KEY" > /home/openclaw/.ssh/authorized_keys
chown openclaw:openclaw /home/openclaw/.ssh/authorized_keys; chmod 600 /home/openclaw/.ssh/authorized_keys
echo 'openclaw ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/openclaw; chmod 440 /etc/sudoers.d/openclaw
systemctl enable --now ssh 2>/dev/null || true
echo OK
EOF
done
```

**A Raspberry Pi or other plain host:** the same lines without `pct exec`.

Be clear about what this grants: **`sudo` and the `docker` group are root inside
that machine.** There is no "manage Docker but not root". The limit is the
machine: an unprivileged container, or the Pi. If a machine needs less, give
less (no sudo, no docker group, a narrower `sudoers` line).

Then from the agent VM, for each machine:

```bash
ssh -i ~/.ssh/openclaw_homelab -o IdentitiesOnly=yes openclaw@192.168.178.87 'hostname; sudo -n true && echo sudo-ok'
```

Put each host into `~/.ssh/config` with `IdentityFile ~/.ssh/openclaw_homelab`
and `IdentitiesOnly yes`, so the right key is always used.

---

## 5 · A narrow Proxmox role instead of a node shell

Root on a Proxmox node is root over every guest and every disk. The API covers
what the agent needs. As root on one node:

```bash
pveum role add OpenClaw -privs "VM.Audit VM.PowerMgmt VM.Snapshot VM.Snapshot.Rollback Datastore.Audit Sys.Audit Pool.Audit SDN.Audit"
pveum user add openclaw@pve --comment "AI agent"
pveum acl modify / -user openclaw@pve -role OpenClaw
pveum user token add openclaw@pve agent --privsep 0      # prints the secret ONCE
```

It can see everything, start and stop guests, and take and roll back snapshots
(the undo button before risky changes). It **cannot** create or delete guests,
or touch disks, networks, firewalls, storage, users or permissions.

Leave out `VM.PowerMgmt` and `VM.Snapshot.Rollback` if you want a purely
read-and-snapshot agent.

---

## 6 · Application accounts: its own, and as small as works

For every app the agent should manage, an account of its own, never yours:

| App | Account | Keep it small by |
|---|---|---|
| Pterodactyl | a normal user, added as **subuser** on chosen servers | ticking only the permissions it needs; client API key with **Allowed IPs** = the agent VM |
| AMP | its own user and role | a role with only what it needs (this lab chose broad, and says so) |
| Nginx Proxy Manager | a non-admin user | "manage" for proxy hosts only; certificates "view" |
| anything with read-only tokens (WUD, ...) | read-only token | |

Secrets go to **one folder on the agent VM, one file per system, mode 600**:

```bash
install -d -m 700 ~/.config/homelab
printf 'PVE_HOST=192.168.178.20\nPVE_TOKEN_ID=openclaw@pve!agent\nPVE_TOKEN_SECRET=...\n' > ~/.config/homelab/proxmox.env
chmod 600 ~/.config/homelab/*.env
```

**How to hand a secret to the agent without a chat:** a password pasted into a
chat is in the chat history and at the model provider; treat it as leaked. Put
it into the file yourself (over SSH, or `read -rsp "secret: " S; ... "$S" ...` in
a shell on the target machine) and tell the agent the file name.

---

## 7 · GitHub: a private config repository and a token

1. **A private repository** (here `homelab-ops`) that mirrors the real config
   files at their real paths:

   ```
   hosts/<machine>/<real/path/on/the/machine>
   changes/YYYY-MM-DD-name.md        one change note per PR
   REPORTS.md                        findings, each with an empty "Answer:" line
   scripts/check-secrets.sh          the secret scanner (copy it from this repository)
   ```

   Ask the agent for the first PR: a **read-only snapshot** of the configs as they
   run today, scrubbed of secrets. Every later change then has a "before".

2. **A fine-grained personal access token** (GitHub → Settings → Developer
   settings) for **only the repositories it should work on**, with *Contents:
   read/write* and *Pull requests: read/write*. Add *Workflows* only if it should
   edit CI files.

3. **Protect `main`** in each repository (Settings → Branches → *require a pull
   request before merging*). Then "never merge, never push to main" is a lock,
   not only a rule. (If findings go straight to `main` like here, allow that one
   path, or send `REPORTS.md` through PRs too.)

4. **Commits are authored as you.** Set the agent VM's `git config --global
   user.name/user.email` to yours, and tell the agent never to add
   `Co-authored-by` lines. You are accountable for what you merge.

5. **Install the scanner as a hook** in every clone on the agent VM:
   `./scripts/check-secrets.sh --install`.

---

## 8 · The standing rules

Write them into the agent's long-term memory (OpenClaw: `MEMORY.md` /
`AGENTS.md` in its workspace) in your own words. This lab's, short form:

```text
- NEVER change anything in the homelab unless I explicitly asked for that specific thing.
  Findings = report only (REPORTS.md), then wait.
- ALWAYS ask before anything dangerous or big: deleting, restarting nodes/services,
  firewall/network changes, migrations. Read-only checks are fine.
- Work via PRs on both repos. Never push to main, never merge. Exception: REPORTS.md.
- MERGE = APPLY: apply only what the merged PR's change note says. Back up first.
- Every change gets changes/YYYY-MM-DD-name.md: What / Where / Apply / Verify / Undo / Result.
- Least privilege for your access, minimal effort for me. Explain infra in simple terms.
- Never commit secrets. Never print them. Never ask me to paste them into chat.
- Commit as me. No agent as author or co-author.
```

---

## 9 · The merge-watcher

An automation that checks GitHub every 2 minutes **with a script** and only wakes
the agent when a PR was merged. While nothing is merged, it costs nothing.

`watch-merges.js` (an OpenClaw condition script; adapt the repository name):

```javascript
// Fire only for PRs merged since the last check. Read-only: actions belong in the payload.
const res = await exec({ command: "gh pr list -R OWNER/homelab-ops --state merged --limit 10 --json number,mergedAt,title" });
const prs = JSON.parse(String(res?.aggregated ?? "[]"));
const seen = new Set(trigger.state?.seen ?? prs.map(p => p.number));   // first run: remember, don't fire
const fresh = prs.filter(p => !seen.has(p.number));
json({
  fire: fresh.length > 0,
  message: fresh.map(p => `PR #${p.number} merged: ${p.title}`).join("\n"),
  state: { seen: [...new Set([...seen, ...prs.map(p => p.number)])].slice(-50) },
});
```

```bash
openclaw automations add \
  --name "merge-watcher" \
  --every 2m \
  --trigger-script ./watch-merges.js \
  --message "A PR was merged. Apply exactly what its change note says (back up, apply, verify), then report the result."
```

Two lessons from running it:

- **Only one applier per PR.** If you also tell the agent "I merged it, apply it",
  the watcher and the agent may both apply. Let the change note say who applies
  ("by the watcher" / "by the agent, needs secrets"), and have the applier check
  for backup files of a previous apply before starting.
- **Check the PR state before pushing to it.** A PR merged a minute ago is gone;
  a push to its branch never reaches `main`.

---

## 10 · First test

1. Ask: *"Check which Proxmox guests are running and how full the storages are.
   Read-only."* It should answer from the API, change nothing.
2. Ask for a harmless change, e.g. a new tile in your dashboard. You get a PR with
   a change note.
3. Read the diff, merge. Within ~2 minutes the watcher wakes the agent, it applies,
   verifies, and reports in the chat.
4. Ask it to check its own access: *"List every system you can reach and with
   which rights."* The answer should match what you set up, and nothing more.

---

## If it goes wrong

| Symptom | Cause |
|---|---|
| `Permission denied (publickey)` to a host | the key isn't chosen: `IdentityFile` + `IdentitiesOnly yes` in `~/.ssh/config`, or the `from=` address is wrong |
| the agent "can't" do something in Proxmox | the role lacks it, as intended; decide if it should |
| a change was applied twice | two appliers; see step 9 |
| a secret ended up in Git | rewrite history (`git filter-repo`), force-push, **rotate the secret**; on GitHub, old PR refs keep it until GitHub Support purges them |
| the agent did something you didn't ask for | tighten the standing rules (step 8), and review what its keys allow |

---

## Undo

```bash
# each machine
userdel -r openclaw; rm -f /etc/sudoers.d/openclaw
# any Proxmox node
pveum user delete openclaw@pve; pveum role delete OpenClaw
```

Then: delete its app users (panels, proxy), revoke its GitHub token, delete its
chat bot in @BotFather, and delete the agent VM (or keep its backup).
