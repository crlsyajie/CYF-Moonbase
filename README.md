# CYF Moonbase

A live view of my dev work as a lunar base. Each push to GitHub, and each Claude Code run, sends a cargo crate across the moon between the stations.

- **Habitat**: me
- **Factory**: where every commit gets built and checked
- **GitHub warehouse** and **Claude warehouse**: hexagon stations at the end of each route
- **Build sites**: empty pads for future stations

## Status

The front end is done (`index.html`, plain HTML/CSS/JS, no build step). For now, crates only move when you press the test buttons.

Next: a Cloudflare Worker that takes GitHub webhooks and a Claude Code hook, and streams events to the page. Then set `FEED_URL` in `index.html`.

Event format: `{ id, type: "push" | "pull" | "pr" | "merge" | "claude" | "fail", title, repo, branch?, sha?, at }`
