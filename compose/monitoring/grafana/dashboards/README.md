# Dashboard JSON goes here

Grafana loads every `*.json` file in this folder into the **Homelab** folder
(provider: `../provisioning/dashboards/homelab.yml`).

The JSON files are **generated**, not edited by hand:

```bash
python3 scripts/grafana/gen_all.py   # writes homelab-overview/hosts/games/security.json
```

They are not committed here because the Games dashboard contains this lab's
game ports, and game ports are never published
([docs/99](../../../../docs/99-security-notes.md)). The generators are in
[`scripts/grafana/`](../../../../scripts/grafana/); fill in your own ports in
`queries.py` and run them. How and why: [docs/25](../../../../docs/25-dashboards-as-code.md).
