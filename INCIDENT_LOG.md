# Hermes Watchdog — Incident Log

Auto-generated. Each incident gets a line added.

| Date | Level | Signal | Value | Action | Resolution |
|------|-------|--------|-------|--------|------------|
| 2026-07-07 | CRITICAL | context | 95% | Session died | New session started |

---

## Incident Detail: 2026-07-07

**Level:** CRITICAL  
**Signal:** Context saturation + API stall  
**Root cause:** API call #8 blocked for 367s (6 min)  

**Timeline:**
- 11:44 AM — User sends message
- 11:44 AM — Agent starts work, API call #8 begins
- ~11:50 AM — API call #8 completes (367s later)
- Context hit 87% → 95% during stall
- 11:53 AM — 3-min inactivity warning fires (TOO LATE)
- 11:55 AM — 5-min gateway timeout kills session

**What the watchdog system will prevent:**
- Tool call circuit breaker: Would alert at 90s, fire CRITICAL at 180s
- Context monitor: Would alert at 65% (not 87%)
- External heartbeat: Would catch no-activity in 5 min (not 6 min)

**Fix deployed:** hermes-watchdog v1 (this repo)
