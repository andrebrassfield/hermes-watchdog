# Alert Thresholds Reference

## At a Glance

| Signal | WATCH | WARN | ALERT | CRITICAL |
|--------|-------|------|-------|----------|
| Context % | 50–64% | 65–79% | 80–89% | 90%+ |
| Tool call duration | 60–89s | 90–119s | 120–179s | 180s+ |
| No activity | 90–119s | 120–149s | 150–179s | 180s+ |
| Growth rate | 5%/min | 10%/min | 15%/min | 20%+/min |

## Context % Thresholds

```
0%  ─┬─ NOMINAL ─────────────────────────────────────────────────
    │
50% ─┤─ WATCH        "Context at 52% — monitoring closely"
    │                  Action: Increase sampling to 15s
    │
65% ─┤─ WARN         "Context at 68% — backing up state"
    │                  Action: Snapshot to GitHub, alert Telegram
    │
80% ─┤─ ALERT        "Context at 83% — compaction needed"
    │                  Action: Full snapshot, GitHub Issue created
    │
90% ─┤─ CRITICAL     "Context at 93% — emergency!"
    │                  Action: Rescue sequence, /reset if needed
    │
100% ─┴─ SESSION DEAD (compaction or OOM)
```

## Tool Call Duration

The most impactful threshold. The 2026-07-07 incident was a 367s (6 min) call that killed the session.

```
0s   ─┬─ Normal (let run)
      │
60s  ─┤─ WATCH "Tool call running long (62s)"
      │         Action: Log, increase monitoring
      │
90s  ─┤─ WARN "Tool call slow (94s) — web_search"
      │         Action: Alert Telegram (if cooldown allows)
      │
120s ─┤─ ALERT "Tool stalled (127s) — circuit breaker"
      │         Action: Log full details, attempt cancel signal
      │
180s ─┴─ BREAK/CANCEL "Tool call killed by circuit breaker"
              Action: Fire CRITICAL alert, snapshot state
```

## Per-Tool Overrides

Some tools are known to be slower. Overrides adjust thresholds:

| Tool | WATCH | WARN | ALERT | BREAK |
|------|-------|------|-------|-------|
| `web_search` | 60s | 90s | 120s | 180s |
| `batch_web_search` | 90s | 150s | 240s | 300s |
| `extract_content` | 60s | 120s | 180s | 240s |
| `git_operation` | 45s | 90s | 150s | 200s |

## Context Growth Rate

Context % per minute of conversation. High growth = session running out of steam fast.

```
0-4%/min   ─── NOMINAL
5-9%/min   ─── WATCH   (eta to 80% still > 10 min)
10-14%/min ─── WARN    (eta to 80% is 5-10 min)
15-19%/min ─── ALERT   (eta to 80% is < 5 min)
20%+/min   ─── CRITICAL (will hit 80% within 3 min)
```

## Time-to-80%

A derived metric: "If context keeps growing at this rate, how many minutes until 80%?"

```
> 15 min  ─── NOMINAL (plenty of runway)
10-15 min ─── WATCH   (start thinking about compaction)
5-10 min  ─── WARN    (compaction should run soon)
< 5 min   ─── ALERT   (compaction must run now)
NOW       ─── CRITICAL (already at 80%+)
```

## Cooldown Table

| Level | Cooldown | Why |
|-------|----------|-----|
| WATCH | 5 min | Prevent alert spam during normal monitoring |
| WARN | 3 min | Allow time for state to change before re-alerting |
| ALERT | 10 min | Give time for action to take effect |
| CRITICAL | 30 min | Don't spam during active incident |

## GitHub Issue Labels

| Label | When Created |
|-------|-------------|
| `watchdog-watch` | On WATCH (if enabled) |
| `watchdog-alert` | On ALERT |
| `watchdog-critical` | On CRITICAL |
| `watchdog-recovered` | After incident resolved |
