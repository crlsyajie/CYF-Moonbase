# CYF Moonbase

A live view of my dev work as a lunar base. Each push to GitHub, and each Claude Code run, sends a cargo crate across the moon between the stations.

- **Habitat**: me
- **Factory**: where every commit gets built and checked, ringed by the **Main Road** that links every station
- **GitHub warehouse** and **Claude warehouse**: hexagon stations at the end of each route
- **Claude Code Workshop** and **Claude Chat Tower**: two hexagons side by side, one for Claude Code sessions, one for claude.ai chats
- **Creative Media Factory**: where Claude's skills run; its rooftop billboard shows the skill in use
- **Formula 1 Paddock**: the F1 GP Predictor; runs of the `f1-gp-update` skill send a crate here and the car races
- **Build site**: an empty pad for the next station

## Live Claude Code activity (local)

`bridge.py` is a tiny local server (Python standard library, 127.0.0.1 only). Claude Code hooks in `~/.claude/settings.json` send it each prompt, tool call and finish. The page connects to it automatically, so while Claude is working the Claude warehouse lights up and shows what it is doing. Each finished turn sends a crate to the habitat, and a `git push`, `git pull`, `gh pr create` or `gh pr merge` run by Claude sends the matching crate. Each skill Claude uses sends a crate from the Claude warehouse through the Creative Media Factory to the habitat.

```bash
python3 bridge.py
```

Then open http://127.0.0.1:8787 (the bridge serves the page too). Without the bridge the page falls back to test mode; each station's panel has buttons to send test crates.

Claude chat (claude.ai) has no hooks. Anything can report a chat by posting `{"type": "chat_start" | "chat", "title": "..."}` to the bridge's `/hook`; the planned Worker will offer this as a claude.ai connector.

Privacy: the bridge never forwards prompt text or full commands, only the event kind, tool name, a file's base name and the project folder name.

## Hosted hub (Cloudflare Workers, free plan)

`worker/` is the hub at https://moonbase.moonbase-hub.workers.dev. It keeps the last 40 crates and relays live events to every open page over WebSockets.

- `POST /github` takes GitHub webhooks (pushes, pull requests, workflow runs), checked against `GITHUB_SECRET`.
- `POST /hook` takes events from `bridge.py`, which forwards everything when `~/.config/moonbase/upstream.json` exists. It needs `INGEST_TOKEN`.
- `GET /ws` is the page's live connection.

Opened from the bridge (127.0.0.1) the page uses the local stream; anywhere else, such as GitHub Pages, it uses the hub. Set `PUBLIC_DETAILS = "false"` in `worker/wrangler.toml` to hide commit messages and chat topics from viewers.

Deploy: `cd worker && npx wrangler deploy` (Node.js and a `wrangler login` first). Secrets live only in Cloudflare and in `~/.config/moonbase/`, never in the repo.

Event format: `{ id, type: "push" | "pull" | "pr" | "merge" | "claude" | "fail" | "skill", title, repo, branch?, sha?, at }`
