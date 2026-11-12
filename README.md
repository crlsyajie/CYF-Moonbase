# CYF Moonbase

A live view of my dev work as a lunar base. Each push to GitHub, and each Claude Code run, sends a cargo crate across the moon between the stations.

- **Habitat**: me
- **Factory**: where every commit gets built and checked, ringed by the **Main Road** that links every station
- **GitHub warehouse** and **Claude warehouse**: hexagon stations at the end of each route
- **Claude Code Workshop** and **Claude Chat Tower**: two hexagons side by side, one for Claude Code sessions, one for claude.ai chats
- **Creative Media Factory**: where Claude's skills run; a party starts there (dance floor, disco ball, dancers, confetti) while a skill runs
- **Formula 1 Garage**: the F1 GP Predictor; runs of the `f1-gp-update` skill send a crate here and the car rolls out onto the apron
- **Launch Pad**: behind the Habitat; every successful deploy (GitHub Pages builds, deployment statuses, or `wrangler`/`vercel`/`netlify`/`firebase` deploys run from Claude Code) launches the rocket
- **Agent Office**: click it to walk inside. Eighteen agents work on three floors on my mail, calendars, AI news, LinkedIn, social media and code; floor 3 is their meeting room (see below)
- **Off-Duty Lounge**: after 10 minutes with no activity I walk here and watch a movie, read or paint; any activity sends me back to work

## Live Claude Code activity (local)

`bridge.py` is a tiny local server (Python standard library, 127.0.0.1 only). Claude Code hooks in `~/.claude/settings.json` send it each prompt, tool call and finish. The page connects to it automatically, so while Claude is working the Claude warehouse lights up and shows what it is doing. Each finished turn sends a crate to the habitat, and a `git push`, `git pull`, `gh pr create` or `gh pr merge` run by Claude sends the matching crate. Each skill Claude uses sends a crate from the Claude warehouse through the Creative Media Factory to the habitat.

```bash
python3 bridge.py
```

Then open http://127.0.0.1:8787 (the bridge serves the page too). Without the bridge the page falls back to test mode; each station's panel has buttons to send test crates.

Claude chat (claude.ai) has no hooks; it reports chats through the hub's MCP connector instead (see below).

Privacy: the bridge never forwards prompt text or full commands, only the event kind, tool name, a file's base name and the project folder name.

## Agent Office (local and private)

`office.py` is a team of agents written from scratch on the Python standard library. The bridge loads it and serves it to the page at `/office/*`.

| Desk | What it does | How it thinks |
| --- | --- | --- |
| Chief of Staff | Runs everyone in order, spots personal/work clashes, writes the briefing | Plain code |
| Mail Sorter (personal, work) | Separates spam from real mail | Its own Naive Bayes model |
| Inbox Analyst (personal, work) | Picks the emails that need me, and says why | Its own Naive Bayes model |
| Scheduler (personal, work) | Today, tomorrow, clashes and free time | Plain code |
| Reply Writer | Drafts a suggested reply for each important email | A local model through Ollama (`llama3.2:3b`); fill-in templates when Ollama is off |
| News Scout | Reads AI news feeds and keeps what matches my interests | Its own Naive Bayes model |
| Follow-up Tracker, Meeting Prep, Deadline Watcher | Quiet threads, context before meetings, due dates in mail | Plain rules |
| Coach | Keeps training the three models: lessons from what really happened in the mailboxes (spam folder, mail I replied to), a re-test of every lesson after each run, and questions for me where a model is unsure | Plain code driving the models |
| GitHub Watcher | Checks my GitHub for new pushes every 10 minutes | GitHub's public API |
| Keymaster | Guards the keys agents need. Values live in the macOS Keychain, go only to the agent a key slot names, every request is logged, and no value ever reaches a report, the page or the writing model | Plain code |
| Yajie's Twin | Asks me questions, keeps my answers, guesses my next answer before asking and keeps score, and passes my writing style to the Reply Writer and my interests to the News Scout | A trait profile and a word-overlap search, both from scratch |

Inside, the office has two floors (keys 1 and 2, or the switch at the bottom left). Floor 1 is the front office: the personal and work mail rooms, the manager's office and a lounge. Floor 2 is the workshop: the open workspace, the vault, the training room, the twin's study and the dev room. The Chief walks to whoever is working, by corridor and lift.

Keys: a slot in `config.json` (`"keys"`) names which agent may ask for which key. Add a value yourself with `security add-generic-password -U -s moonbase-office -a <name> -w`, which asks for it in the terminal. Website passwords do not belong here; no agent signs in to a website.

The three models are defined and trained in `office.py`: they start from a small starter set and learn from every correction made in the office ("Not spam", "This is important", "Not for me"). Personal is Gmail, work is Outlook; each has its own agents.

Everything the office keeps lives in `~/.local/share/moonbase-office/` (owner-only files, outside this repo): `config.json` (interests, news feeds, important senders, daily run time, writing model), `models.json`, `inbox/<wing>/mail.json` and `calendar.json`, and the last reports. Until mail is delivered for a wing, its agents work on made-up practice mail and say so.

Other endpoints: `POST /office/answer` (an answer for the twin) and `POST /office/ask` (a question for the twin).

Mail and calendars are delivered to the agents, they never fetch them: `POST /office/ingest` with `{ "wing": "personal" | "work", "kind": "mail" | "calendar", "items": [...] }`, or `python3 office.py ingest personal mail file.json`. Mail items take `from`, `subject`, `body` or `snippet`, `date`, and optionally `thread_id`, `sent`, `labels`; calendar items take `title`, `start`, `end`, `attendees`, `location`.

Privacy: office reports are served only to the page on 127.0.0.1 (requests from any other website or host name are refused), are never passed to the hub, and never appear on the hosted page, which draws the office with every report hidden.

```bash
python3 office.py run      # run the team once in the terminal and print the briefing
```

## Hosted hub (Cloudflare Workers, free plan)

`worker/` is the hub at https://moonbase.moonbase-hub.workers.dev. It keeps the last 40 crates and relays live events to every open page over WebSockets.

- `POST /github` takes GitHub webhooks (pushes, pull requests, workflow runs), checked against `GITHUB_SECRET`.
- `POST /hook` takes events from `bridge.py`, which forwards everything when `~/.config/moonbase/upstream.json` exists. It needs `INGEST_TOKEN`.
- `POST /mcp/<MCP_KEY>` is a tiny MCP server, added to claude.ai as a custom connector, so Claude Chat can report chats (`moonbase_chat_started`, `moonbase_skill_used`, `moonbase_chat_finished`); skills used in a chat go to the Creative Media Factory, or the F1 Garage for `f1-gp-update`. The key in the address keeps it private.
- `GET /ws` is the page's live connection. The hub also counts open pages and sends a live "N watching" count; each viewer appears as a visitor astronaut on the base.

Opened from the bridge (127.0.0.1) the page uses the local stream; anywhere else, such as GitHub Pages, it uses the hub. Set `PUBLIC_DETAILS = "false"` in `worker/wrangler.toml` to hide commit messages and chat topics from viewers.

Deploy: `cd worker && npx wrangler deploy` (Node.js and a `wrangler login` first). Secrets live only in Cloudflare and in `~/.config/moonbase/`, never in the repo.

Event format: `{ id, type: "push" | "pull" | "pr" | "merge" | "claude" | "fail" | "skill", title, repo, branch?, sha?, at }`
