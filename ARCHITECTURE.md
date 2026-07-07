# Hermes Watchdog — Architecture Deep Dive

## The Failure Mode (Post-Mortem)

```
Timeline from screenshot (2026-07-07):
T+0:00   User sends message at 11:44 AM
T+0:XX   Agent starts work — API call #8 begins
T+6:07   API call #8 completes (367 seconds = 6 min 7 sec)
T+0:00   After API call: context was 87%
T+~60s   Context climbs to 95% (compaction threshold)
T+3:00   "No activity for 3 min" warning fires
T+5:00   Gateway timeout kills session
```

**What failed:**
1. API call #8 took 6+ minutes — no circuit breaker
2. Context filled from 87% → 95% during the block — no preemptive dump
3. Compaction kicked in reactively instead of proactively
4. 3-min warning was too late to recover
5. 5-min timeout was the death sentence

---

## Layer 1: Detection — The Signal Layer

### Signal Sources

We watch 4 primary signal channels:

**1. Context Usage (from agent self-reporting)**
```
Signal: context_percent (0–100)
Source: Agent internal state, sampled at each tool call completion
Storage: ~/.hermes/watchdog/state.jsonl
Sample rate: Every tool call + every 30 seconds idle
```

**2. Tool Call Duration (from watchdog wrapper)**
```
Signal: tool_call_duration_seconds
Source: Wrapped around every tool call via circuit breaker
Storage: ~/.hermes/watchdog/tool_timing.jsonl
Threshold: > 60s = slow, > 120s = stalled, > 180s = kill
```

**3. Last Activity Timestamp (from heartbeat)**
```
Signal: seconds_since_last_activity
Source: Tracked by watchdog-monitor skill
Storage: ~/.hermes/watchdog/activity.json
Threshold: > 90s = concern, > 150s = critical
```

**4. External Heartbeat (from GitHub Actions)**
```
Signal: heartbeat_stale (boolean)
Source: GitHub Actions scheduled workflow
Storage: GitHub Actions log + hermes-watchdog/.heartbeat file
Threshold: Missed 2 consecutive = critical
```

### Signal Collection — Context Monitor

The `context_monitor.py` script runs inside the agent environment and:

1. Reads `~/.hermes/watchdog/state.jsonl` for context history
2. Computes rate of context growth (context_per_minute)
3. Predicts time-to-80% based on current rate
4. Writes alerts to `~/.hermes/watchdog/alerts.json`

```python
# Simplified detection logic
def detect_context_danger(state_history):
    latest = state_history[-1]
    pct = latest['context_percent']
    rate = compute_growth_rate(state_history)  # % per minute
    
    # Predict
    if pct < 50:
        return "NOMINAL", pct
    elif pct < 65:
        time_to_80 = (80 - pct) / rate if rate > 0 else float('inf')
        if time_to_80 < 10:
            return "WARN", f"Context {pct}% — 80% in ~{time_to_80:.0f}min"
        return "WATCH", pct
    elif pct < 80:
        return "ALERT", f"Context {pct}% — compaction needed"
    else:
        return "CRITICAL", f"Context {pct}% — emergency dump!"
```

---

## Layer 2: Decision — The Threshold Engine

### Threshold Matrix

| Signal | WATCH | WARN | ALERT | CRITICAL |
|--------|-------|------|-------|----------|
| Context % | 50–64% | 65–79% | 80–89% | 90%+ |
| Tool duration | 60–90s | 90–120s | 120–180s | 180s+ |
| No activity | 90–120s | 120–150s | 150–180s | 180s+ |
| Heartbeat missed | 1 | 1 | 2 | 3+ |
| Context rate | < 5%/min | 5–10%/min | 10–15%/min | 15%+/min |

### Alert Cooldown

Prevents alert storms:

```yaml
cooldowns:
  watch:  5 min   # Min time between WATCH alerts
  warn:   3 min   # Min time between WARN alerts
  alert:  10 min  # Min time between ALERT alerts
  critical: 30 min # Min time between CRITICAL alerts
```

### Decision Tree

```
START
  │
  ├─► Is context % > 50%?
  │     ├─ NO  → NOMINAL
  │     └─ YES → Is cooldown active for this level?
  │              ├─ YES → Skip alert, log only
  │              └─ NO  → Determine level:
  │                       50–64% = WATCH
  │                       65–79% = WARN
  │                       80–89% = ALERT
  │                       90%+   = CRITICAL
  │
  ├─► Is any tool call > 60s?
  │     ├─ NO  → NOMINAL
  │     └─ YES → Mark slow, increase sample rate
  │              ├─ 60–90s  → Log + WATCH
  │              ├─ 90–120s → WARN
  │              ├─ 120–180s → ALERT
  │              └─ 180s+   → CRITICAL + attempt cancel
  │
  └─► Time since last activity?
        ├─ < 90s  → NOMINAL
        ├─ 90–120s → WATCH
        ├─ 120–150s → WARN
        ├─ 150–180s → ALERT
        └─ 180s+   → CRITICAL + trigger rescue
```

---

## Layer 3: Action — The Response Layer

### Telegram Alert Format

All Telegram alerts follow this structure:

```
[LEVEL] [TIMESTAMP] Watchdog Alert
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signal: {context_%|tool_duration|no_activity}
Value:  {current_value}
Status: {alert_level}
Action: {recommended_action}

⏱ Time-to-critical: {estimated_minutes}min
📍 Last activity: {n} seconds ago
🔧 Agent: {profile_name}
```

### State Snapshot

When WARN or higher fires, we dump session state to GitHub:

```python
def snapshot_state():
    snapshot = {
        "ts": timestamp(),
        "context_percent": read_context_percent(),
        "tool_timing": read_tool_timing(),
        "activity_ts": read_last_activity(),
        "session_id": current_session_id(),
        "recent_history": read_last_n_state_events(20),
    }
    
    # Write to hermes-watchdog/snapshots/{session_id}_{ts}.json
    path = f"snapshots/{session_id}_{timestamp().replace(':','-')}.json"
    push_to_github(path, snapshot)
    
    return path
```

---

## Layer 4: Recovery — The Rescue Layer

### Recovery Playbook

**Scenario 1: Context at 80%+, agent still responsive**
```
1. Telegram: "Context at {X}% — initiating preemptive compaction"
2. Agent: Run context compaction (if LCM plugin available)
3. If compaction frees > 20%: continue normally
4. If compaction frees < 20%: alert "compaction insufficient, consider /reset"
5. Snapshot state
```

**Scenario 2: Tool call stalled 180s+**
```
1. Fire CRITICAL alert
2. Log: which tool, how long, what arguments (secrets redacted)
3. Send cancel signal to tool (if supported)
4. Next tool call proceeds normally
5. Do NOT block — let the session continue
```

**Scenario 3: No activity 180s+, agent appears deadlocked**
```
1. CRITICAL alert
2. Snapshot current state
3. Push state to hermes-watchdog/snapshots/
4. Send /reset command to gateway
5. On restart: load latest snapshot, resume from last checkpoint
```

**Scenario 4: GitHub Actions heartbeat missed 3x**
```
1. Sandbox likely down or unreachable
2. Create GitHub Issue: label=watchdog-critical
3. Telegram: "Sandbox may be down — manual intervention required"
4. Do NOT attempt automated rescue (too many unknowns)
```

### State Restoration

After a rescue, the agent:

1. Reads the latest snapshot from `snapshots/`
2. Reconstructs session context from snapshot
3. Reports what it was doing before the crash
4. Asks: "Resume from where we left off?"
5. If confirmed: replays pending work items
6. If not confirmed: fresh start, historical context preserved in snapshot

---

## Layer 5: GitHub Cockpit

### Issue Dashboard

GitHub Issues serve as the incident log:

```
Labels used:
- watchdog-watch    (informational, no action needed)
- watchdog-warn     (monitoring elevated)
- watchdog-alert    (action required)
- watchdog-critical (immediate intervention)
- watchdog-recovered (incident resolved)
```

### Heartbeat File (`.heartbeat`)

GitHub Actions writes a timestamp every 5 minutes:

```json
{
  "last_heartbeat": "2026-07-07T16:45:00Z",
  "consecutive_misses": 0,
  "agent_status": "responsive",
  "context_percent": 34,
  "uptime_minutes": 127
}
```

### Scheduled Workflows

```
heartbeat.yml      → every 5 min  (miss detection)
context-monitor.yml → every 2 min  (context + tool timing)
health-report.yml   → every 15 min (full system health)
```

---

## Data Flow

```
                    ┌──────────────────┐
                    │   AGENT SESSION   │
                    │  (MaxHermes sand) │
                    └────────┬─────────┘
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
          ▼                  ▼                  ▼
   ~/.hermes/watchdog/  tool calls     Telegram
   state.jsonl          (timed)         bot
          │                  │              
          ▼                  ▼              
   context_monitor.py    circuit_breaker.py
          │                  │              
          └────────┬─────────┘              
                   │                        
                   ▼                        
         ~/.hermes/watchdog/alerts.json     
                   │                        
         ┌─────────┴─────────┐              
         ▼                   ▼              
   GitHub Actions         Telegram bot       
   (5-min heartbeat)     (immediate)        
         │                                  
         ▼                                  
   hermes-watchdog/                       
   .heartbeat + issues                    
```

---

## Security Considerations

1. **No secrets in logs** — tool arguments are redacted before logging
2. **Telegram token in GitHub Secrets** — never in code
3. **Snapshot sanitization** — PII stripped before push
4. **Read-only GitHub PAT** — watchdog repo only, no other repos
5. **State file permissions** — `~/.hermes/watchdog/` is owner-read-only

---

## Performance Impact

- Monitoring overhead: < 1% CPU (just file reads + simple math)
- State writes: ~1KB per event
- GitHub push (snapshot): ~10–50KB, once per incident
- Telegram alerts: < 500 bytes each

The watchdog adds negligible load to the agent. Most of the heavy lifting (heartbeat, GitHub Actions) runs external to the agent.
