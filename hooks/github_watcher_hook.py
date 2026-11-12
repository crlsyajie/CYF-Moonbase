#!/usr/bin/env python3
"""Claude Code Stop hook for the GitHub Watcher (Moonbase Agent Office).

When Claude finishes a turn in a git project that has work GitHub does not have yet, this makes Claude ask Yajie
one question, "push this?", before it stops. It never pushes anything itself, and it asks once per new commit (or once
per session for uncommitted work), so saying no is remembered. It also tells the GitHub Watcher's desk what is waiting.
Runs inside Claude Code because the bridge, a background service, cannot read ~/Documents. Errors are ignored.
"""
import json
import os
import subprocess
import sys
import urllib.request

DATA = os.path.expanduser(os.environ.get("MOONBASE_OFFICE_DATA", "~/.local/share/moonbase-office"))


def main():
    h = json.load(sys.stdin)
    cwd = h.get("cwd") or ""
    if not cwd:
        return

    def git(*args):
        r = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=3)
        return r.stdout.strip() if r.returncode == 0 else ""

    top = git("rev-parse", "--show-toplevel")
    if not top or not git("remote"):
        return                                          # not a git project, or nowhere to push to
    head, branch = git("rev-parse", "HEAD"), git("branch", "--show-current")
    has_upstream = bool(git("rev-parse", "--abbrev-ref", "@{u}"))
    ahead = int((git("rev-list", "--count", "@{u}..HEAD") if has_upstream else git("rev-list", "--count", "HEAD", "--not", "--remotes")) or 0)
    dirty = len([l for l in git("status", "--porcelain").splitlines() if l.strip()])
    subject, name = git("log", "-1", "--format=%s"), os.path.basename(top)
    try:                                                # the Watcher's desk shows what is waiting (names and counts only)
        body = json.dumps({"repo": name, "branch": branch, "ahead": ahead, "dirty": dirty, "subject": subject[:140] if ahead else ""}).encode()
        urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8787/office/pushable", data=body, headers={"Content-Type": "application/json"}), timeout=2).read()
    except Exception:
        pass
    if h.get("stop_hook_active") or not (ahead or dirty):
        return                                          # already asked this turn, or nothing to push
    path = os.path.join(DATA, "push_asked.json")
    try:
        asked = json.load(open(path))
    except Exception:
        asked = {}
    rec = asked.get(top, {})
    if ahead and rec.get("sha") != head:
        rec["sha"] = head
        what = "%d commit%s on branch %s that %s not on GitHub yet (latest: \"%s\")" % (ahead, "" if ahead == 1 else "s", branch or "?", "is" if ahead == 1 else "are", subject[:100])
        if dirty:
            what += ", plus %d file%s with uncommitted changes" % (dirty, "" if dirty == 1 else "s")
        ask = "Ask the user one short question: do they want to push now?"
    elif dirty and not ahead and rec.get("session") != h.get("session_id"):
        rec["session"] = h.get("session_id")
        what = "%d file%s with changes that are not committed or pushed" % (dirty, "" if dirty == 1 else "s")
        ask = "Ask the user one short question: do they want you to commit and push this work now?"
    else:
        return
    asked[top] = rec
    os.makedirs(DATA, exist_ok=True)
    json.dump(asked, open(path, "w"))
    print(json.dumps({"decision": "block", "reason": "GitHub Watcher (Moonbase Agent Office): the project \"%s\" has %s. %s Do not commit or push unless they say yes; "
                      "if they say no, do nothing more about it. If you already asked this in your last message, do not ask again." % (name, what, ask)}))


try:
    main()
except Exception:
    pass
