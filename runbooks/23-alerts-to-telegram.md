# Runbook 23 · Alerts to Telegram

**Goal** Grafana sends a short Telegram message when something in the lab breaks
(and when it is fine again), quiet at night for non-urgent things.

**Time** 30 minutes.
**Prerequisites** [Runbook 10](10-monitoring-stack.md) (Prometheus + Grafana),
ideally [21](21-logs-and-crowdsec.md) (some rules use Loki). A Telegram account.
**Reverses cleanly?** Yes: remove the alerting files and restart Grafana.

Concepts, every rule, and the traps: [docs/24](../docs/24-alerting.md).

---

## 1 · Create your own bot (2 minutes, in Telegram)

1. Open a chat with **@BotFather** (the official one, blue tick).
2. Send `/newbot`.
3. Name: anything, e.g. `Homelab Alerts`.
4. Username: must end in `bot`, e.g. `myhomelab_alerts_bot`.
5. BotFather replies with a **token** like `123456789:AAH...`. Keep it secret: it
   lets anyone post as this bot. (If it leaks: `/revoke` in BotFather.)
6. Open your new bot and send it **any message**, e.g. `hi`. A bot may only
   write to people who wrote to it first.

---

## 2 · Find your chat ID

```bash
curl -s "https://api.telegram.org/bot<TOKEN>/getUpdates" | python3 -m json.tool | grep -A3 '"chat"'
```

The number after `"id":` is your chat ID. Empty result: send the bot another
message and run it again.

Send yourself a test right away, so you know token and ID are right before
Grafana is involved:

```bash
curl -s "https://api.telegram.org/bot<TOKEN>/sendMessage" -d chat_id=<CHAT_ID> -d text="test from the lab"
```

---

## 3 · Put both into `alerting.env`

On LXC 102, in `/opt/monitoring`:

```bash
cat > alerting.env <<'EOF'
TELEGRAM_BOT_TOKEN=123456789:AAH...
TELEGRAM_CHAT_ID=123456789
EOF
chmod 600 alerting.env
```

The compose file passes it to Grafana (`env_file: alerting.env`), and
`contact-points.yml` uses `${TELEGRAM_BOT_TOKEN}` / `${TELEGRAM_CHAT_ID}`. The
token is never written into a config file or into Git.

---

## 4 · The alerting files

In `/opt/monitoring/grafana/provisioning/alerting/`
([in this repository](../compose/monitoring/grafana/provisioning/alerting/)):

| File | What it says | Edit? |
|---|---|---|
| `contact-points.yml` | two Telegram receivers on the same bot: `telegram` (with "OK again" messages) and `telegram-games` (without) | rarely |
| `policies.yml` | critical and 🎮 → any time; warning → muted 23:00-08:00 Europe/Berlin; group per alert and node; repeat every 4 h | quiet hours, timezone |
| `templates.yml` | the message: emoji, one bold line, one explanation, a link | to taste |
| `rules.yml` | the 19 rules. **Generated**, don't edit by hand | via `gen_alerts.py` |

### Adapt the rules to your lab

Rules are written in [`scripts/grafana/gen_alerts.py`](../scripts/grafana/gen_alerts.py).
Read it once; each rule is one call with its query, message and `for`. Things
that are specific to this lab and that you will want to change:

- `node!~"pve2|pve3"` in "Host down" and `node=~"pve2|pve3"` in "Power-saving node off":
  those two nodes are switched off on purpose, so they get a soft 🟠 "is off" instead of 🔴.
  Use your own names, or remove both.
- `id!="lxc/101"` in "Guest with autostart stopped": one guest excluded on
  purpose. Remove it or put your own (with a comment saying why).
- `node="pve2"` in "OPNsense stopped sending logs": the node the firewall runs on.
- thresholds (80 / 90 %, 85 °C) and `for` times.

Then:

```bash
python3 scripts/grafana/gen_alerts.py          # writes rules.yml
# copy rules.yml to /opt/monitoring/grafana/provisioning/alerting/ on LXC 102
```

**Before going live, test every rule's query against your data** and load the
files into a throwaway Grafana: [runbook 26](26-test-grafana-changes-safely.md).
A broken alerting file can stop Grafana from starting.

---

## 5 · Load it

```bash
cd /opt/monitoring && docker compose -p stacks up -d grafana   # picks up alerting.env
docker restart stacks-grafana-1                                # re-reads the alerting files
docker logs stacks-grafana-1 2>&1 | grep -E "provision alerting|level=error" | tail -5
```

You want `finished to provision alerting` and no error about alerting.

---

## 6 · Verify

In Grafana:

1. **Alerting → Alert rules**: three folders of rules (critical, warning, games),
   all **Normal** (green). A rule in *Firing* right after deploying means its
   query already returns 1 today: check it before it pages you every 4 hours.
2. **Alerting → Contact points → `telegram` → Test**: a test message arrives.
3. **Alerting → Notification policies**: the three routes, the *night* mute timing.

A real end-to-end test: reboot the Raspberry Pi. About 2 minutes later:
"🔴 pi is DOWN" (and "🔴 AdGuard DNS on the Pi is DOWN", the Pi carries DNS),
then "✅ OK again" for both once it is back.

---

## 7 · Living with it

- **Before planned maintenance:** *Alerting → Silences → New silence*, matcher
  e.g. `node = pi`, duration 1 h. Better than disabling a rule and forgetting it.
- **An alert that is always wrong:** fix the rule (in `gen_alerts.py`), don't
  mute the chat. A muted chat also mutes the real 🔴.
- **Rules are read-only in the UI** on purpose. A change is: edit
  `gen_alerts.py`, regenerate, test, copy, restart Grafana.

---

## If it goes wrong

| Symptom | Cause |
|---|---|
| Grafana does not start after adding the files | a syntax error in an alerting file; `docker logs stacks-grafana-1`, remove the file, fix, retry. Test in a throwaway Grafana first (runbook 26) |
| test message: "chat not found" | wrong chat ID, or you never wrote to the bot |
| test message: "Unauthorized" | wrong token, or `alerting.env` not loaded (`docker compose up -d grafana`, not just restart, after creating it) |
| rule shows "Error", message about `$$A` | `$$` written in a rule file: alert-rule files take `$A` literally, only contact points expand variables |
| a rule never fires in a test | the query lacks `bool` (`< 1` instead of `< bool 1`), see docs/24 |
| "internet down" when only the exporter died | `or vector(0)` in that rule, see docs/24 |
| a rule fires (Alerting shows it) but no Telegram message; Grafana log says 400 "Unsupported start tag" | a `<` or `&` in the alert text (Telegram HTML). The generator refuses them now |
| messages every evening for a switched-off node | exclude it from "Host down" and gate its guests on its `up`, see docs/24 |

---

## Undo

```bash
rm -r /opt/monitoring/grafana/provisioning/alerting
docker restart stacks-grafana-1
```

In Telegram: `/deletebot` in @BotFather.
