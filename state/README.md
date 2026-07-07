# State Directory

This directory is where the agent pushes its live state for GitHub Actions to read.

**Not committed to git** — `.gitignore` excludes this directory.

The agent pushes to `state/latest.jsonl` (overwriting each time) so GitHub Actions can read the current state without cloning the full history.

## File Format

`state/latest.jsonl` — one JSON object per line, most recent last.

```jsonl
{"ts": "2026-07-07T14:30:00Z", "context_percent": 42, "tool_call_active": false}
{"ts": "2026-07-07T14:30:05Z", "context_percent": 43, "tool_call_active": true, "tool_name": "web_search"}
{"ts": "2026-07-07T14:30:12Z", "context_percent": 43, "tool_call_active": false}
```

## GitHub Actions Read Path

```
hermes-watchdog/state/latest.jsonl
         ↑ pushed by agent every 5 min
```

GitHub Actions `context-monitor.yml` reads this file every 2 minutes to check for high context.
