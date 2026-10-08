<div align="center">

# Reports

**Dated write-ups of changes that were large enough to have a story.**

</div>

---

A third kind of page, alongside [`docs/`](../) and [`runbooks/`](../../runbooks/):

| | [`docs/`](../) | [`runbooks/`](../../runbooks/) | `reports/` |
|---|---|---|---|
| Answers | *what is this and why* | *how do I do it* | *what happened, and what it cost* |
| Ages | slowly | slowly | **never**, it is dated |
| Rewritten when | understanding improves | the procedure changes | never |

The wiki and the runbooks are kept current. A report is a snapshot and stays
wrong on purpose once the lab moves on, because its value is the record of what
was true at the time, what broke, and what was decided.

Every report includes the problems hit, the verification actually run, and an
honest assessment of what is still weak. The limitations sections are not
modesty; they are the parts that are load-bearing when something breaks.

---

## The reports

| Date | Report | Summary |
|---|---|---|
| 2026-08-13 | [DMZ migration](2026-08-13-dmz-migration.md) | isolating internet-facing game servers from the house LAN using a software DMZ on Proxmox |
| 2026-09-11 | [Privacy update](2026-09-11-privacy-update.md) | encrypted upstream DNS (Quad9 over DoH/DoT) and qBittorrent on the NAS only through Mullvad via gluetun |
| 2026-10-08 | [AI agent with least privilege](2026-10-08-ai-agent-least-privilege.md) | giving an AI agent its own narrow access (per-machine user, limited Proxmox API role), and putting every change through Git PRs where a merge is the approval to apply |
| 2026-10-08 | [Monitoring, security logs and alerting](2026-10-08-monitoring-security-alerting.md) | every machine, the router and the game servers monitored; firewall and website logs with locations; CrowdSec watching; four generated dashboards; 19 alert rules to Telegram, and the sixteen things that broke on the way |

---

## Redaction

Reports follow the same rule as the rest of the repository:

> **Publish the design. Never publish the reachability.**

Public addresses and externally forwarded port numbers appear as placeholders.
Internal RFC1918 addressing appears in full, because it is useless to anyone
outside the network and the design is unintelligible without it. See
[`docs/99-security-notes.md`](../99-security-notes.md).

---

**Back to:** [the wiki](../) · [repository root](../../README.md)
