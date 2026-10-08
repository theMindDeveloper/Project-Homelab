#!/usr/bin/env python3
"""Test the generated dashboards and alert rules against the LIVE Prometheus and Loki, read-only.

For every panel query and every alert-rule query it reports:  ok / EMPTY / ERR
and it checks that no two panels overlap. Exit code 1 if any query errors or panels overlap.

  ERR    the query is wrong (syntax, unknown function, bad label matcher) -> fix it
  EMPTY  the query is valid but returns nothing right now -> needs a reason
         (e.g. "no game is running", "no failed SSH logins today")

Usage (Loki is usually only reachable on the Docker network, so run it there):
  docker run --rm --network stacks_default -v "$PWD":/w:ro python:3.13-alpine \
    python -I /w/scripts/grafana/check_dashboards.py \
      --prom http://prometheus:9090 --loki http://loki:3100 \
      /w/compose/monitoring/grafana/dashboards/*.json \
      --rules /w/compose/monitoring/grafana/provisioning/alerting/rules.yml

Only Python's standard library. Only GET requests to the query APIs.
"""
import argparse, json, sys, urllib.parse, urllib.request

RANGE, STEP = "6h", "5m"   # what $__range / $__auto / $__rate_interval are replaced with


def query(base, path, params):
    url = f"{base.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "check-dashboards/1"}), timeout=60) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode(errors='replace')[:160]}"
    except Exception as e:  # unreachable, timeout
        return None, f"{type(e).__name__}: {e}"
    if d.get("status") != "success":
        return None, str(d)[:160]
    return d["data"]["result"], None


def run(expr, ds, panel_type, prom, loki):
    expr = (expr.replace("$__range", RANGE).replace("$__auto", STEP).replace("$__rate_interval", STEP))
    if ds == "prometheus":
        return query(prom, "/api/v1/query", {"query": expr})
    if ds == "loki":
        if not loki:
            return [], "skipped (no --loki)"
        if panel_type == "logs":   # log queries (not metric queries) only work as range queries
            return query(loki, "/loki/api/v1/query_range", {"query": expr, "limit": 5, "since": RANGE})
        return query(loki, "/loki/api/v1/query", {"query": expr, "limit": 5})
    return [], f"skipped (data source {ds})"


def panels(ps):
    for p in ps:
        yield p
        yield from p.get("panels", [])   # panels inside folded rows


def overlaps(ps):
    """Overlap check per section: top level, and inside each folded row."""
    bad = []
    groups = [[p for p in ps]] + [p.get("panels", []) for p in ps if p.get("type") == "row"]
    for g in groups:
        cells = {}
        for p in g:
            gp = p["gridPos"]
            for x in range(gp["x"], gp["x"] + gp["w"]):
                for y in range(gp["y"], gp["y"] + gp["h"]):
                    if (x, y) in cells and cells[(x, y)] != p.get("title"):
                        bad.append((p.get("title"), cells[(x, y)]))
                    cells[(x, y)] = p.get("title")
            if gp["x"] + gp["w"] > 24:
                bad.append((p.get("title"), "wider than 24 columns"))
    return sorted(set(bad))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dashboards", nargs="*")
    ap.add_argument("--prom", required=True)
    ap.add_argument("--loki")
    ap.add_argument("--rules")
    ap.add_argument("--quiet", action="store_true", help="only print EMPTY and ERR")
    a = ap.parse_args()
    errors = empties = total = 0

    def report(where, title, ref, ds, ptype, expr):
        nonlocal errors, empties, total
        total += 1
        res, err = run(expr, ds, ptype, a.prom, a.loki)
        if err and not err.startswith("skipped"):
            errors += 1
            print(f"ERR    {where} | {title} [{ref}] | {err}")
        elif not res:
            empties += 1
            print(f"EMPTY  {where} | {title} [{ref}]" + (f"  ({err})" if err else ""))
        elif not a.quiet:
            print(f"ok     {where} | {title} [{ref}] n={len(res)}")

    for path in a.dashboards:
        d = json.load(open(path))
        name = d.get("title", path)
        # a custom variable (like the Hosts switch): test the queries once per value
        variables = {v["name"]: [o["value"] for o in v.get("options", [])] or [v.get("current", {}).get("value", "")]
                     for v in d.get("templating", {}).get("list", []) if v.get("type") == "custom"}
        combos = [{}] if not variables else [{k: val} for k, vals in variables.items() for val in vals]
        for combo in combos:
            where = name + "".join(f" [{k}={v}]" for k, v in combo.items())
            for p in panels(d["panels"]):
                for t in p.get("targets", []):
                    expr = t.get("expr", "")
                    for k, v in combo.items():
                        expr = expr.replace(f"${k}", v)
                    report(where, p.get("title"), t.get("refId"), t["datasource"]["type"], p.get("type"), expr)
        for title, other in overlaps(d["panels"]):
            errors += 1
            print(f"ERR    {name} | layout: '{title}' overlaps '{other}'")

    if a.rules:
        text = open(a.rules).read()
        doc = json.loads(text[text.index("{"):])          # rules.yml is JSON (valid YAML) after a comment line
        uids = {"prometheus-homelab": "prometheus", "loki-homelab": "loki"}
        for g in doc["groups"]:
            for r in g["rules"]:
                for q in r["data"]:
                    if q["datasourceUid"] in uids:
                        report("alert rule", r["title"], q["refId"], uids[q["datasourceUid"]], "", q["model"]["expr"])

    print(f"\n{total} queries: {errors} errors, {empties} empty")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
