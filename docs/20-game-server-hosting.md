# Game server hosting internals: Pterodactyl and AMP

Moving the game stack into the DMZ broke both managers in ways that had nothing
to do with firewall rules. This page is what I learned about how they actually
work, written so the next address change is a five-minute job instead of an
evening.

---

## The two managers in this lab

| | Pterodactyl | AMP |
|---|---|---|
| Guests | LXC 106 (panel) and LXC 105 (wings) | LXC 107 |
| Architecture | split: a web panel and a separate daemon | single application, one instance per game |
| Games | Zomboid, Minecraft | Terraria, Space Engineers |
| Runs games as | Docker containers | managed processes |
| Licence | free, open source | commercial, **bound to a machine fingerprint** |
| Survived the move | no, four things needed changing | yes, zero internal changes |

The asymmetry is instructive and comes down to one design decision, covered
below.

---

## Pterodactyl: the four places an address is stored

This is the core lesson. A Pterodactyl deployment stores network addresses in
**four** independent places, and after moving the guests all four were wrong at
once.

| # | Setting | Where | What it controls |
|---|---|---|---|
| 1 | `APP_URL` | panel `.env` | what the panel generates links **and wings configs** from |
| 2 | `remote:` | wings `/etc/pterodactyl/config.yml` | wings talking to the panel |
| 3 | node `fqdn` | panel database / admin UI | **the browser** talking to wings, for the console websocket |
| 4 | allocations | panel database | the address a game server binds to |

Post-migration values in this lab:

| # | Value |
|---|---|
| 1 | `http://10.10.10.22` |
| 2 | `http://10.10.10.22` |
| 3 | `10.10.10.20` |
| 4 | `10.10.10.20:<port>` |

### Number 3 is the one that surprises people

The live console does **not** go browser → panel → wings. The browser opens a
websocket **directly to wings**. So the node's `fqdn` must be an address your
*browser* can reach, which is not necessarily an address the panel can reach.

In this lab both happen to be reachable from the house because of the static
route plus the floating pass rule. In a stricter setup they would differ, and
that is the case that breaks people's mental model.

### Fix the source, not the copy

`wings configure` fetches its configuration **from the panel**, and the panel
generates `remote:` from its own `APP_URL`. While `APP_URL` pointed at the old
address, every `wings configure` obediently handed wings an address the block
rule refused.

> **Fix the source of a generated value, not just the generated copy.**

```bash
# the panel lives at /opt/pterodactyl-panel, with /var/www/pterodactyl symlinked to it
pct exec 106 -- sed -i 's|^APP_URL=.*|APP_URL=http://10.10.10.22|' /opt/pterodactyl-panel/.env
```

The symlink is worth calling out: editing `/var/www/pterodactyl/.env` appears to
work and silently does nothing useful in some tooling. Always use the real path.

---

## `allowed_origins`, and the 403 that looks like a crash

**Symptom.** The server console shows a spinner and
*"We're having some trouble connecting to your server"*.

**In the wings log:**

```
websocket: request origin not allowed by Upgrader.CheckOrigin   status=403
```

followed by a long Go stack trace that looks like a crash and is not: that is
the recovery middleware logging a rejected request.

**Cause.** The browser's websocket to wings carries an `Origin` header naming
the page it came from. wings checks it against `allowed_origins`. With that list
empty, wings falls back to trusting only the panel URL it already knows, and
rejects anything else.

**Fix**, in `/etc/pterodactyl/config.yml`:

```yaml
allowed_origins: ["http://192.168.178.60:8080", "http://10.10.10.22"]
```

```bash
pct exec 105 -- systemctl restart wings
```

**Two traps in that one line:**

1. The key already exists as an empty list. **Adding** a second one creates a
   YAML duplicate key that resolves unpredictably. It has to be **replaced**.
2. Use flow style with square brackets. It sidesteps the indentation problem
   that block-style lists invite when you are editing with `sed`.

> **Standing rule: if the address used to reach the panel ever changes, add it
> to `allowed_origins`, or every console will 403.**

---

## Allocations, and why the node cannot be changed

**A server belongs permanently to a node. There is no move button.**

Creating a new node and recreating each server means new UUIDs, manually copying
volume directories under `/var/lib/pterodactyl/volumes/<uuid>`, and losing
databases, schedules, users and subusers, none of which follow.

So when the admin UI's allocation dropdown returned *"No results found"* despite
the allocations existing and the node being correct, editing the database
directly was strictly the safer option.

```bash
# ALWAYS back up first
pct exec 106 -- bash -c 'source /opt/pterodactyl-panel/.env; \
  mysqldump -u$DB_USERNAME -p$DB_PASSWORD $DB_DATABASE > /root/panel-backup-$(date +%F).sql'
```

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
UPDATE servers SET allocation_id = 1001 WHERE id = 1;
UPDATE servers SET allocation_id = 1003 WHERE id = 3;
UPDATE allocations SET server_id = NULL WHERE id IN (1, 2, 3);

-- the address the browser uses to reach wings
UPDATE nodes SET fqdn = "10.10.10.20" WHERE id = 1;
```

The root cause of the empty dropdown was never fully determined. It was most
likely a caching artefact compounded by the panel's 500 errors at the time.

---

## The 500 error caused by running `artisan` as root

**Symptom.**

```
file_put_contents(...): Failed to open stream: Permission denied
```

**Cause.** Running `php artisan ...` as root creates cache files under
`/opt/pterodactyl-panel/storage/framework/cache/` owned by root. Apache runs as
`www-data` and then cannot write to them.

**Fix:**

```bash
pct exec 106 -- chown -R www-data:www-data \
  /opt/pterodactyl-panel/storage /opt/pterodactyl-panel/bootstrap/cache
pct exec 106 -- systemctl restart apache2
```

**Prevention:** always run artisan as the web user.

```bash
sudo -u www-data php /opt/pterodactyl-panel/artisan <command>
```

---

## AMP, and why it needed nothing

AMP required **zero internal reconfiguration** after the move. Every AMP service
binds to `0.0.0.0`, meaning "every address this machine has", so it
automatically listened on whatever address the container ended up with.

That is the whole difference. Pterodactyl stores addresses; AMP binds to all of
them.

| Binding | Effect when the address changes |
|---|---|
| `0.0.0.0` | nothing to change; it follows the interface |
| a specific address | breaks, and must be reconfigured |

Worth remembering when configuring anything: binding to a specific address is a
security control (it limits which network can reach the service), and it is also
a thing that will break when addressing changes. In this lab the panel's MariaDB
and Redis bind to `127.0.0.1` deliberately, which is why moving the panel was
clean: nothing external depended on them.

---

## AMP and machine-bound licences

**Symptom, after the container moved to a different physical host:**

```
[Licencing Error/6] : Unable to load licence for AMP Professional Edition - NoMatchingMachineId
[Core Warning/10]   : Expected licence feature RunAMP is not present.
```

**Cause.** The licence is activated against a **machine fingerprint**. Moving
LXC 107 to a different physical node changed it.

Ruled out first, in this order: DNS resolved; HTTPS to the licence server
returned 200; both instances were stopped, so no concurrency limit applied. Only
then does the fingerprint explanation become the obvious one.

**Fix, once per instance:**

```bash
pct exec 107 -- su - amp -c "ampinstmgr reactivate <InstanceName>"
```

**Recurrence:** only if the container moves hosts again. Newly created instances
inherit the licence and are unaffected.

> **Generalisation: anything licensed to hardware is a migration hazard.**
> Add "reactivate the licence" to any runbook that moves a guest between nodes.

---

## Adding a new game server, now

The migration was a one-time cost. Ongoing work is three steps, roughly two
minutes:

1. **Panel:** create the server and pick a free allocation. Ports on
   `10.10.10.20` are pre-created for this.
2. **OPNsense:** one Destination NAT rule. Use the copy icon on an existing rule
   and change only the ports and the target.
3. **FRITZ!Box:** one share, attached to the OPNsense device entry.

Before the DMZ it was steps 1 and 3. **The entire ongoing cost of the whole
design is one extra click per game.**

Full procedure: [runbook 16](../runbooks/16-publish-a-game-server-port.md).

---

## Symptom index

| Symptom | Cause | Page |
|---|---|---|
| Console spinner, "trouble connecting" | `allowed_origins` rejects the browser | above |
| Panel 500, permission denied on cache | `artisan` run as root | above |
| wings cannot reach the panel | `APP_URL` still points at the old address | above |
| Allocation dropdown empty | stale cache; fix in the database | above |
| Game killed with exit code 137 | container memory cap below the panel's limit | [19](19-lxc-migration-and-resources.md#the-trap-this-creates) |
| AMP `NoMatchingMachineId` | licence fingerprint changed with the host | above |
| Game port open in a scanner but players cannot join | wrong protocol, TCP versus UDP | [13](13-addressing-and-osi-layers.md#ports) |

---

**Back to:** [the wiki index](README.md) ·
[the migration report](reports/2026-08-13-dmz-migration.md)
