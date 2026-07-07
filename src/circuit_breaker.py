#!/usr/bin/env python3
"""
hermes-watchdog circuit_breaker.py
Tool call timing wrapper with circuit breaker pattern.
Prevents a single slow/stalled tool call from killing the session.
"""

import json
import os
import time
from pathlib import Path
from collections import defaultdict, deque
from functools import wraps

WATCHDOG_DIR = Path.home() / ".hermes" / "watchdog"
TIMING_FILE = WATCHDOG_DIR / "tool_timing.jsonl"
STATE_FILE = WATCHDOG_DIR / "state.jsonl"
ALERTS_FILE = WATCHDOG_DIR / "alerts.json"
WATCHDOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Default Thresholds ────────────────────────
THRESHOLDS = {
    "watch": 60,
    "warn": 90,
    "alert": 120,
    "break": 180,
}

TOOL_OVERRIDES = {
    "web_search":              {"warn": 60, "alert": 120, "break": 180},
    "batch_web_search":        {"warn": 90, "alert": 150, "break": 240},
    "extract_content":         {"warn": 60, "alert": 120, "break": 180},
    "extract_content_from_websites": {"warn": 60, "alert": 120, "break": 180},
    "git_operation":           {"warn": 45, "alert": 90, "break": 150},
    "gh_api":                  {"warn": 45, "alert": 90, "break": 150},
}

# ── Circuit State ─────────────────────────────
circuit_state = defaultdict(lambda: {
    "stall_count": 0,
    "last_stall_ts": None,
    "rolling_durations": deque(maxlen=5),
})

current_tool_name = None
current_tool_start = None

# ── Utilities ────────────────────────────────
def get_thresholds(tool_name):
    return TOOL_OVERRIDES.get(tool_name, THRESHOLDS)

def get_level(duration, tool_name):
    t = get_thresholds(tool_name)
    if duration >= t["break"]: return "BREAK"
    if duration >= t["alert"]: return "ALERT"
    if duration >= t["warn"]: return "WARN"
    if duration >= t["watch"]: return "WATCH"
    return "OK"

def log_timing(tool_name, duration, status, error_msg=None):
    """Append a tool call record to tool_timing.jsonl."""
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool_name": tool_name,
        "duration_s": round(duration, 1),
        "status": status,
    }
    if error_msg:
        record["error"] = error_msg
    
    with open(TIMING_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")
    
    # Also update circuit state
    cs = circuit_state[tool_name]
    cs["rolling_durations"].append(duration)
    
    if status == "success":
        # Reset stall count on success
        cs["stall_count"] = 0
    
    return record

def check_cooldown(tool_name):
    """Check if circuit is open for this tool."""
    cs = circuit_state[tool_name]
    if cs["stall_count"] >= 3:
        if cs["last_stall_ts"] and (time.time() - cs["last_stall_ts"]) < 60:
            return False  # Circuit open
        else:
            cs["stall_count"] = 0  # Reset after cooldown
    return True

def mark_stalled(tool_name, duration):
    """Record a stall event."""
    cs = circuit_state[tool_name]
    cs["stall_count"] += 1
    cs["last_stall_ts"] = time.time()

def read_alerts(n=10):
    if not ALERTS_FILE.exists():
        return []
    with open(ALERTS_FILE) as f:
        try:
            return json.load(f)[-n:]
        except:
            return []

def in_cooldown(level):
    """Check if this alert level is in cooldown."""
    alerts = read_alerts()
    now = time.time()
    cooldown_seconds = {"WATCH": 300, "WARN": 180, "ALERT": 600, "CRITICAL": 1800}
    for alert in reversed(alerts):
        if alert.get("level") == level:
            ts = alert.get("ts")
            if ts:
                try:
                    t = time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
                    if now - t < cooldown_seconds.get(level, 0):
                        return True
                except:
                    pass
    return False

def record_alert(level, signal, value):
    """Record alert to alerts.json."""
    alerts = []
    if ALERTS_FILE.exists():
        with open(ALERTS_FILE) as f:
            try:
                alerts = json.load(f)
            except:
                alerts = []
    alerts.append({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "level": level,
        "signal": signal,
        "value": value,
    })
    with open(ALERTS_FILE, "w") as f:
        json.dump(alerts[-100:], f, indent=2)  # Keep last 100

# ── Main Wrapper ──────────────────────────────
def with_timing(tool_name, tool_fn, *args, **kwargs):
    """
    Wrap a tool call with timing and circuit breaker.
    
    Usage:
        result = with_timing("web_search", actual_search, query="...")
    
    Returns tuple: (result, metadata) where metadata has timing info.
    """
    global current_tool_name, current_tool_start
    
    # Check circuit
    if not check_cooldown(tool_name):
        log_timing(tool_name, 0, "circuit_open")
        raise RuntimeError(f"Circuit breaker open for {tool_name}. Wait and retry.")
    
    current_tool_name = tool_name
    current_tool_start = time.time()
    
    try:
        start = time.time()
        result = tool_fn(*args, **kwargs)
        duration = time.time() - start
        
        record = log_timing(tool_name, duration, "success")
        level = get_level(duration, tool_name)
        
        # Fire alert if needed
        if level != "OK" and not in_cooldown(level):
            from telegram_alerter import fire_alert
            fire_alert(
                level=level if level != "BREAK" else "ALERT",
                signal=f"tool_slow:{tool_name}",
                value=f"{duration:.0f}s",
                action=f"Tool {tool_name} running slow ({level})",
            )
            record_alert(level, f"tool_slow:{tool_name}", f"{duration:.0f}s")
        
        return result, {"duration_s": duration, "status": "success", "level": level}
        
    except Exception as e:
        duration = time.time() - current_tool_start
        log_timing(tool_name, duration, "error", str(e)[:100])
        current_tool_name = None
        current_tool_start = None
        raise

    finally:
        current_tool_name = None
        current_tool_start = None

def timed_tool_call(tool_fn, *args, **kwargs):
    """Alias for with_timing, inferring tool name from fn.__name__."""
    return with_timing(tool_fn.__name__, tool_fn, *args, **kwargs)

# ── Simulate for testing ─────────────────────
if __name__ == "__main__":
    print("Circuit breaker module loaded")
    print(f"State dir: {WATCHDOG_DIR}")
    print(f"Timing file: {TIMING_FILE}")
    print(f"Tool thresholds: {json.dumps(THRESHOLDS, indent=2)}")
    print(f"Tool overrides: {json.dumps(TOOL_OVERRIDES, indent=2)}")
    
    # Simulate a fast call
    def fast_fn():
        time.sleep(0.1)
        return "ok"
    
    result, meta = with_timing("test_fast", fast_fn)
    print(f"\nFast call: {meta}")
    
    # Simulate a slow call
    def slow_fn():
        time.sleep(2)
        return "ok"
    
    # Patch thresholds for test
    old_thresholds = THRESHOLDS.copy()
    THRESHOLDS["BREAK"] = 3  # 3 seconds for testing
    
    try:
        result, meta = with_timing("test_slow", slow_fn)
        print(f"Slow call: {meta}")
    except Exception as e:
        print(f"Slow call error: {e}")
    
    THRESHOLDS.update(old_thresholds)
