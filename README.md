# Hermes Watchdog — Proactive Monitoring & Early Intervention System

## Problem Statement

On 2026-07-07, a single long-running API call (~6 minutes) caused a complete session death:

```
User message → Agent blocked on API call #8 (367s) →
Context: 87% → 95% while blocked →
3-min inactivity warning (TOO LATE) →
5-min gateway timeout → SESSION DEAD
```

The 3-minute warning is a **canary in a coal mine** — by the time it fires, you're already in the death spiral. We need to catch failures at 60% context, or after 2 minutes of a slow tool call, not after 5 minutes of total silence.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         HERMES WATCHDOG                              │
│              Proactive Monitoring / Early Intervention               │
└─────────────────────────────────────────────────────────────────────┘

  LAYER 1: DETECTION          LAYER 2: DECISION           LAYER 3: ACTION
  ─────────────────           ─────────────────           ─────────────────
  • Context % monitor        • Threshold engine          • Telegram alert
  • Tool call timer          • Alert level calc          • State dump
  • Heartbeat pings          • Intervention rules        • Context backup
  • Session health check     • Cooldown tracker          • Session rescue
                              
                              
  LAYER 4: RECOVERY           LAYER 5: COCKPIT (GitHub)
  ─────────────────           ──────────────────────────
  • Graceful handoff         • Watchdog repo (this)
  • State restoration        • GitHub Actions (scheduled)
  • Resumable context        • Issue dashboard
  • Alert acknowledgement    • Status page (GitHub Pages)
```

### Detection Signals (Watched Continuously)

| Signal | Normal | Warning | Critical | Action |
|--------|--------|---------|----------|--------|
| Context usage | < 50% | 50–65% | 65–80% | Alert + dump |
| Tool call duration | < 60s | 60–120s | 120s+ | Probe + alert |
| Time since last agent activity | < 90s | 90–150s | 150s+ | Full干预 |
| Heartbeat (GitHub Actions) | every 5 min | missed 1 | missed 2+ | Alert + restart |
| Telegram response latency | < 30s | 30–60s | 60s+ | Investigate |

### Decision Engine

```
IF context_usage > 50% AND < 65%:
    → WARN: Increase logging frequency, begin state dumping
    → TELEGRAM: "Context at {X}% — monitoring closely"
    
IF context_usage > 65% OR tool_call_duration > 120s:
    → ALERT: Fire Telegram warning immediately
    → DUMP: Save full session state to GitHub
    → BACKUP: Push context snapshot to hermes-watchdog/snapshots/
    
IF context_usage > 80% OR (no_activity > 150s AND tool_call_active):
    → CRITICAL: Trigger session rescue
    → ACTION: /reset signal, restore from latest snapshot
    → TELEGRAM: "CRITICAL — session rescue triggered"
    
IF GitHub Actions missed 2+ heartbeats:
    → CRITICAL: Sandbox may be down
    → ACTION: Create GitHub Issue with label `watchdog-critical`
```

---

## Repository Structure

```
hermes-watchdog/
├── README.md                          ← You are here
├── ARCHITECTURE.md                    ← Deep dive on each layer
├── PHASES.md                         ← Implementation roadmap
│
├── .github/
│   └── workflows/
│       ├── heartbeat.yml             ← 5-min heartbeat monitor
│       ├── context-monitor.yml        ← 2-min context checker
│       ├── watchdog-timer.yml         ← Tool call duration tracker
│       └── session-recovery.yml      ← Automated rescue actions
│
├── skills/
│   ├── watchdog-monitor/             ← In-agent monitoring skill
│   │   └── SKILL.md
│   └── watchdog-circuit-breaker/     ← Tool call circuit breaker
│       └── SKILL.md
│
├── src/
│   ├── health_check.py               ← Main health check script
│   ├── context_monitor.py            ← Context % + compaction watcher
│   ├── circuit_breaker.py            ← Tool call timeout tracker
│   ├── telegram_alerter.py           ← Telegram alerting module
│   ├── state_snapshotted.py          ← Session state dumper
│   ├── session_rescue.py             ← Rescue + restore logic
│   └── requirements.txt
│
├── configs/
│   ├── watchdog.yaml                 ← Thresholds + alert config
│   └── telegram_secrets.yaml         ← Telegram bot token (encrypted)
│
├── snapshots/                        ← Session state snapshots (gitignored)
│   └── README.md
│
├── docs/
│   ├── ALERT_THresholds.md
│   ├── TELEGRAM_ALERTS.md
│   └── RECOVERY_PLAYBOOK.md
│
└── INCIDENT_LOG.md                   ← Auto-updated incident history
```

---

## How It Works

### In-Agent Monitoring (Hermes Watchdog Skill)

The agent loads the `watchdog-monitor` skill at session start. It runs a lightweight co-routine that:

1. **Tracks context %** — samples every tool call completion, logs to local state
2. **Times each tool call** — if any call exceeds 90s, marks it as "slow" and increases monitoring frequency
3. **Maintains activity log** — records last agent activity timestamp
4. **Fires early warnings** — at 50%, 60%, 70% context thresholds

### GitHub Actions (External Layer)

Since MaxHermes is cloud-hosted and we can't run local cron, GitHub Actions provides the external heartbeat:

- **Every 5 min**: `heartbeat.yml` — checks if the agent is responding, creates an issue if not
- **Every 2 min**: `context-monitor.yml` — reads session state file, alerts on high context
- **On-demand**: `watchdog-timer.yml` — triggered by agent tool calls, tracks durations
- **On failure**: `session-recovery.yml` — backs up state, attempts recovery

### Telegram Alerting

Alerts fire at graduated levels:

```
🟡 WATCH (50% context): "Context at 52% — slowing growth"
🟠 WARN (65% context): "Context at 68% — backing up state, watch closely"
🔴 ALERT (80%+ or 2min stall): "CRITICAL — rescue sequence initiated"
⚠️  TOOL STALL (90s+ on one call): "Tool call stalled 90s — probing..."
```

---

## Key Design Decisions

### 1. External Monitoring via GitHub Actions

We cannot rely on local cron inside the sandbox (it gets wiped). GitHub Actions provides:
- Reliable 1-minute granularity scheduling
- Persistence across sandbox rebuilds
- Git-native logging and audit trail
- Issue creation for critical alerts
- Secrets management for Telegram tokens

### 2. Graduated Alert Levels

Instead of binary "alive/dead", we use 4 levels:
- **WATCH** — informational, no action needed
- **WARN** — increase monitoring, prepare for action
- **ALERT** — take action (dump state, notify)
- **CRITICAL** — full intervention (reset, rescue)

### 3. State Snapshots to GitHub

Every time we detect a warning condition, we snapshot the session state to `hermes-watchdog/snapshots/`. This means even if the session dies completely, we have the context to resume from.

### 4. Circuit Breaker Pattern for Tool Calls

The single biggest failure mode is a single blocking tool call (web search, content extraction) taking 6+ minutes. We wrap tool calls with a circuit breaker:
- Track start time of each tool call
- If call exceeds 90s, log a warning
- If call exceeds 150s, fire critical alert + attempt cancel
- Next tool call starts fresh; don't let one slow call poison the session

### 5. Cooldown to Prevent Alert Storms

Every alert level has a cooldown:
- WATCH: 5 min before next WATCH
- WARN: 3 min before next WARN
- ALERT: 10 min before next ALERT
- CRITICAL: 30 min cooldown (don't spam during active incident)

---

## Alert Routing

| Level | Telegram | GitHub Issue | GitHub Actions |
|-------|----------|--------------|----------------|
| WATCH | 🟡 Info | No | Log only |
| WARN | 🟠 Warning | No | Log + snapshot |
| ALERT | 🔴 Alert | Yes (label: watchdog-alert) | Snapshot + rescue |
| CRITICAL | 🚨 Critical | Yes (label: watchdog-critical) | Full recovery |

---

## Dependencies

- MaxHermes sandbox (cloud-hosted)
- Telegram bot (for alerts) — `@WatchdogHermesBot`
- GitHub repo: `andrebrassfield/hermes-watchdog`
- GitHub PAT with repo + issues permissions
- `urllib.request` + `json` (stdlib, no external deps)

---

## Phases

See [PHASES.md](./PHASES.md) for the full implementation roadmap.

---

*Built by Hermes + Dre — 2026-07-07*
