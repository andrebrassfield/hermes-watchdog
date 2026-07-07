# Hermes Watchdog — Implementation Phases

## Priority Philosophy

Build the highest-impact, lowest-complexity pieces first. Each phase should be deployable independently and provide immediate value.

---

## Phase 0: Foundation (1–2 hours)

**Goal:** Get the monitoring infrastructure in place without changing agent behavior.

### Deliverables

- [ ] `hermes-watchdog` GitHub repo created
- [ ] `src/health_check.py` — basic health reporting script
- [ ] `.github/workflows/heartbeat.yml` — 5-min heartbeat workflow
- [ ] Telegram bot created (`@WatchdogHermesBot`)
- [ ] `configs/watchdog.yaml` — threshold configuration

### Verification

```bash
# Test: Heartbeat workflow runs, creates .heartbeat file
# Test: health_check.py outputs JSON status
# Test: Telegram bot responds to /start
```

### Skip Criteria

None — this is the foundation everything else builds on.

---

## Phase 1: In-Agent Context Monitor (2–3 hours)

**Goal:** Agent self-reports context usage and fires early warnings.

### Deliverables

- [ ] `skills/watchdog-monitor/SKILL.md` — monitoring skill
- [ ] `src/context_monitor.py` — context % tracker
- [ ] Phase 1 Telegram alerts at 50%, 65%, 80%
- [ ] State file: `~/.hermes/watchdog/state.jsonl`

### Implementation Steps

1. Create `watchdog-monitor` skill with context % sampling logic
2. Agent loads skill at session start
3. Every tool call: sample context %, append to state.jsonl
4. Every 30s idle: sample context %
5. At 50%: fire WATCH alert
6. At 65%: fire WARN alert + begin state snapshot
7. At 80%: fire ALERT + force snapshot to GitHub

### Verification

```
# Manual test:
1. Start agent session
2. Run many tool calls to fill context
3. Confirm Telegram alerts at 50%, 65%, 80%
4. Check state.jsonl is being written
```

---

## Phase 2: Tool Call Circuit Breaker (2–3 hours)

**Goal:** Prevent a single slow tool call from killing the session.

### Deliverables

- [ ] `skills/watchdog-circuit-breaker/SKILL.md`
- [ ] `src/circuit_breaker.py` — tool call timer
- [ ] Timeout at 90s (warn), 150s (kill alert), 180s (cancel)
- [ ] Tool timing log: `~/.hermes/watchdog/tool_timing.jsonl`

### Implementation Steps

1. Create circuit breaker skill
2. Wrap ALL tool calls with timing wrapper
3. At 90s: log slow call, increase monitoring
4. At 150s: fire ALERT + log full call details (redacted)
5. At 180s: attempt cancel, alert CRITICAL
6. Always allow next call to proceed

### Verification

```
# Manual test:
1. Mock a slow tool call (sleep 120s in test)
2. Confirm WATCH fires at 90s
3. Confirm ALERT fires at 150s
4. Confirm session survives (next call succeeds)
```

---

## Phase 3: GitHub Actions External Monitor (2–3 hours)

**Goal:** External heartbeat independent of agent, catches full stalls.

### Deliverables

- [ ] `.github/workflows/context-monitor.yml` — 2-min context check
- [ ] `.github/workflows/health-report.yml` — 15-min full report
- [ ] `src/external_monitor.py` — reads agent state, writes GitHub
- [ ] GitHub Issue creation on ALERT/CRITICAL

### Implementation Steps

1. `context-monitor.yml` runs every 2 min via cron
2. Reads `~/.hermes/watchdog/state.jsonl` (if accessible via runner)
3. Reads `.heartbeat` file in hermes-watchdog repo
4. If heartbeat stale 2+ times → create Issue (watchdog-critical)
5. If context > 80% from last known → create Issue (watchdog-alert)
6. `health-report.yml` runs every 15 min → posts to Issue thread

### Note on Runner Access

GitHub Actions runners run OUTSIDE the MaxHermes sandbox. They cannot directly read `~/.hermes/watchdog/`. Two solutions:

**Option A (Simple):** Agent writes state to a GitHub file
- Agent pushes `state.jsonl` to `hermes-watchdog/state/` every 5 min
- GitHub Actions reads from there

**Option B (MaxHermes API):** Use MaxHermes API if exposed
- Check if `agent.minimax.io` or similar exposes status endpoint
- Runner calls API instead of reading files

*Recommendation: Start with Option A. Simple, reliable, GitHub-native.*

---

## Phase 4: Automated Recovery (3–4 hours)

**Goal:** Session automatically rescues itself on critical failure.

### Deliverables

- [ ] `.github/workflows/session-recovery.yml`
- [ ] `src/session_rescue.py` — backup + restore logic
- [ ] `snapshots/` directory — state snapshots
- [ ] Recovery playbook in `docs/RECOVERY_PLAYBOOK.md`

### Implementation Steps

1. CRITICAL alert fires → GitHub Actions triggered
2. Actions reads latest snapshot from `snapshots/`
3. Creates rescue branch: `rescue/{session_id}`
4. Pushes emergency state dump
5. Sends /reset to agent via Telegram command
6. On restart: agent reads snapshot, offers to resume

### Recovery Flow

```
CRITICAL detected
    │
    ├─► Snapshot state to snapshots/{id}.json
    │
    ├─► Create GitHub Issue: watchdog-critical
    │
    ├─► Telegram: "CRITICAL — session rescue initiated"
    │
    ├─► Send /reset signal
    │
    └─► On restart:
            ├─► Read latest snapshot
            ├─► Report: "Session died at {context}%. Was working on {task}."
            ├─► Ask: "Resume from {checkpoint}?"
            └─► If yes: restore context from snapshot
```

---

## Phase 5: Observability Dashboard (2–3 hours)

**Goal:** Full visibility into agent health over time.

### Deliverables

- [ ] `docs/ALERT_THRESHOLDS.md` — threshold reference
- [ ] `docs/TELEGRAM_ALERTS.md` — alert format reference
- [ ] GitHub Pages status page (optional)
- [ ] `INCIDENT_LOG.md` — auto-updated incident history

### Metrics to Track

```
- Alert frequency (alerts per day/week)
- Mean time to alert (MTTA)
- Mean time to recovery (MTTR)
- Context % at time of alert
- Most common stall trigger (which tool call)
- Session survival rate
```

---

## Phase Dependencies

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5
  │                                              │
  │                                              │
  └──────────────────────────────────────────────┘
              (Phase 3 needs Phase 1 for state file)
```

---

## Quick Wins (First Session)

If we only have 1 session to build this:

1. **Phase 0 foundation** (create repo, basic workflow)
2. **Phase 1 context monitor** (the most impactful single piece)
3. **Basic Telegram alerting**

That's enough to catch the 87% → 95% failure mode with a 5-minute warning instead of a 3-minute one.

---

## Future Enhancements

- **Predictive compaction** — ML model predicts when context will hit 80%
- **Auto-compaction** — LCM plugin triggers compaction automatically
- **Multi-session monitoring** — Monitor all agent sessions simultaneously
- **Slack integration** — Route alerts to Slack as well as Telegram
- **PagerDuty integration** — Escalate to phone for CRITICAL at night

---

*Built by Hermes + Dre — 2026-07-07*
