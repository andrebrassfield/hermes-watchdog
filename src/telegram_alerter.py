#!/usr/bin/env python3
"""
hermes-watchdog telegram_alerter.py
Sends formatted alerts to Telegram.
Uses MaxHermes MCP matrix tool when running inside agent,
or direct HTTP call when running standalone.
"""

import json
import os
import sys
import time
import urllib.request
import urllib.parse

# ── Configuration ────────────────────────────────────────────
# TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID should be set as env vars
# or in ~/.hermes/watchdog/config.json

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

ALERT_EMOJI = {
    "OK": "✅",
    "WATCH": "🟡",
    "WARN": "🟠",
    "ALERT": "🔴",
    "CRITICAL": "🚨",
}

ALERT_TEMPLATE = """{emoji} [{level}] Watchdog {ts}
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Signal: {signal}
Value: {value}
Status: {status}
Action: {action}

⏱ Time-to-80%: {t80}min
📍 Last activity: {activity}s ago
🔧 Agent: {agent}"""

def load_config():
    config_path = os.path.expanduser("~/.hermes/watchdog/config.json")
    if os.path.exists(config_path):
        with open(config_path) as f:
            return json.load(f)
    return {}

def send_telegram(text, parse_mode="Markdown"):
    """Send message directly via Telegram Bot API."""
    if not BOT_TOKEN or not CHAT_ID:
        config = load_config()
        token = config.get("telegram_bot_token") or BOT_TOKEN
        chat = config.get("telegram_chat_id") or CHAT_ID
        if not token or not chat:
            print("⚠️ Telegram not configured — alert not sent")
            return False
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": chat,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=urllib.parse.urlencode(data).encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            result = json.loads(r.read())
            return result.get("ok", False)
    except Exception as e:
        print(f"⚠️ Telegram send failed: {e}")
        return False

def fire_alert(level, signal, value, action="Monitor", agent="hermes", t80=None, activity=None):
    """Fire an alert at the given level."""
    if level == "OK":
        return
    
    emoji = ALERT_EMOJI.get(level, "⚠️")
    ts = time.strftime("%H:%M:%S UTC", time.gmtime())
    
    # Format the value string
    if isinstance(value, float):
        value_str = f"{value:.1f}"
    else:
        value_str = str(value)
    
    text = ALERT_TEMPLATE.format(
        emoji=emoji,
        level=level,
        ts=ts,
        signal=signal,
        value=value_str,
        status=f"{level} ({signal})",
        action=action,
        t80=str(round(t80)) if t80 and t80 != float("inf") else "N/A",
        activity=str(activity) if activity else "N/A",
        agent=agent,
    )
    
    print(f"[{level}] {text}")
    return send_telegram(text)

# ── CLI Interface ────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 telegram_alerter.py <level> <signal> <value> [action]")
        sys.exit(1)
    
    level = sys.argv[1].upper()
    signal = sys.argv[2]
    value = sys.argv[3]
    action = sys.argv[4] if len(sys.argv) > 4 else "Monitor"
    
    # Also read health state for extra context
    health_path = os.path.expanduser("~/.hermes/watchdog/health.json")
    health = {}
    if os.path.exists(health_path):
        with open(health_path) as f:
            health = json.load(f)
    
    result = fire_alert(
        level=level,
        signal=signal,
        value=value,
        action=action,
        agent=health.get("agent", "hermes"),
        t80=health.get("time_to_80_min"),
        activity=health.get("last_activity_seconds_ago"),
    )
    
    sys.exit(0 if result else 1)
