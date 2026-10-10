#!/usr/bin/env python3
"""Moonbase local bridge.

Claude Code hooks POST their JSON here (/hook); the Moonbase page listens on /events
(Server-Sent Events). Runs on 127.0.0.1 only, standard library only.

Privacy: prompt text and full shell commands are never forwarded. The page only sees
the event kind, the tool name, a file's base name and the project folder name.

    python3 bridge.py            # listens on 127.0.0.1:8787
"""
import json
import re
import os
import queue
import subprocess
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("MOONBASE_PORT", "8787"))
HISTORY_MAX = 40

history = []          # recent crate events, replayed to new viewers
clients = []          # one queue per open page
lock = threading.Lock()
tool_counts = {}      # tools used per Claude session, for the "finished" crate

VERBS = {
    "Read": "Reading", "Edit": "Editing", "Write": "Writing", "NotebookEdit": "Editing",
    "Bash": "Running a command", "Grep": "Searching", "Glob": "Searching files",
    "WebFetch": "Reading the web", "WebSearch": "Searching the web", "Agent": "Briefing a helper",
    "Skill": "Loading a skill", "ToolSearch": "Loading tools", "TodoWrite": "Planning",
}


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def emit(ev):
    ev.setdefault("id", uuid.uuid4().hex[:12])
    ev.setdefault("at", now_iso())
    with lock:
        if not ev["type"].startswith("claude_"):
            history.insert(0, ev)
            del history[HISTORY_MAX:]
        for q in list(clients):
            q.put(ev)


def git(cwd, *args):
    try:
        return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        return ""


def translate(h):
    # Claude chat (claude.ai) has no hooks; a connector or script can post {"type": "chat_start" | "chat", "title": ...}.
    if h.get("type") in ("chat_start", "chat"):
        return [{"type": h["type"], "title": str(h.get("title") or "Claude chat")[:80], "repo": "claude.ai"}]
    name = h.get("hook_event_name", "")
    cwd = h.get("cwd") or ""
    repo = os.path.basename(cwd.rstrip("/")) or "Claude Code"
    sid = h.get("session_id", "")
    tool = h.get("tool_name", "")
    inp = h.get("tool_input") or {}

    if name == "UserPromptSubmit":
        tool_counts[sid] = 0
        return [{"type": "claude_start", "title": "Reading your prompt", "repo": repo}]

    if name == "PreToolUse":
        tool_counts[sid] = tool_counts.get(sid, 0) + 1
        target = os.path.basename(str(inp.get("file_path") or inp.get("notebook_path") or ""))
        verb = VERBS.get(tool, "Using " + tool.split("__")[-1].replace("_", " "))
        out = [{"type": "claude_tool", "title": verb + (" " + target if target else ""), "repo": repo, "tools": tool_counts[sid]}]
        if tool == "Skill":  # a skill run: the Creative Media Factory gets a crate
            skill = str(inp.get("skill") or "a skill")
            out[0]["title"] = "Using skill " + skill
            if skill.endswith("f1-gp-update"):  # the F1 GP Predictor gets its own hexagon
                out.append({"type": "f1", "title": "F1 prediction updated", "repo": "F1 GP Predictor", "branch": "f1-gp-update"})
            else:
                out.append({"type": "skill", "title": "Skill · " + skill, "skill": skill, "repo": repo, "branch": "claude/session"})
        return out

    if name == "PostToolUse" and tool == "Bash":
        cmd = str(inp.get("command", ""))
        # Only count a command that actually runs, at the start of the line or after ; && || | (
        # not the same words quoted inside a heredoc or a string.
        ran = lambda c: re.search(r"(?:^|[;&|(]\s*)" + c.replace(" ", r"\s+") + r"\b", cmd.split("<<")[0], re.M) is not None
        branch = git(cwd, "branch", "--show-current")
        out = []
        if ran("git push"):
            out.append({"type": "push", "title": git(cwd, "log", "-1", "--format=%s") or "Push", "sha": git(cwd, "rev-parse", "HEAD"), "branch": branch, "repo": repo})
        if ran("git pull"):
            out.append({"type": "pull", "title": "Pull " + (git(cwd, "rev-parse", "--abbrev-ref", "@{u}") or "from origin"), "sha": git(cwd, "rev-parse", "HEAD"), "branch": branch, "repo": repo})
        if ran("gh pr create"):
            out.append({"type": "pr", "title": "PR opened · " + (git(cwd, "log", "-1", "--format=%s") or branch), "branch": branch, "repo": repo})
        if ran("gh pr merge"):
            out.append({"type": "merge", "title": "Merged a pull request", "branch": branch, "repo": repo})
        return out

    if name == "Stop":
        n = tool_counts.pop(sid, 0)
        return [{"type": "claude", "title": f"Claude finished · {n} tool{'s' if n != 1 else ''} used", "repo": repo, "branch": "claude/session"}]

    return []


class Handler(BaseHTTPRequestHandler):
    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self.send_response(204); self.cors(); self.end_headers()

    def do_POST(self):
        if self.path != "/hook":
            self.send_response(404); self.end_headers(); return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0) or 0)) or b"{}")
            for ev in translate(body):
                emit(ev)
        except Exception as e:
            print("bad hook payload:", e)
        self.send_response(204); self.cors(); self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200); self.cors(); self.end_headers(); self.wfile.write(b"ok"); return
        if self.path in ("/", "/index.html"):  # the bridge also serves the page, so Moonbase is one address
            body = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html"), "rb").read()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Cache-Control", "no-cache")
            self.end_headers(); self.wfile.write(body); return
        if self.path != "/events":
            self.send_response(404); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.cors(); self.end_headers()
        q = queue.Queue()
        with lock:
            clients.append(q)
            snapshot = list(history)
        try:
            self.wfile.write(f"event: history\ndata: {json.dumps(snapshot)}\n\n".encode()); self.wfile.flush()
            while True:
                try:
                    ev = q.get(timeout=15)
                    self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode())
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with lock:
                clients.remove(q)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    print(f"Moonbase on http://127.0.0.1:{PORT}  (page /, hooks → /hook, live feed → /events)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
