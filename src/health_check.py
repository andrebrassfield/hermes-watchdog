#!/usr/bin/env python3
"""
hermes-watchdog health_check.py
Run inside the MaxHermes sandbox to report agent health status.
Writes JSON to stdout for external consumption (GitHub Actions, Telegram).
"""

import json
import os
import time
from pathlib import Path

WATCHDOG_DIR = Path.home() / ".hermes" / "watchdog"
STATE_FILE = WATCHDOG_DIR / "state.jsonl"
ACTIVITY_FILE = WATCHDOG_DIR / "activity.json"
ALERTS_FILE = WATCHDOG_DIR / "alerts.json"

# ── Config thresholds ──────────────────────────────────────────
THRESHOLDS = {
    "context": {"watch": 50, "warn": 65, "alert": 80, "critical": 90},
    "tool_duration": {"watch": 60, "warn": 90, "alert": 120, "critical": 180},
    "no_activity": {"watch": 90, "warn": 120, "alert": 150, "critical": 180},
}

def read_context_history(n=10):
    """Read last N context samples from state file."""
    if not STATE_FILE.exists():
        return []
    with open(STATE_FILE) as f:
        lines = f.readlines()
    samples = []
    for line in lines[-n:]:
        try:
            samples.append(json.loads(line))
        except:
            pass
    return samples

def current_context_pct():
    """Get latest context %."""
    history = read_context_history(1)
    return history[-1].get("context_percent", 0) if history else 0

def compute_growth_rate(history):
    """Compute context growth rate (% per minute) from history."""
    if len(history) < 2:
        return 0.0
    oldest = history[0]
    newest = history[-1]
    try:
        t0 = time.mktime(time.strptime(oldest["ts"], "%Y-%m-%dT%H:%M:%SZ"))
        t1 = time.mktime(time.strptime(newest["ts"], "%Y-%m-%dT%H:%M:%SZ"))
    except:
        return 0.0
    dt = max(t1 - t0, 1)
    dp = newest.get("context_percent", 0) - oldest.get("context_percent", 0)
    return (dp / dt) * 60  # % per minute

def last_activity_seconds():
    """Seconds since last agent activity."""
    if not ACTIVITY_FILE.exists():
        return None
    try:
        with open(ACTIVITY_FILE) as f:
            data = json.load(f)
        ts = data.get("last_activity_ts")
        if ts:
            try:
                t = time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
                return int(time.time() - t)
            except:
                pass
    except:
        pass
    return None

def slowest_tool(history):
    """Find the slowest tool call in recent history."""
    if not history:
        return None
    slowest = max(history, key=lambda x: x.get("tool_duration_s", 0))
    if slowest.get("tool_duration_s", 0) > 0:
        return slowest
    return None

def alert_level(pct, tool_s, no_activity_s):
    """Determine current alert level based on all signals."""
    # Context
    ctx = THRESHOLDS["context"]
    if pct >= ctx["critical"]: return "CRITICAL", "context"
    if pct >= ctx["alert"]: return "ALERT", "context"
    if pct >= ctx["warn"]: return "WARN", "context"
    if pct >= ctx["watch"]: return "WATCH", "context"
    
    # Tool duration
    if tool_s and tool_s >= THRESHOLDS["tool_duration"]["critical"]: return "CRITICAL", "tool"
    if tool_s and tool_s >= THRESHOLDS["tool_duration"]["alert"]: return "ALERT", "tool"
    if tool_s and tool_s >= THRESHOLDS["tool_duration"]["warn"]: return "WARN", "tool"
    if tool_s and tool_s >= THRESHOLDS["tool_duration"]["watch"]: return "WATCH", "tool"
    
    # No activity
    if no_activity_s and no_activity_s >= THRESHOLDS["no_activity"]["critical"]: return "CRITICAL", "activity"
    if no_activity_s and no_activity_s >= THRESHOLDS["no_activity"]["alert"]: return "ALERT", "activity"
    if no_activity_s and no_activity_s >= THRESHOLDS["no_activity"]["warn"]: return "WARN", "activity"
    if no_activity_s and no_activity_s >= THRESHOLDS["no_activity"]["watch"]: return "WATCH", "activity"
    
    return "OK", "none"

def time_to_80_pct(rate, current_pct):
    """Predict minutes until context hits 80%."""
    if rate <= 0:
        return float('inf')
    return (80 - current_pct) / rate

def main():
    WATCHDOG_DIR.mkdir(parents=True, exist_ok=True)
    
    history = read_context_history(20)
    pct = current_context_pct()
    rate = compute_growth_rate(history)
    no_activity = last_activity_seconds()
    slow_tool = slowest_tool(history)
    tool_s = slow_tool.get("tool_duration_s") if slow_tool else None
    
    level, reason = alert_level(pct, tool_s, no_activity)
    t80 = time_to_80_pct(rate, pct)
    
    health = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": level,
        "alert_reason": reason,
        "context_percent": pct,
        "context_growth_rate_pct_per_min": round(rate, 2),
        "time_to_80_min": round(t80, 1) if t80 != float('inf') else None,
        "last_activity_seconds_ago": no_activity,
        "slowest_tool": {
            "name": slow_tool.get("tool_name") if slow_tool else None,
            "duration_s": tool_s
        } if slow_tool else None,
        "samples_in_history": len(history),
    }
    
    print(json.dumps(health, indent=2))
    
    # Also write to watchdog state for GitHub Actions to pick up
    state_out = WATCHDOG_DIR / "health.json"
    with open(state_out, "w") as f:
        json.dump(health, f, indent=2)
    
    return health

if __name__ == "__main__":
    main()
