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
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("MOONBASE_PORT", "8787"))
# On-demand: the bridge exits after this many minutes with no Claude activity and no page open (0 = never).
IDLE_MIN = float(os.environ.get("MOONBASE_IDLE_MIN", "30"))
last_seen = time.time()
HISTORY_MAX = 40

# Optional: forward every event to the Moonbase hub on Cloudflare, so the hosted page is live too.
# ~/.config/moonbase/upstream.json = {"url": "https://...workers.dev", "token_file": "..."} (written by the setup, kept private)
UPSTREAM = None
try:
    _cfg = json.load(open(os.path.expanduser("~/.config/moonbase/upstream.json")))
    UPSTREAM = (_cfg["url"].rstrip("/") + "/hook", open(os.path.expanduser(_cfg["token_file"])).read().strip())
except Exception:
    pass
outbox = queue.Queue()


def forwarder():
    """Send events to the hub in order. If the network is down (sleep, Wi-Fi change), keep the event and retry
    with growing pauses instead of dropping it; live "working" pulses older than 2 minutes are skipped as stale."""
    while True:
        ev = outbox.get()
        delay = 2
        while True:
            if ev["type"].startswith("claude_") and time.time() - ev.get("_t", time.time()) > 120:
                break
            try:
                body = {k: v for k, v in ev.items() if k != "_t"}
                req = urllib.request.Request(UPSTREAM[0], data=json.dumps(body).encode(), method="POST",
                                             headers={"Content-Type": "application/json", "Authorization": "Bearer " + UPSTREAM[1], "User-Agent": "moonbase-bridge"})
                urllib.request.urlopen(req, timeout=8).read()
                break
            except Exception as e:
                print("hub forward failed, retrying in", delay, "s:", e)
                time.sleep(delay)
                delay = min(delay * 2, 60)

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
    if UPSTREAM:
        outbox.put({**ev, "_t": time.time()})


def git(cwd, *args):
    try:
        return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        return ""


def watch_deploy(remote, sha, name):
    """After a push, follow GitHub's public deployment status for that commit (GitHub Pages, Vercel, Netlify...)
    and launch the rocket when one succeeds. Works without webhooks for public repos; about 20 requests per push."""
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote or "")
    if not m or not sha:
        return
    owner, repo = m.groups()
    get = lambda url: json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "moonbase-bridge"}), timeout=10))
    deadline, seen_any = time.time() + 8 * 60, False
    while time.time() < deadline:
        time.sleep(30)
        try:
            for d in get(f"https://api.github.com/repos/{owner}/{repo}/deployments?sha={sha}&per_page=5"):
                seen_any = True
                states = get(d["statuses_url"])
                if states and states[0].get("state") == "success":
                    emit({"type": "deploy", "title": f"Live · {d.get('environment') or 'production'}", "repo": name, "sha": sha, "id": "deploy-" + sha})
                    return
                if states and states[0].get("state") in ("failure", "error"):
                    return
        except Exception as e:
            print("deploy watch:", e)
        if not seen_any and time.time() > deadline - 5 * 60:  # nothing deploys from this repo
            return


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
        out = [{"type": "claude_start", "title": "Reading your prompt", "repo": repo}]
        # A skill run as a slash command ("/anthropic-skills:cinematic-street-style ...") loads without a tool call,
        # so look at the first word only; nothing else from the prompt is read or sent.
        m = re.match(r"\s*/([A-Za-z0-9_.-]+(?::[A-Za-z0-9_.-]+)?)", str(h.get("prompt") or ""))
        if m and m.group(1) not in ("clear", "compact", "help", "model", "config", "cost", "exit", "resume", "init", "mcp", "memory", "login", "logout", "status", "permissions", "hooks", "agents", "doctor", "review", "rc"):
            skill = m.group(1)
            if skill.endswith("f1-gp-update"):
                out.append({"type": "f1", "title": "F1 prediction updated", "repo": "F1 GP Predictor", "branch": "f1-gp-update"})
            else:
                out.append({"type": "skill", "title": "Skill · " + skill.split(":")[-1], "skill": skill, "repo": repo, "branch": "claude/session"})
        return out

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
                out.append({"type": "skill", "title": "Skill · " + skill.split(":")[-1], "skill": skill, "repo": repo, "branch": "claude/session"})
        return out

    if name == "PostToolUse" and tool == "Bash":
        cmd = str(inp.get("command", ""))
        # Only count a command that actually runs, at the start of the line or after ; && || | (
        # not the same words quoted inside a heredoc or a string.
        bare = re.sub(r"<<-?\s*['\"]?(\w+)['\"]?[^\n]*\n.*?\n\s*\1\b", "", cmd, flags=re.S)  # drop heredoc bodies
        bare = re.sub(r"'[^']*'|\"(?:[^\"\\]|\\.)*\"", "''", bare)  # and quoted text such as commit messages
        ran = lambda c: re.search(r"(?:^|[;&|(]\s*)" + c.replace(" ", r"\s+") + r"\b", bare, re.M) is not None
        gi = h.get("git") or {}  # filled in by hooks/moonbase_hook.py, since this background service can't read ~/Documents
        g = lambda key, *args: gi.get(key) or git(cwd, *args)
        branch = g("branch", "branch", "--show-current")
        out = []
        if ran("git push"):
            head = g("head", "rev-parse", "HEAD")
            out.append({"type": "push", "title": g("subject", "log", "-1", "--format=%s") or "Push", "sha": head, "branch": branch, "repo": repo})
            threading.Thread(target=watch_deploy, args=(g("remote", "remote", "get-url", "origin"), head, repo), daemon=True).start()
        if ran("git pull"):
            out.append({"type": "pull", "title": "Pull " + (g("upstream", "rev-parse", "--abbrev-ref", "@{u}") or "from origin"), "sha": g("head", "rev-parse", "HEAD"), "branch": branch, "repo": repo})
        if ran("gh pr create"):
            out.append({"type": "pr", "title": "PR opened · " + (g("subject", "log", "-1", "--format=%s") or branch), "branch": branch, "repo": repo})
        for tool_cmd in ("wrangler deploy", "vercel --prod", "netlify deploy", "firebase deploy"):
            if ran(tool_cmd):  # PostToolUse only fires when the command succeeded
                out.append({"type": "deploy", "title": "Deployed with " + tool_cmd.split()[0], "repo": repo, "branch": branch})
                break
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
        global last_seen
        last_seen = time.time()
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


def idle_watch():
    while True:
        time.sleep(60)
        with lock:
            busy = bool(clients)
        if busy:
            continue
        if IDLE_MIN and time.time() - last_seen > IDLE_MIN * 60:
            print("idle, stopping"); os._exit(0)


if __name__ == "__main__":
    threading.Thread(target=idle_watch, daemon=True).start()
    if UPSTREAM:
        threading.Thread(target=forwarder, daemon=True).start()
    print(f"Moonbase on http://127.0.0.1:{PORT}{'  + forwarding to ' + UPSTREAM[0] if UPSTREAM else ''}  (page /, hooks → /hook, live feed → /events)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
