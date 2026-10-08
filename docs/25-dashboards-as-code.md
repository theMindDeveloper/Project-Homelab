# Dashboards as code

**The four Grafana dashboards are not built by clicking. A Python script writes
them.** This page explains why, how the script is organised, how to change a
dashboard, and the Grafana behaviours that cost an evening to understand.

Code: [`scripts/grafana/`](../scripts/grafana/). What the dashboards show:
[docs/08](08-monitoring.md#the-four-dashboards).

---

## Why generate dashboards

A Grafana dashboard is a JSON document. A real one is 2,000-6,000 lines of
JSON, most of it positions, colours and defaults. Clicking one together works
until the second change:

| Clicking | Generating |
|---|---|
| a change is a hunt through panel menus | a change is a few lines of Python |
| the change is invisible in Git ("dashboard.json: 1,400 lines changed") | the diff is the change ("threshold 0.8 → 0.9") |
| ten panels drift into ten slightly different colour schemes | one helper, one look |
| a query fix is repeated in every panel that uses it | a query lives once, in `queries.py` |
| a rebuilt Grafana is empty until someone clicks again | `gen_all.py`, done |

The cost: a dashboard cannot be "just quickly fixed" in the UI. Provisioned
dashboards are read-only there (`allowUiUpdates: false`). That is the point.

---

## How the code is organised

| File | What it is |
|---|---|
| [`lib.py`](../scripts/grafana/lib.py) | the building blocks: a `Dash` class with one method per panel type (`stat`, `gauge`, `bargauge`, `ts` for time series, `table`, `pie`, `logs`, `state_timeline`, `geomap`), colours, thresholds, the link bar |
| [`queries.py`](../scripts/grafana/queries.py) | query fragments used in several places: "internet traffic only", "game traffic", "failed SSH", the port → game name table |
| `gen_overview.py`, `gen_hosts.py`, `gen_games.py`, `gen_security.py` (+ `gen_security_details.py`) | one file per dashboard |
| [`gen_all.py`](../scripts/grafana/gen_all.py) | runs all four and writes the JSON into `compose/monitoring/grafana/dashboards/` |
| [`gen_alerts.py`](../scripts/grafana/gen_alerts.py) | the alert rules, same idea, writes `rules.yml` |

A panel is one call:

```python
D.row("Nodes")
D.bargauge("CPU", [P('1 - avg by (node) (rate(node_cpu_seconds_total{job="proxmox-host",mode="idle"}[5m]))',
                     legend="{{node}}", instant=True)],
           0, 6, 6, mode="lcd", links=host_link())
#          x  w  h   -> column 0, 6 of 24 columns wide, 6 rows high
```

The layout is a grid 24 columns wide. Each call places a panel at a column and
width in the current row; `D.next_row(h)` moves down.

Only Python's standard library is used. No Grafana SDK, no `pip install`.

---

## Changing a dashboard

```bash
$EDITOR scripts/grafana/gen_hosts.py      # change something
python3 scripts/grafana/gen_all.py        # writes the JSON
git diff --stat                           # what changed
# copy the JSON to the Grafana host's dashboards folder; Grafana reloads in ~10 s
```

Before it goes live, three checks, each of which caught real mistakes here
([runbook 26](../runbooks/26-test-grafana-changes-safely.md) has the commands):

1. **Run every query** of the dashboard against the live Prometheus and Loki
   APIs. Errors are bugs; empty results need a reason (often "this data only
   exists while a game runs").
2. **Check that no panels overlap** (a small script over the `gridPos` values).
3. **Load it into a throwaway Grafana** if anything structural changed.

**The generated JSON is not committed in this public repository**, because the
Games dashboard contains this lab's game ports (never published, see
[docs/99](99-security-notes.md)). `queries.py` here has example ports; put your
own in and run the generator.

---

## The Grafana traps

### Loki "top N" bar charts collapse into one bar

A Loki *instant* query like `topk(12, sum by (country) (count_over_time(...)))`
reaches Grafana as **one table** with a row per country. Prometheus returns one
*series* per country. Bar gauges and pie charts by default reduce each series to
one value, so with Loki the whole table became **one bar** ("65", no country
names).

Fix: for Loki-fed bar gauges and pies, show every row:

```json
"reduceOptions": {"values": true, "fields": "/^Value/", "calcs": ["lastNotNull"]}
```

`lib.py` does this automatically when a panel's query is a Loki query.

### The default map needs an API key

Grafana's default basemap (CARTO) now draws "API KEY REQUIRED" over the whole
map. Use a tile layer that needs no key: `osm-standard`, or an XYZ layer with
ESRI's free dark tiles (what `lib.py` uses):

```
https://services.arcgisonline.com/arcgis/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}
```

### Every number three times

The first Proxmox dashboard showed every gauge three times. Prometheus asked
pve-exporter for the *whole cluster* once per node, so every guest existed three
times, with a different `instance` label each. The fix is in `prometheus.yml`
(cluster data from one node only), but the dashboards are also written to
survive duplicates: `max by (id) (...)` before every join, so a duplicate can
never multiply a row.

### Joining a name onto a number

pve-exporter reports `pve_cpu_usage_ratio{id="lxc/102"}` without a name; the name
is in a separate "info" metric. The join:

```promql
max by (id, name, node, type) (
  max by (id) (pve_cpu_usage_ratio)
  * on (id) group_left(name, node, type)
  max by (id, name, node, type) (pve_guest_info{template="0"})
)
```

`gen_overview.py` wraps this in a small `J()` helper so every guest panel uses it
the same way.

### Several queries in one table

A table with one column per query (state, CPU, RAM, uptime, ...) needs each query
as `format: table`, then the transformations **merge** (one row per guest) and
**organize** (rename `Value #A` → "State", order the columns). `lib.table()`
builds that from a list of `(field, title, unit, thresholds, cell style)`.

### Clicking a node opens its details

The node bars on the Overview open the Hosts dashboard on that node. The link is
a **data link** on the field, `/d/homelab-hosts?var-host=${__field.labels.node}`.
It must sit in `fieldConfig.defaults.links`; a panel link (`panel.links`) cannot
see the field's labels and opens the dashboard with an empty selection.

### Folded sections

The Security dashboard's "Details ·" sections are collapsed rows. In the JSON a
collapsed row **contains** its panels (`row.panels`), and its position is only
one grid line; Grafana pushes the rest down when you unfold it. `lib.py` handles
this with `D.row(title, collapsed=True)`.

### A switch at the top

The Hosts dashboard's host switch is a *custom variable* with a fixed list
(`pve, pve2, pve3, pi, nas`) rather than a query, so the order is fixed and a
switched-off node is still in the list. Every query uses `node="$host"`.

---

## Provisioning details

```yaml
# compose/monitoring/grafana/provisioning/dashboards/homelab.yml
providers:
  - name: homelab
    folder: Homelab
    type: file
    disableDeletion: false   # delete a JSON file -> Grafana deletes that dashboard
    allowUiUpdates: false    # no UI edits; the generator is the source
    options:
      path: /var/lib/grafana/dashboards
```

- Grafana re-reads the JSON files by itself every few seconds; no restart.
- Changing the **provider** file (e.g. `disableDeletion`) needs one Grafana restart.
- Data sources are referenced by a fixed **uid** (`prometheus-homelab`,
  `loki-homelab`), set in the data source files, so the dashboards don't depend
  on whatever Grafana would generate.

---

**Back to:** [08 · Monitoring](08-monitoring.md)
