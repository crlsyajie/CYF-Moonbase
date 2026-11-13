#!/usr/bin/env python3
"""Claude Code Stop hook for the GitHub Watcher (Moonbase Agent Office).

When Claude finishes a turn in a git project with commits GitHub does not have yet, this pushes them (a plain
`git push` of the current branch to its own upstream: never a force push, never a new branch), because Yajie asked
for pushes to go out without a question. Work that is not committed yet is handled the same way: the hook cannot write
a sensible commit message itself, so it hands the turn back to Claude with a standing instruction to commit and push
now, without asking. Set "auto_push": false in the office config to be asked instead. It also tells the GitHub
Watcher's desk what is waiting.
Runs inside Claude Code because the bridge, a background service, cannot read ~/Documents. Errors are ignored.
"""
import json
import os
import subprocess
import sys
import time
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
    lines = [l for l in git("status", "--porcelain").splitlines() if l.strip()]
    dirty, new = len(lines), sorted(l[3:] for l in lines if l.startswith("??"))
    changed = dirty - len(new)                          # files git already tracks that were edited
    subject, name = git("log", "-1", "--format=%s"), os.path.basename(top)
    try:                                                # the Watcher's desk shows what is waiting (names and counts only)
        body = json.dumps({"repo": name, "branch": branch, "ahead": ahead, "dirty": dirty, "subject": subject[:140] if ahead else ""}).encode()
        urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8787/office/pushable", data=body, headers={"Content-Type": "application/json"}), timeout=2).read()
    except Exception:
        pass
    if not (ahead or dirty):
        return                                          # nothing to push
    try:
        auto = json.load(open(os.path.join(DATA, "config.json"))).get("auto_push", True)
    except Exception:
        auto = True
    if ahead and auto and has_upstream and branch:
        r = subprocess.run(["git", "-C", cwd, "push"], capture_output=True, text=True, timeout=25)
        if r.returncode == 0:
            try:
                body = json.dumps({"repo": name, "branch": branch, "ahead": 0, "dirty": dirty, "pushed": ahead}).encode()
                urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8787/office/pushable", data=body, headers={"Content-Type": "application/json"}), timeout=2).read()
            except Exception:
                pass
            print(json.dumps({"systemMessage": "GitHub Watcher pushed %d commit%s of %s (%s) to GitHub." % (ahead, "" if ahead == 1 else "s", name, branch)}))
            return
        # the push did not go through (no network, rejected, sign-in needed): fall through and ask instead
    if h.get("stop_hook_active"):
        return                                          # Claude was already handed this once in this turn
    path = os.path.join(DATA, "push_asked.json")
    try:
        asked = json.load(open(path))
    except Exception:
        asked = {}
    rec = asked.get(top, {})
    if dirty and not ahead and auto and has_upstream and branch:
        # Standing approval: commit and push without a question. New files that were left out before are not raised again.
        fresh = [f for f in new if f not in rec.get("left_out", [])]
        if not (changed or fresh):
            return
        rec["left_out"] = new[-200:]
        asked[top] = rec
        os.makedirs(DATA, exist_ok=True)
        json.dump(asked, open(path, "w"))
        print(json.dumps({"decision": "block", "reason": "GitHub Watcher (Moonbase Agent Office): the project \"%s\" has %d edited file%s%s not committed or pushed. "
                          "The user has given standing approval for this (\"auto_push\" in their office settings), so do it now and do not ask: "
                          "commit the work from this session with a clear message, then `git push` the current branch (%s) to its upstream. "
                          "Rules: never force push; first check the changes for passwords, keys, tokens or private data and leave any such file out; "
                          "only add new files that you created in this session and leave other untracked files alone; if the work is unfinished or broken, "
                          "or the push fails, do not push and say why. Then tell the user in one short line what was pushed."
                          % (name, changed, "" if changed == 1 else "s", (" and %d new file%s" % (len(fresh), "" if len(fresh) == 1 else "s")) if fresh else "", branch)}))
        return
    if ahead and rec.get("sha") != head:
        rec["sha"] = head
        what = "%d commit%s on branch %s that %s not on GitHub yet (latest: \"%s\")" % (ahead, "" if ahead == 1 else "s", branch or "?", "is" if ahead == 1 else "are", subject[:100])
        if dirty:
            what += ", plus %d file%s with uncommitted changes" % (dirty, "" if dirty == 1 else "s")
        ask = "Ask the user one short question: do they want to push now?"
    elif dirty and not ahead and h.get("session_id") not in rec.get("sessions", []) and time.time() - rec.get("asked_at", 0) > 3 * 3600:
        # once per session, and at most once every three hours per project, however many sessions are working in it
        rec["sessions"] = (rec.get("sessions", []) + [h.get("session_id")])[-20:]
        rec["asked_at"] = time.time()
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
