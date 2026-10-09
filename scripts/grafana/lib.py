"""Tiny helpers to build Grafana dashboard JSON. Used by the gen_*.py scripts next to this file.
Run: python3 scripts/grafana/gen_all.py   (writes into hosts/lxc102/opt/monitoring/grafana/dashboards/)"""
import json

PROM = {"type": "prometheus", "uid": "prometheus-homelab"}
LOKI = {"type": "loki", "uid": "loki-homelab"}

# Colours (Grafana palette names) used everywhere, so the dashboards look like one family.
GOOD, WARN, BAD, INFO, NEUTRAL = "green", "orange", "red", "blue", "text"
GAME_C, WEB_C, BLOCK_C = "#5794F2", "#FF9830", "#F2495C"

def thr(*steps):
    """thr("green", 0.75, "orange", 0.9, "red") -> Grafana thresholds."""
    s = [{"color": steps[0], "value": None}]
    for i in range(1, len(steps), 2):
        s.append({"color": steps[i + 1], "value": steps[i]})
    return {"mode": "absolute", "steps": s}

PCT = thr(GOOD, 0.75, WARN, 0.9, BAD)
TEMP = thr(GOOD, 70, WARN, 85, BAD)


def _reduce(targets, rows=None):
    """Loki instant queries come back as ONE table (a row per label set), Prometheus as one series per label set.
    Bar gauges/pies must then show every row ("values": True), or they collapse into a single bar."""
    if rows is None:
        rows = any(t["datasource"]["type"] == "loki" for t in targets)
    return {"calcs": ["lastNotNull"], "fields": "/^Value/" if rows else "", "values": bool(rows)}


class Dash:
    def __init__(self, title, uid, tags, links=(), refresh="1m", time_from="now-24h", desc=""):
        self.d = {"title": title, "uid": uid, "tags": list(tags), "timezone": "browser", "editable": False,
                  "refresh": refresh, "time": {"from": time_from, "to": "now"}, "schemaVersion": 41,
                  "graphTooltip": 1, "panels": [], "templating": {"list": []}, "annotations": {"list": []},
                  "description": desc, "links": list(links)}
        self.y = 0
        self._id = 0
        self._open_row = None

    # ---- layout ---------------------------------------------------------------
    def _add(self, p, x, w, h):
        self._id += 1
        p["id"] = self._id
        p["gridPos"] = {"x": x, "y": self.y, "w": w, "h": h}
        (self._open_row["panels"] if self._open_row else self.d["panels"]).append(p)
        return p

    def next_row(self, h):
        self.y += h

    def row(self, title, collapsed=False):
        """collapsed=True: a fold-out section; the panels added after it live inside it until the next row()."""
        if self._open_row:                      # close the previous fold-out: next row sits right below it
            self.y = self._open_row["gridPos"]["y"] + 1
            self._open_row = None
        self._id += 1
        r = {"type": "row", "title": title, "id": self._id, "collapsed": collapsed,
             "gridPos": {"h": 1, "w": 24, "x": 0, "y": self.y}, "panels": []}
        self.d["panels"].append(r)
        self.y += 1
        if collapsed:
            self._open_row = r

    def var_custom(self, name, label, values, current):
        self.d["templating"]["list"].append({
            "type": "custom", "name": name, "label": label, "query": ",".join(values),
            "options": [{"text": v, "value": v, "selected": v == current} for v in values],
            "current": {"text": current, "value": current}, "multi": False, "includeAll": False,
            "hide": 0, "skipUrlSync": False})

    def save(self, path):
        if self._open_row:
            self._open_row = None
        with open(path, "w") as f:
            json.dump(self.d, f, indent=2)
            f.write("\n")
        return sum(len(p.get("panels", [])) if p["type"] == "row" else 1 for p in self.d["panels"])

    # ---- queries ----------------------------------------------------------------
    @staticmethod
    def prom(expr, legend="", ref="A", instant=False, fmt=None):
        t = {"refId": ref, "datasource": PROM, "expr": expr, "legendFormat": legend}
        if instant:
            t.update(instant=True, range=False)
        if fmt:
            t["format"] = fmt
        return t

    @staticmethod
    def loki(expr, legend="", ref="A", instant=False):
        t = {"refId": ref, "datasource": LOKI, "expr": expr, "queryType": "instant" if instant else "range"}
        if legend:
            t["legendFormat"] = legend
        return t

    # ---- panels -----------------------------------------------------------------
    def stat(self, title, targets, x, w, h=4, unit="none", th=None, desc="", decimals=None, graph=False,
             color_mode="background", mappings=None, text_mode="value", links=None):
        d = {"unit": unit, "thresholds": th or thr(INFO), "color": {"mode": "thresholds"}}
        if decimals is not None:
            d["decimals"] = decimals
        if mappings:
            d["mappings"] = mappings
        if links:
            d["links"] = links          # data links: may use ${__field.labels.*}
        p = {"type": "stat", "title": title, "description": desc, "datasource": targets[0]["datasource"],
             "targets": targets, "fieldConfig": {"defaults": d, "overrides": []},
             "options": {"colorMode": color_mode, "graphMode": "area" if graph else "none", "justifyMode": "center",
                         "textMode": text_mode, "wideLayout": True, "showPercentChange": False,
                         "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}}}
        return self._add(p, x, w, h)

    def gauge(self, title, targets, x, w, h=6, unit="percentunit", th=PCT, mn=0, mx=1, desc="", decimals=1):
        return self._add({"type": "gauge", "title": title, "description": desc, "datasource": targets[0]["datasource"],
                          "targets": targets,
                          "fieldConfig": {"defaults": {"unit": unit, "min": mn, "max": mx, "decimals": decimals,
                                                       "thresholds": th, "color": {"mode": "thresholds"}}, "overrides": []},
                          "options": {"showThresholdMarkers": True, "showThresholdLabels": False, "minVizHeight": 75,
                                      "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}}},
                         x, w, h)

    def bargauge(self, title, targets, x, w, h, unit="percentunit", th=PCT, mn=0, mx=1, desc="", mode="gradient",
                 orientation="horizontal", decimals=None, color=None, rows=None, links=None):
        d = {"unit": unit, "min": mn, "thresholds": th, "color": color or {"mode": "thresholds"}}
        if links:
            d["links"] = links
        if mx is not None:
            d["max"] = mx
        if decimals is not None:
            d["decimals"] = decimals
        return self._add({"type": "bargauge", "title": title, "description": desc,
                          "datasource": targets[0]["datasource"], "targets": targets,
                          "fieldConfig": {"defaults": d, "overrides": []},
                          "options": {"displayMode": mode, "orientation": orientation, "showUnfilled": True,
                                      "valueMode": "color", "namePlacement": "auto", "sizing": "auto",
                                      "minVizHeight": 16, "maxVizHeight": 300,
                                      "reduceOptions": _reduce(targets, rows)}},
                         x, w, h)

    def ts(self, title, targets, x, w, h=8, unit="none", th=None, mn=None, mx=None, desc="", stack=False,
           bars=False, overrides=None, legend="list", fill=15, calcs=("lastNotNull", "max")):
        custom = {"lineWidth": 2, "fillOpacity": 80 if bars else fill, "gradientMode": "opacity", "showPoints": "never",
                  "drawStyle": "bars" if bars else "line", "lineInterpolation": "smooth",
                  "stacking": {"mode": "normal" if stack else "none", "group": "A"},
                  "thresholdsStyle": {"mode": "line+area" if th else "off"}, "axisSoftMin": 0 if mn is None else mn}
        d = {"unit": unit, "custom": custom, "thresholds": th or thr(GOOD), "color": {"mode": "palette-classic"}}
        if mn is not None:
            d["min"] = mn
        if mx is not None:
            d["max"] = mx
        lg = {"displayMode": legend, "placement": "bottom" if legend == "list" else "right", "showLegend": True,
              "calcs": [] if legend == "list" else list(calcs)}
        return self._add({"type": "timeseries", "title": title, "description": desc,
                          "datasource": targets[0]["datasource"], "targets": targets,
                          "fieldConfig": {"defaults": d, "overrides": overrides or []},
                          "options": {"legend": lg, "tooltip": {"mode": "multi", "sort": "desc"}}},
                         x, w, h)

    def pie(self, title, targets, x, w, h=8, unit="none", desc="", overrides=None, donut=True, rows=None):
        return self._add({"type": "piechart", "title": title, "description": desc,
                          "datasource": targets[0]["datasource"], "targets": targets,
                          "fieldConfig": {"defaults": {"unit": unit, "color": {"mode": "palette-classic"}},
                                          "overrides": overrides or []},
                          "options": {"pieType": "donut" if donut else "pie", "displayLabels": ["percent"],
                                      "legend": {"displayMode": "table", "placement": "right", "showLegend": True,
                                                 "values": ["value", "percent"]},
                                      "tooltip": {"mode": "single"},
                                      "reduceOptions": _reduce(targets, rows)}},
                         x, w, h)

    def table(self, title, targets, x, w, h, cols, desc="", sort=None, merge=True, labels_to_fields=False,
              footer=False):
        """cols: list of (source field, display name, unit, thresholds|None, cell options|None, width|None)"""
        rename, order, overrides = {}, {}, []
        for i, c in enumerate(cols):
            src, name, unit, th, cell = c[:5]
            width = c[5] if len(c) > 5 else None
            fld = f"Value #{src}" if len(src) == 1 else src
            rename[fld] = name
            order[fld] = i
            props = [{"id": "unit", "value": unit}]
            if th:
                props.append({"id": "thresholds", "value": th})
            if cell:
                props.append({"id": "custom.cellOptions", "value": cell})
            if width:
                props.append({"id": "custom.width", "value": width})
            overrides.append({"matcher": {"id": "byName", "options": name}, "properties": props})
        tr = []
        if labels_to_fields:
            tr.append({"id": "labelsToFields", "options": {"mode": "columns"}})
        if merge:
            tr.append({"id": "merge", "options": {}})
        tr += [{"id": "organize", "options": {"excludeByName": {"Time": True}, "renameByName": rename, "indexByName": order}},
               {"id": "filterFieldsByName", "options": {"include": {"names": [c[1] for c in cols]}}}]
        return self._add({"type": "table", "title": title, "description": desc,
                          "datasource": targets[0]["datasource"], "targets": targets, "transformations": tr,
                          "fieldConfig": {"defaults": {"custom": {"align": "auto", "filterable": False,
                                                                  "cellOptions": {"type": "auto"}}},
                                          "overrides": overrides},
                          "options": {"showHeader": True, "cellHeight": "sm", "sortBy": sort or [],
                                      "footer": {"show": footer, "reducer": ["sum"], "fields": ""}}},
                         x, w, h)

    def logs(self, title, targets, x, w, h, desc=""):
        return self._add({"type": "logs", "title": title, "description": desc, "datasource": targets[0]["datasource"],
                          "targets": targets,
                          "options": {"showTime": True, "wrapLogMessage": True, "sortOrder": "Descending",
                                      "enableLogDetails": True, "dedupStrategy": "none", "prettifyLogMessage": False,
                                      "showLabels": False, "showCommonLabels": False}},
                         x, w, h)

    def state_timeline(self, title, targets, x, w, h, mappings, desc="", th=None):
        return self._add({"type": "state-timeline", "title": title, "description": desc,
                          "datasource": targets[0]["datasource"], "targets": targets,
                          "fieldConfig": {"defaults": {"mappings": mappings, "thresholds": th or thr(BAD, 1, GOOD),
                                                       "color": {"mode": "thresholds"},
                                                       "custom": {"fillOpacity": 85, "lineWidth": 0}},
                                          "overrides": []},
                          "options": {"showValue": "never", "mergeValues": True, "alignValue": "left", "rowHeight": 0.85,
                                      "legend": {"showLegend": False}, "tooltip": {"mode": "single"}}},
                         x, w, h)

    def geomap(self, title, targets, x, w, h, layers, desc="", transformations=None, overrides=None,
               view=None):
        return self._add({"type": "geomap", "title": title, "description": desc,
                          "datasource": targets[0]["datasource"], "targets": targets,
                          "transformations": transformations or [],
                          "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "thresholds": thr(INFO)},
                                          "overrides": overrides or []},
                          "options": {"view": view or {"id": "coords", "lat": 30, "lon": 10, "zoom": 1.6},
                                      "controls": {"showZoom": True, "mouseWheelZoom": True, "showAttribution": True,
                                                   "showScale": False, "showMeasure": False, "showDebug": False},
                                      "tooltip": {"mode": "details"},
                                      "basemap": DARK_BASEMAP, "layers": layers}},
                         x, w, h)

    def text(self, content, x, w, h, title=""):
        return self._add({"type": "text", "title": title, "options": {"mode": "markdown", "content": content},
                          "transparent": True}, x, w, h)


# Free dark map tiles, no API key (CARTO now needs one). ESRI "World Dark Gray Base".
DARK_BASEMAP = {"type": "xyz", "name": "Dark map (ESRI)", "config": {
    "url": "https://services.arcgisonline.com/arcgis/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}",
    "attribution": "Tiles © Esri — Esri, DeLorme, NAVTEQ"}}

BAR_CELL = {"type": "gauge", "mode": "lcd", "valueDisplayMode": "text"}
BAR_BASIC = {"type": "gauge", "mode": "basic", "valueDisplayMode": "text"}
BG_CELL = {"type": "color-background", "mode": "basic"}
TXT_CELL = {"type": "color-text"}

UPDOWN = [{"type": "value", "options": {"0": {"text": "DOWN", "color": BAD, "index": 0},
                                        "1": {"text": "UP", "color": GOOD, "index": 1}}}]

def dash_link(title, uid, icon="dashboard"):
    return {"title": title, "type": "link", "url": f"/d/{uid}", "icon": icon, "targetBlank": False,
            "keepTime": True, "includeVars": False, "asDropdown": False, "tags": [], "tooltip": ""}

NAV = [dash_link("Overview", "homelab-overview"), dash_link("Hosts", "homelab-hosts", "bolt"),
       dash_link("Games", "homelab-games", "play"), dash_link("Security", "homelab-security", "shield")]

def host_link(label_expr="${__field.labels.node}"):
    """Click a node's bar/tile -> open the Hosts dashboard on that node."""
    return [{"title": "Open in Hosts", "url": "/d/homelab-hosts?var-host=" + label_expr + "&${__url_time_range}"}]
