# watchdog-circuit-breaker Skill

## Purpose

Prevents a single slow/stalled tool call from killing the session.

The failure from 2026-07-07 was a single API call (#8) that took 367 seconds (6+ minutes). While that call was blocking, the session couldn't do anything — context grew, the 3-minute warning fired, and the session died.

This skill wraps every tool call with a circuit breaker that times out slow calls and fires alerts before they become fatal.

## How It Works

```
Tool Call Starts
      │
      ▼
[Record start time]
      │
      ▼
┌─────────────────────────────────┐
│     Circuit Breaker Wrapper      │
│                                 │
│  0–90s:   Normal — let run      │
│  90–120s: WATCH — log slow      │
│  120–180s: ALERT — log + warn  │
│  180s+:   BREAK — cancel + alert │
│                                 │
└─────────────────────────────────┘
      │
      ▼
[Tool completes or times out]
      │
      ▼
[Log duration, check thresholds]
      │
      ▼
[Continue to next tool call]
```

## Key Thresholds

| Duration | Level | Action |
|----------|-------|--------|
| < 60s | Normal | None |
| 60–90s | WATCH | Log as slow, increase sampling |
| 90–120s | WARN | Fire WATCH alert via Telegram |
| 120–180s | ALERT | Fire WARN alert via Telegram |
| 180s+ | BREAK | Cancel call (if possible), fire ALERT |

## Usage

This skill should be loaded alongside `watchdog-monitor`. It's not standalone — it enhances the monitoring skill with circuit breaker functionality.

```
skill: watchdog-circuit-breaker
```

## Key Functions

### `with_timing(tool_name, tool_fn, *args, **kwargs)`

Wrap any tool call:

```python
def web_search(query):
    return with_timing("web_search", actual_web_search, query=query)

def extract_content(url):
    return with_timing("extract_content", actual_extract, url=url)
```

### `cancel_if_stalled()`

Called periodically (every 30s during a long call). Checks if current tool has been running > 180s. If so, attempts to cancel and marks it as "stalled."

```python
def cancel_if_stalled():
    if current_tool_start and (time.time() - current_tool_start) > 180:
        # Log as stalled
        log_stalled_tool(current_tool_name, time.time() - current_tool_start)
        # Attempt cancel (set a flag, don't actually kill the process)
        return True
    return False
```

### `should_proceed(tool_name)`

Circuit breaker pattern — if a tool has stalled repeatedly, briefly skip it:

```python
STALL_THRESHOLD = 3  # Stall 3 times on same tool = circuit open
COOLDOWN_PERIOD = 60  # seconds

def should_proceed(tool_name):
    stalls = stall_count.get(tool_name, 0)
    if stalls >= STALL_THRESHOLD:
        if time.time() - last_stall[tool_name] < COOLDOWN_PERIOD:
            return False  # Circuit open
        else:
            # Reset and try again
            stall_count[tool_name] = 0
    return True
```

## Circuit State

```python
# Per-tool circuit state
circuit_state = {
    "tool_name": {
        "stall_count": 0,
        "last_stall_ts": None,
        "avg_duration_s": 0.0,
        "last_5_durations": [],  # ring buffer
    }
}
```

## Alert on Stall

When a tool is cancelled or marked as stalled:

```python
fire_alert(
    level="ALERT",
    signal=f"tool_stall:{tool_name}",
    value=f"{duration:.0f}s",
    action=f"Tool {tool_name} stalled. Circuit breaker opened. Next call will retry.",
    agent="hermes",
)
```

## Snapshot on Stall

Stall events are important enough to snapshot immediately:

```python
# On any stall (> 180s):
snapshot_state(reason=f"tool_stall:{tool_name}", duration=duration)
```

## Common Stalled Tools

Based on the incident, these are the most likely to stall:

- `web_search` / `mcp_matrix_batch_web_search` — network-dependent
- `extract_content_from_websites` — website responsiveness
- `git operations` — network + disk
- `gh api` calls — GitHub API rate limits

When these tools are called, the circuit breaker is especially vigilant.

## Integration with watchdog-monitor

The circuit-breaker skill is additive to watchdog-monitor. Load both:

```
skill: watchdog-monitor
skill: watchdog-circuit-breaker
```

The circuit-breaker uses the same state files and alert cooldowns as watchdog-monitor.

## Pitfalls

1. **Don't actually kill processes** — you can't safely SIGKILL from within Python. Set a flag and let the next call proceed.
2. **Don't over-alert** — the 180s BREAK threshold is the only guaranteed stall. 90–180s is watch-only.
3. **Reset on success** — if a tool call succeeds after being flagged slow, reset its stall count.
4. **Ring buffer the durations** — only keep last 5 durations per tool to compute rolling average.

## Verification

```bash
# Simulate a slow tool call:
timeout 5 python3 -c "
import time, sys
sys.path.insert(0, 'src')
from circuit_breaker import with_timing
def slow_fn():
    time.sleep(4)
    return 'ok'
result = with_timing('test_slow', slow_fn)
print(f'Result: {result}')
"

# Should see timing logged
# Should NOT see alert (4s < 90s threshold)
```
