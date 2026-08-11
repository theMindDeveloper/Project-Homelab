# Scripts

Small, single-purpose, no dependencies beyond what is already on a Proxmox node
or a Debian container. Each one has its usage in the header; run it with
`--help`.

| Script | Runs on | What it is for |
|---|---|---|
| [`check-secrets.sh`](check-secrets.sh) | any machine with the repo | Blocks a commit that contains anything private. Install it as a hook once and forget it. |
| [`new-lxc.sh`](new-lxc.sh) | a Proxmox node, as root | Creates an unprivileged Debian LXC with the same settings every time. |
| [`install-docker.sh`](install-docker.sh) | inside a fresh Debian LXC, as root | Docker Engine plus the Compose plugin, from Docker's own repository, with log rotation configured. |
| [`backup-all.sh`](backup-all.sh) | a Proxmox node, as root | `vzdump` every guest with retention and a readable summary. Built for cron. |
| [`health-check.sh`](health-check.sh) | anywhere on the LAN | Checks every address in the inventory. Exits non-zero if anything is down. |

## First thing to run

```bash
./scripts/check-secrets.sh --install
```

That writes `.git/hooks/pre-commit`. From then on every `git commit` is scanned
and a commit containing a public IP, an IPv6 host address, a MAC address, a
tunnel UUID, a private key or a token-shaped string is refused.

Test that it works before trusting it:

```bash
echo "my public ip is 203.0.113.99" > /tmp/leak.md && cp /tmp/leak.md ./leak.md
git add leak.md && git commit -m "should fail"     # expect: blocked
git reset leak.md && rm leak.md
```

## Why these are shell scripts and not Ansible

Because there are five of them and they run on three machines. Ansible is the
right answer at the point where provisioning is repeated often enough that
"it worked when I ran it" stops being good enough, and moving to it is on the
list in the README. Writing 400 lines of YAML to do what `pct create` does in
one command would be cargo cult, not automation.

The honest version of that: these scripts are *consistency*, not
*infrastructure as code*. They make every container come out the same. They do
not make the lab reproducible from a git checkout, and the difference matters.
