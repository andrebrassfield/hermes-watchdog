# Telegram Alert Reference

All watchdog alerts are sent to the configured Telegram chat.

## Alert Format

Every alert follows this structure:

```
[LEVEL] [TIMESTAMP] Watchdog Alert
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signal: {signal}
Value: {value}
Status: {level} ({reason})
Action: {action}

⏱ Time-to-80%: {n}min
📍 Last activity: {n}s ago
🔧 Agent: hermes
```

## Alert Levels

### 🟡 WATCH (Level: INFO)
**Trigger:** Informational — no immediate action needed.

Example:
```
🟡 [14:23:01 UTC] Watchdog Alert
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signal: context_percent
Value: 54%
Status: WATCH (context)
Action: Monitoring closely

⏱ Time-to-80%: 8min
📍 Last activity: 23s ago
🔧 Agent: hermes
```

**When:** Context at 50–64%, or tool call > 60s.

---

### 🟠 WARN (Level: WARNING)
**Trigger:** Elevated monitoring — prepare for action.

Example:
```
🟠 [14:25:33 UTC] Watchdog Alert
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signal: context_percent
Value: 68%
Status: WARN (context)
Action: Backing up state to GitHub

⏱ Time-to-80%: 4min
📍 Last activity: 45s ago
🔧 Agent: hermes
```

**When:** Context at 65–79%, or tool call > 90s, or no activity > 120s.

**Action taken:** State snapshot created, pushed to GitHub.

---

### 🔴 ALERT (Level: ERROR)
**Trigger:** Action required — intervention needed.

Example:
```
🔴 [14:28:15 UTC] Watchdog Alert
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signal: tool_stall:web_search
Value: 142s
Status: ALERT (tool)
Action: Tool web_search stalled. Next call will retry.

⏱ Time-to-80%: N/A
📍 Last activity: 89s ago
🔧 Agent: hermes
```

**When:** Context at 80–89%, or tool call > 120s, or no activity > 150s.

**Action taken:** GitHub Issue created, Telegram fires, session marked for review.

---

### 🚨 CRITICAL (Level: EMERGENCY)
**Trigger:** Immediate intervention — session may die.

Example:
```
🚨 [14:30:00 UTC] Watchdog Alert
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signal: context_percent
Value: 93%
Status: CRITICAL (context)
Action: Emergency state dump. Rescue sequence queued.

⏱ Time-to-80%: NOW
📍 Last activity: 167s ago
🔧 Agent: hermes
```

**When:** Context at 90%+, or tool call > 180s, or no activity > 180s.

**Action taken:** Full state snapshot pushed, GitHub Issue created with `watchdog-critical`, rescue workflow triggered.

---

## Alert Commands

### /watchdog status
Returns current health JSON:
```
✅ Watchdog OK
Context: 34%
Growth: 2.1%/min
Last activity: 12s ago
Slowest tool: web_search (8.2s)
Time to 80%: ~22min
```

### /watchdog snapshot
Forces a manual state snapshot:
```
📸 Snapshot created: session_xxx_1719834000.json
Pushed to: hermes-watchdog/snapshots/
```

### /watchdog alerts
Shows recent alerts:
```
Recent alerts:
🟠 WARN 14:25 — context 68%
🟡 WATCH 14:20 — context 54%
✅ OK 14:15 — context 31%
```

### /watchdog list
Lists available snapshots:
```
Available snapshots:
session_xxx_1719834000.json (context: 91%)
session_xxx_1719833500.json (context: 72%)
session_xxx_1719833000.json (context: 45%)
```

### /watchdog restore {id}
Restores from a snapshot:
```
📦 Restoring from session_xxx_1719834000.json
Context: 91%
Reason: context_critical
Session: session_xxx
⏱ Loading state...
✓ Session restored
```

---

## Routing

| Event | Telegram | GitHub Issue | GitHub Actions |
|-------|----------|--------------|----------------|
| WATCH | ✅ (info) | ❌ | Log only |
| WARN | ✅ | ❌ | Snapshot |
| ALERT | ✅ | ✅ (watchdog-alert) | Snapshot + flag |
| CRITICAL | ✅ | ✅ (watchdog-critical) | Full rescue |

---

## Cooldowns

To prevent alert storms, each level has a minimum time between alerts:

- **WATCH**: 5 min
- **WARN**: 3 min
- **ALERT**: 10 min
- **CRITICAL**: 30 min

---

## Telegram Bot Setup

1. Create bot via @BotFather: `/newbot`
2. Get bot token: `123456:ABC-DEF...`
3. Start chat with bot, send `/start`
4. Get your chat ID: `123456789`
5. Add to `~/.hermes/watchdog/config.json`:
```json
{
  "telegram_bot_token": "123456:ABC-DEF...",
  "telegram_chat_id": "123456789"
}
```
6. Or set env vars: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
