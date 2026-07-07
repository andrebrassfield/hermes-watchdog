#!/usr/bin/env python3
"""
hermes-watchdog session_rescue.py
Session backup and rescue logic.
Snapshots current state to GitHub, enables recovery after crashes.
"""

import json
import os
import time
import urllib.request
import urllib.parse
import base64
from pathlib import Path
from datetime import datetime

WATCHDOG_DIR = Path.home() / ".hermes" / "watchdog"
SNAPSHOT_DIR = WATCHDOG_DIR / "snapshots"
GITHUB_REPO = "andrebrassfield/hermes-watchdog"
GITHUB_PAT = os.environ.get("GITHUB_WATCHDOG_PAT", "")

WATCHDOG_DIR.mkdir(parents=True, exist_ok=True)

# ── Snapshot ────────────────────────────────
def create_snapshot(reason="manual", session_id=None):
    """Create a full session state snapshot."""
    
    if session_id is None:
        session_id = os.environ.get("HERMES_SESSION_ID", f"session_{int(time.time())}")
    
    snapshot = {
        "id": f"{session_id}_{int(time.time())}",
        "reason": reason,
        "ts": datetime.utcnow().isoformat() + "Z",
        "session_id": session_id,
        
        # Context
        "context_percent": read_context_percent(),
        
        # Tool timing
        "tool_timing": read_recent_timing(20),
        
        # Activity
        "last_activity_ts": read_last_activity(),
        
        # Recent history
        "context_history": read_context_history(50),
        
        # Health
        "health": read_health(),
    }
    
    # Save locally
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    local_path = SNAPSHOT_DIR / f"{snapshot['id']}.json"
    with open(local_path, "w") as f:
        json.dump(snapshot, f, indent=2)
    
    # Push to GitHub
    push_to_github(snapshot)
    
    return snapshot, local_path

def read_context_percent():
    health = read_health()
    return health.get("context_percent", 0)

def read_health():
    health_file = WATCHDOG_DIR / "health.json"
    if health_file.exists():
        with open(health_file) as f:
            return json.load(f)
    return {}

def read_last_activity():
    activity_file = WATCHDOG_DIR / "activity.json"
    if activity_file.exists():
        with open(activity_file) as f:
            return json.load(f).get("last_activity_ts")
    return None

def read_context_history(n=50):
    state_file = WATCHDOG_DIR / "state.jsonl"
    if not state_file.exists():
        return []
    with open(state_file) as f:
        lines = f.readlines()
    history = []
    for line in lines[-n:]:
        try:
            history.append(json.loads(line))
        except:
            pass
    return history

def read_recent_timing(n=20):
    timing_file = WATCHDOG_DIR / "tool_timing.jsonl"
    if not timing_file.exists():
        return []
    with open(timing_file) as f:
        lines = f.readlines()
    timing = []
    for line in lines[-n:]:
        try:
            timing.append(json.loads(line))
        except:
            pass
    return timing

def push_to_github(snapshot):
    """Push snapshot to hermes-watchdog/snapshots/ via GitHub API."""
    if not GITHUB_PAT:
        print("⚠️ GITHUB_WATCHDOG_PAT not set — skipping GitHub push")
        return
    
    path = f"snapshots/{snapshot['id']}.json"
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{urllib.parse.quote(path)}"
    
    # Check if exists
    sha = None
    req = urllib.request.Request(url, headers=headers())
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            sha = json.loads(r.read()).get("sha")
    except:
        pass
    
    body = {
        "message": f"snapshot: {snapshot['reason']} — {snapshot['id']}",
        "content": base64.b64encode(json.dumps(snapshot, indent=2).encode()).decode(),
        "branch": "main"
    }
    if sha:
        body["sha"] = sha
    
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers=headers(),
        method="PUT"
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            print(f"✓ Snapshot pushed to GitHub: {path}")
    except Exception as e:
        print(f"⚠️ GitHub push failed: {e}")

def headers():
    return {
        "Authorization": f"token {GITHUB_PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json"
    }

# ── Rescue ─────────────────────────────────
def list_snapshots():
    """List all local snapshots, newest first."""
    SNAPSHOT_DIR.mkdir(exist_ok=True)
    files = sorted(SNAPSHOT_DIR.glob("*.json"), key=os.path.getmtime, reverse=True)
    return [f.name for f in files]

def load_snapshot(snapshot_id):
    """Load a snapshot by ID."""
    path = SNAPSHOT_DIR / f"{snapshot_id}.json"
    if path.exists():
        with open(path) as f:
            return json.load(f)
    
    # Try GitHub
    return load_snapshot_from_github(snapshot_id)

def load_snapshot_from_github(snapshot_id):
    path = f"snapshots/{snapshot_id}.json"
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{urllib.parse.quote(path)}"
    req = urllib.request.Request(url, headers=headers())
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
            content = base64.b64decode(data["content"]).decode()
            return json.loads(content)
    except Exception as e:
        print(f"⚠️ Could not load snapshot from GitHub: {e}")
        return None

def restore_from_snapshot(snapshot):
    """Restore session from a snapshot."""
    print(f"Restoring from snapshot: {snapshot['id']}")
    print(f"  Reason: {snapshot['reason']}")
    print(f"  Context: {snapshot['context_percent']}%")
    print(f"  Session: {snapshot['session_id']}")
    
    # Load context history into state.jsonl
    state_file = WATCHDOG_DIR / "state.jsonl"
    with open(state_file, "w") as f:
        for event in snapshot.get("context_history", []):
            f.write(json.dumps(event) + "\n")
    
    # Load tool timing
    timing_file = WATCHDOG_DIR / "tool_timing.jsonl"
    with open(timing_file, "w") as f:
        for event in snapshot.get("tool_timing", []):
            f.write(json.dumps(event) + "\n")
    
    return snapshot

# ── CLI ────────────────────────────────────
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 session_rescue.py snapshot [reason]")
        print("  python3 session_rescue.py list")
        print("  python3 session_rescue.py restore <snapshot_id>")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "snapshot":
        reason = sys.argv[2] if len(sys.argv) > 2 else "manual"
        snap, path = create_snapshot(reason=reason)
        print(f"✓ Snapshot created: {path}")
        print(json.dumps(snap, indent=2))
    
    elif cmd == "list":
        snaps = list_snapshots()
        print(f"Found {len(snaps)} snapshots:")
        for s in snaps[:10]:
            print(f"  {s}")
    
    elif cmd == "restore":
        if len(sys.argv) < 3:
            print("Usage: session_rescue.py restore <snapshot_id>")
            sys.exit(1)
        snapshot = load_snapshot(sys.argv[2])
        if snapshot:
            restore_from_snapshot(snapshot)
            print("✓ Session restored")
        else:
            print("⚠️ Snapshot not found")
    
    else:
        print(f"Unknown command: {cmd}")
