#!/usr/bin/env python3
"""Claude Code PostToolUse(Bash) hook for Moonbase.

Runs inside Claude Code (which can read your repos), adds the git details the bridge needs for push, pull and
deploy tracking, and posts the payload to the local bridge. The bridge runs as a background service and macOS
won't let it read ~/Documents, so it can't look these up itself. Never blocks Claude: errors are ignored.
"""
import json
import subprocess
import sys
import urllib.request

try:
    h = json.load(sys.stdin)
    cmd = str((h.get("tool_input") or {}).get("command", ""))
    cwd = h.get("cwd")
    if cwd and any(k in cmd for k in ("git push", "git pull", "gh pr", "deploy", "--prod")):
        def git(*args):
            return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=3).stdout.strip()
        h["git"] = {"head": git("rev-parse", "HEAD"), "subject": git("log", "-1", "--format=%s"), "branch": git("branch", "--show-current"),
                    "remote": git("remote", "get-url", "origin"), "upstream": git("rev-parse", "--abbrev-ref", "@{u}")}
    req = urllib.request.Request("http://127.0.0.1:8787/hook", data=json.dumps(h).encode(), headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=2).read()
except Exception:
    pass
