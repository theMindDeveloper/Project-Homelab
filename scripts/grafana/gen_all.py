#!/usr/bin/env python3
"""Regenerate all homelab Grafana dashboards. Run from anywhere: python3 scripts/grafana/gen_all.py"""
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
out = os.path.join(here, "..", "..", "compose", "monitoring", "grafana", "dashboards")
import gen_overview, gen_hosts, gen_security, gen_games
for mod, name in ((gen_overview, "homelab-overview.json"), (gen_security, "homelab-security.json"),
                  (gen_hosts, "homelab-hosts.json"),
                  (gen_games, "homelab-games.json")):
    n = mod.build(os.path.join(out, name))
    print(f"{name}: {n} panels")
