# watchdog-monitor Skill

## Trigger Conditions

**ALWAYS LOAD** — at the start of every session. This skill is the core of the proactive monitoring system.

## What It Does

The watchdog-monitor skill runs a lightweight co-routine alongside the agent's normal work:

1. **Samples context %** at every tool call completion
2. **Times every tool call** and logs slow ones
3. **Tracks last agent activity** timestamp
4. **Fires graduated alerts** at 50%, 65%, 80% context thresholds
5. **Predicts time-to-80%** based on context growth rate
6. **Dumps state snapshots** to GitHub when WARN or higher fires
7. **Maintains cooldowns** to prevent alert storms

## Context Sampling

```python
# On every tool call completion, sample context:
SAMPLE_INTERVAL = 30  # seconds between samples when idle
STATE_FILE = ~/.hermes/watchdog/state.jsonl

def sample_context():
    # Read current context (approximated from recent tool calls)
    # Write to state.jsonl as JSONL line
    with open(STATE_FILE, "a") as f:
        f.write(json.dumps({
            "ts": timestamp(),
            "context_percent": current_context_pct(),
            "tool_call_active": False,
            "tool_name": None,
            "tool_duration_s": None,
        }) + "\n")
```

## Alert Levels

| Level | Trigger | Action |
|-------|---------|--------|
| WATCH | Context 50–64% | Log, increase sampling to 15s |
| WARN | Context 65–79% | Fire Telegram, create snapshot |
| ALERT | Context 80–89% | Fire Telegram, push snapshot to GitHub |
| CRITICAL | Context 90%+ OR 180s stall | Fire Telegram, trigger rescue |

## Cooldown Periods

```yaml
cooldowns:
  watch:  5 min   # Minimum between WATCH alerts
  warn:   3 min   # Minimum between WARN alerts
  alert:  10 min  # Minimum between ALERT alerts
  critical: 30 min # Minimum between CRITICAL alerts
```

## Tool Call Timing

Every tool call is wrapped with timing:

```python
def timed_tool_call(tool_name, tool_fn, *args, **kwargs):
    start = time.time()
    try:
        result = tool_fn(*args, **kwargs)
        duration = time.time() - start
        log_tool_call(tool_name, duration, "success", result)
        return result
    except Exception as e:
        duration = time.time() - start
        log_tool_call(tool_name, duration, "error", str(e))
        raise

def log_tool_call(name, duration, status, result):
    # Write to tool_timing.jsonl
    # If duration > 90s: increase monitoring frequency
    # If duration > 150s: fire WATCH alert
    # If duration > 180s: fire ALERT + attempt cancel
    pass
```

## State Files

- `~/.hermes/watchdog/state.jsonl` — context history (JSONL, one line per sample)
- `~/.hermes/watchdog/tool_timing.jsonl` — tool call timings
- `~/.hermes/watchdog/activity.json` — last activity timestamp
- `~/.hermes/watchdog/alerts.json` — recent alerts (for cooldown tracking)
- `~/.hermes/watchdog/health.json` — current health snapshot

## GitHub State Push

Every 5 minutes, push state to GitHub for external monitoring:

```python
# Push to: hermes-watchdog/state/latest.jsonl
# (always overwrite — this is a snapshot, not a log)
def push_state_to_github():
    # Read ~/.hermes/watchdog/state.jsonl (last 50 lines)
    # Push to hermes-watchdog/state/latest.jsonl
    pass
```

## Usage

```
Load this skill at session start:
  skill: watchdog-monitor

The skill runs passively — no commands needed.
Monitor its output via Telegram alerts.

To check health manually:
  /watchdog status    → Show current health JSON
  /watchdog alerts    → Show recent alerts
  /watchdog snapshot  → Force a state snapshot
```

## Pitfalls

1. **Don't block on monitoring** — all monitoring is async. Never let it slow the agent.
2. **Redact secrets** — tool arguments go to tool_timing.jsonl. Never log API keys or tokens.
3. **Don't alert on cooldowns** — always check cooldown before firing Telegram.
4. **Snapshot before reset** — if a rescue is needed, snapshot BEFORE sending /reset.

## Verification

```bash
# After loading skill, verify it's running:
ls -la ~/.hermes/watchdog/

# Should see:
# state.jsonl, tool_timing.jsonl, activity.json, alerts.json, health.json

# Check the health check output:
python3 ~/.hermes/watchdog/health_check.py
```

## Files

- `src/health_check.py` — Core health check script
- `src/telegram_alerter.py` — Telegram alerting module
- `src/circuit_breaker.py` — Tool call timing and circuit breaker
- `configs/watchdog.yaml` — Threshold configuration
- `.github/workflows/heartbeat.yml` — GitHub Actions heartbeat
- `.github/workflows/context-monitor.yml` — GitHub Actions context watcher

## Skill ID

```
watchdog-monitor | v1 | hermes-watchdog
```
