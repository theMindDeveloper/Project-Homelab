# Runbook 18 · Reconfigure Pterodactyl after an address change

**Goal** Panel and wings talking to each other again, the live console working,
and every game server bound to the right address, after the guests moved.

**Time** 20 minutes.
**Prerequisites** Panel and wings both running and reachable from each other.
The new addresses decided.
**Reverses cleanly?** Yes, if you took the database backup in step 0. Without
it, the allocation edits are not cleanly reversible.

Background on why there are four places to change is in
[`docs/20-game-server-hosting.md`](../docs/20-game-server-hosting.md).

---

## The four places, and the order to fix them

**Fix them in this order.** Number 1 generates number 2, so fixing 2 first means
fixing it twice.

| # | Setting | Where | Controls |
|---|---|---|---|
| 1 | `APP_URL` | panel `.env` | what the panel generates links **and wings configs** from |
| 2 | `remote:` | wings `config.yml` | wings talking to the panel |
| 3 | node `fqdn` | panel database | **the browser** talking to wings, for the console websocket |
| 4 | allocations | panel database | the address a game server binds to |

Values used in this lab:

| # | Value |
|---|---|
| 1 | `http://10.10.10.22` |
| 2 | `http://10.10.10.22` |
| 3 | `10.10.10.20` |
| 4 | `10.10.10.20:<port>` |

---

## 0 · Back up the database first

Steps 3 and 4 write directly to it.

```bash
pct exec 106 -- bash -c 'source /opt/pterodactyl-panel/.env; \
  mysqldump -u$DB_USERNAME -p$DB_PASSWORD $DB_DATABASE > /root/panel-backup-$(date +%F).sql'
pct exec 106 -- ls -lh /root/panel-backup-*.sql
```

*`-p$VAR` puts the password in the process list for the life of the command, so
anyone able to run `ps` on that container can read it. Inside a single-purpose
container this is a shrug; on a shared host use `--defaults-extra-file` with a
`0600` credentials file instead.*

---

## 1 · `APP_URL` on the panel

**Note the real path.** The panel lives at `/opt/pterodactyl-panel`, with
`/var/www/pterodactyl` symlinked to it. Editing through the symlink appears to
work and silently does nothing useful in some tooling.

```bash
pct exec 106 -- sed -i 's|^APP_URL=.*|APP_URL=http://10.10.10.22|' /opt/pterodactyl-panel/.env
pct exec 106 -- grep APP_URL /opt/pterodactyl-panel/.env
```

Clear the cached config. **Run artisan as the web user, never as root:**

```bash
pct exec 106 -- sudo -u www-data php /opt/pterodactyl-panel/artisan config:clear
pct exec 106 -- sudo -u www-data php /opt/pterodactyl-panel/artisan cache:clear
```

> **Fix the source of a generated value, not just the generated copy.** While
> `APP_URL` pointed at the old address, every `wings configure` obediently
> handed wings an address that the firewall refused.

---

## 2 · `remote:` in the wings config

```bash
pct exec 105 -- sed -i "s|^remote:.*|remote: 'http://10.10.10.22'|" /etc/pterodactyl/config.yml
pct exec 105 -- systemctl restart wings
pct exec 105 -- systemctl status wings --no-pager
```

Alternatively, re-run `wings configure` with a token from the panel, which is
safe now that step 1 is correct.

---

## 3 · The node FQDN

This is the address **your browser** uses to reach wings for the live console.
The console does not go browser → panel → wings; the browser opens a websocket
straight to wings.

Admin → Nodes → your node → Configuration → FQDN. **Prefer the UI here.** The
direct equivalent, if you need it, is below, and `id = 1` is this lab's node ID,
not necessarily yours:

```sql
SELECT id, name, fqdn FROM nodes;          -- find YOUR node id first
UPDATE nodes SET fqdn = "10.10.10.20" WHERE id = 1;
```

---

## 4 · `allowed_origins`, or every console returns 403

**Symptom.** Console spinner, *"We're having some trouble connecting to your
server"*. In the wings log:

```
websocket: request origin not allowed by Upgrader.CheckOrigin   status=403
```

followed by a Go stack trace that looks like a crash. It is not: that is the
recovery middleware logging a rejected request.

**Cause.** The browser's websocket carries an `Origin` header naming the page it
came from. wings checks it against `allowed_origins`. With that list empty,
wings trusts only the panel URL it already knows and rejects everything else.

**Fix.** In `/etc/pterodactyl/config.yml`, **replace** the existing key:

```yaml
allowed_origins: ["http://192.168.178.60:8080", "http://10.10.10.22"]
```

```bash
pct exec 105 -- systemctl restart wings
```

**Two traps:**

1. The key already exists as an empty list. **Adding** a second one creates a
   YAML duplicate key that resolves unpredictably. It must be replaced, not
   appended.
2. Use flow style with square brackets. It sidesteps the indentation problems
   that block-style lists invite when editing with `sed`.

> **Standing rule: whenever the address used to reach the panel changes, add it
> to `allowed_origins`, or every console will 403.**

---

## 5 · Allocations

**A server belongs permanently to a node. There is no move button**, so do not
try to solve this by creating a new node: that means new UUIDs, manually copying
volume directories under `/var/lib/pterodactyl/volumes/<uuid>`, and losing
databases, schedules, users and subusers.

Try the admin UI first: Admin → Nodes → Allocations, create allocations on the
new address, then assign them per server.

If the dropdown returns **"No results found"** despite the allocations existing
and the node being correct, edit the database. In this lab that was most likely
a caching artefact compounded by the panel's 500 errors at the time.

> **These IDs are from this lab's database and are examples, not a recipe.**
> `1001`, `1002`, `1003`, `id = 1` and `id = 3` are the allocation, server and
> node IDs *in my panel*. Running them unchanged against a different Pterodactyl
> install will reassign the wrong allocations to the wrong servers. Read your own
> IDs first, and only then write:
>
> ```sql
> SELECT id, node_id, ip, port, server_id FROM allocations ORDER BY id;
> SELECT id, name, node_id, allocation_id FROM servers;
> SELECT id, name, fqdn FROM nodes;
> ```
>
> Take the `mysqldump` above before any of this. There is no undo.

```sql
-- point allocations at the right servers
UPDATE allocations SET server_id = 1 WHERE id IN (1001, 1002);
UPDATE allocations SET server_id = 3 WHERE id = 1003;

-- point each server at its primary allocation
UPDATE servers SET allocation_id = 1001 WHERE id = 1;
UPDATE servers SET allocation_id = 1003 WHERE id = 3;

-- release the stale ones
UPDATE allocations SET server_id = NULL WHERE id IN (1, 2, 3);
```

Then clear the cache again and restart wings.

---

## 6 · Reconcile the memory limits

If the container's memory cap changed during the move, every per-server limit in
the panel has to change to match.

Admin → Servers → *server* → Build Configuration → Memory.

> Container 105 was trimmed to 6 GB while the panel still allocated 12 GiB to
> Zomboid. The game grew past 6 GB, the cgroup limit fired, and the process died
> with **exit code 137**. Two limits that disagree means the lower one wins,
> silently and violently.

---

## Verify

```bash
# 1 · wings is running and not erroring
pct exec 105 -- systemctl status wings --no-pager
pct exec 105 -- journalctl -u wings -n 30 --no-pager

# 2 · wings can reach the panel
pct exec 105 -- timeout 5 curl -s -o /dev/null -w 'panel=%{http_code}\n' http://10.10.10.22

# 3 · the wings API answers
pct exec 105 -- timeout 5 curl -s -o /dev/null -w 'wings=%{http_code}\n' http://10.10.10.20:9090
```

4. In the panel, the node shows a **green** heartbeat, not "Node unavailable".
5. Start a server. It reaches Running.
6. **Open the live console.** No spinner, no 403. This is the test that catches
   `allowed_origins`, and nothing else does.
7. Join the game from an external client.

---

## If it goes wrong

| Symptom | Cause | Fix |
|---|---|---|
| Console spinner, "trouble connecting" | `allowed_origins` rejects the browser | step 4 |
| Node shows unavailable | `remote:` wrong, or wings cannot reach the panel | steps 1 and 2 |
| Panel 500, `Permission denied` on cache | artisan was run as root | `chown -R www-data:www-data /opt/pterodactyl-panel/storage /opt/pterodactyl-panel/bootstrap/cache`, restart apache2 |
| `wings configure` keeps writing the old address | `APP_URL` still wrong | step 1, then reconfigure |
| Allocation dropdown empty | stale cache | clear cache, or edit the database |
| Server starts then dies, code 137 | panel memory limit above the container cap | step 6 |
| Edits to `.env` have no effect | edited through the `/var/www` symlink | use `/opt/pterodactyl-panel/.env` |

---

## Undo

```bash
pct exec 106 -- bash -c 'source /opt/pterodactyl-panel/.env; \
  mysql -u$DB_USERNAME -p$DB_PASSWORD $DB_DATABASE < /root/panel-backup-<date>.sql'
```

Then revert `APP_URL`, `remote:` and `allowed_origins` to their previous values
and restart both services.

---

**Back to:** [the runbook index](README.md) ·
[`docs/20 · game server hosting`](../docs/20-game-server-hosting.md)
