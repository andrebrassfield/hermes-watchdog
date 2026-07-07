# Recovery Playbook

## When Something Goes Wrong

### Step 1: Don't Panic

The watchdog system has been capturing state snapshots. Even if the session dies completely, you can recover.

### Step 2: Check Telegram for the Last Alert

The alert will tell you:
- What signal triggered (context %, tool stall, no activity)
- What the value was at time of alert
- What action was taken

### Step 3: Check GitHub for the Latest Snapshot

```
Repo: andrebrassfield/hermes-watchdog
Path: snapshots/
```

Find the most recent `*.json` file. This is your latest state backup.

### Step 4: Recover

**Option A: Resume from Snapshot**
```
skill: watchdog-monitor
/run recovery {snapshot_id}
```

**Option B: Fresh Start**
```
/reset
```
The agent will start fresh. The snapshot is preserved in GitHub for manual review.

---

## Recovery Scenarios

### Scenario 1: Context Hit 90%+ (OOM or Compaction Failure)

**What happened:** Context filled completely. Agent likely crashed or went unresponsive.

**Signs:**
- Telegram: 🚨 CRITICAL alert on context at 90%+
- GitHub Issue: Created with `watchdog-critical` label

**Recovery:**
1. Agent auto-restarts (MaxHermes gateway)
2. New session starts
3. Load latest snapshot: `python3 session_rescue.py restore {latest}`
4. Review what was lost
5. If resumable: continue from checkpoint
6. If not: fresh start

**Prevention:** Phase 2 will add proactive compaction at 65%.

---

### Scenario 2: Tool Call Stalled (6+ Minutes)

**What happened:** A single tool call (web search, content extraction) blocked the session for 6 minutes.

**Signs:**
- Telegram: 🔴 ALERT on tool stall
- Tool timing log: One call with 367s duration

**Recovery:**
1. Next tool call proceeds normally (circuit breaker)
2. Session survives — no manual recovery needed
3. Log is preserved for post-mortem

**Prevention:** Phase 2 circuit breaker fires at 90s, alerts at 120s.

---

### Scenario 3: Session Completely Dead (Gateway Timeout)

**What happened:** Agent went silent for 5+ minutes. Gateway killed the session.

**Signs:**
- Telegram: 🚨 CRITICAL no-activity alert
- Session never recovered

**Recovery:**
1. MaxHermes auto-creates new session
2. Agent starts fresh
3. Load snapshot from GitHub
4. Assess: was the work recoverable?

**Prevention:** Phase 3 heartbeat catches silent sessions in 5 min, before gateway timeout.

---

### Scenario 4: Sandbox Itself is Down

**What happened:** The entire MaxHermes sandbox is unreachable.

**Signs:**
- GitHub heartbeat: 3 consecutive misses
- GitHub Issue: `watchdog-critical` created automatically

**Recovery:**
1. This is a MaxHermes infrastructure issue — not solvable by watchdog
2. Alert Dre via Telegram: "Sandbox may be down — manual check needed"
3. When MaxHermes recovers: session auto-restarts

**Prevention:** Can't prevent — but we catch it in 15 minutes instead of hours.

---

## Snapshot Contents

A snapshot contains:
```json
{
  "id": "session_1234567890_1719834000",
  "reason": "context_critical",
  "ts": "2026-07-07T12:00:00Z",
  "session_id": "session_1234567890",
  "context_percent": 91,
  "context_history": [
    {"ts": "...", "context_percent": 45, ...},
    ...
  ],
  "tool_timing": [
    {"ts": "...", "tool_name": "web_search", "duration_s": 12.3, "status": "success"},
    ...
  ],
  "last_activity_ts": "2026-07-07T11:58:00Z",
  "health": { ... }
}
```

---

## Manual Commands

```
/watchdog status      — Show current health
/watchdog snapshot    — Force a manual snapshot
/watchdog alerts      — Show recent alerts
/watchdog list        — List available snapshots
/watchdog restore {id} — Restore from snapshot
```

---

## Emergency Contacts

- MaxHermes status: Check if the cloud service is operational
- Dre: Check Telegram for manual override
