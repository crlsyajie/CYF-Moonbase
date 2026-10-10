// Moonbase hub on Cloudflare Workers: keeps the recent crates and relays live events to every open page.
//
//   POST /hook    events already translated by bridge.py ({ type, title, repo, ... }); needs "Authorization: Bearer <INGEST_TOKEN>"
//   POST /github  GitHub webhooks (push, pull_request, workflow_run); checked against GITHUB_SECRET
//   GET  /ws      the page's live connection: first {kind: "history", events}, then {kind: "event", event} as they happen
//
// One Durable Object ("Hub") holds the history and the open WebSockets. It uses the hibernation API,
// so idle connections cost nothing on the free plan.

const CORS = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Content-Type, Authorization', 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS' };
const TYPES = new Set(['push', 'pull', 'pr', 'merge', 'fail', 'claude', 'skill', 'f1', 'chat', 'chat_start', 'claude_start', 'claude_tool']);
const LIVE_ONLY = new Set(['claude_start', 'claude_tool', 'chat_start']); // activity pulses, not crates: never stored

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (req.method === 'OPTIONS') return new Response(null, { headers: CORS });
    const hub = env.HUB.get(env.HUB.idFromName('moonbase'));

    if (url.pathname === '/ws') return hub.fetch(req);

    if (url.pathname === '/hook' && req.method === 'POST') {
      if (!env.INGEST_TOKEN || req.headers.get('Authorization') !== `Bearer ${env.INGEST_TOKEN}`) return new Response('unauthorized', { status: 401, headers: CORS });
      const body = await req.json().catch(() => null);
      for (const ev of (Array.isArray(body) ? body : [body]).map(clean).filter(Boolean)) await emit(hub, ev);
      return new Response(null, { status: 204, headers: CORS });
    }

    if (url.pathname === '/github' && req.method === 'POST') {
      const raw = await req.text();
      if (!(await signed(env.GITHUB_SECRET, raw, req.headers.get('X-Hub-Signature-256')))) return new Response('bad signature', { status: 401 });
      for (const ev of fromGitHub(req.headers.get('X-GitHub-Event'), JSON.parse(raw)).map(clean).filter(Boolean)) await emit(hub, ev);
      return new Response('ok');
    }

    if (url.pathname === '/') return new Response('Moonbase hub is running.', { headers: CORS });
    return new Response('not found', { status: 404, headers: CORS });
  },
};

const emit = (hub, ev) => hub.fetch('https://hub/emit', { method: 'POST', body: JSON.stringify(ev) });

function clean(e) {
  if (!e || !TYPES.has(e.type)) return null;
  const s = (v, n) => (v == null || v === '' ? undefined : String(v).slice(0, n));
  return {
    id: s(e.id, 40) || crypto.randomUUID().slice(0, 12), type: e.type, title: s(e.title, 120), repo: s(e.repo, 60),
    branch: s(e.branch, 60), sha: s(e.sha, 40), skill: s(e.skill, 60), tools: Number.isFinite(e.tools) ? e.tools : undefined,
    at: s(e.at, 30) || new Date().toISOString(),
  };
}

function fromGitHub(kind, p) {
  const repo = p.repository?.name;
  if (kind === 'push' && p.head_commit) return [{ type: 'push', title: p.head_commit.message.split('\n')[0], repo, branch: (p.ref || '').replace('refs/heads/', ''), sha: p.after, id: 'gh-' + p.after }];
  if (kind === 'pull_request') {
    const pr = p.pull_request;
    if (p.action === 'opened') return [{ type: 'pr', title: `PR #${pr.number} · ${pr.title}`, repo, branch: pr.head?.ref }];
    if (p.action === 'closed' && pr.merged) return [{ type: 'merge', title: `Merged PR #${pr.number} · ${pr.title}`, repo, branch: pr.base?.ref, sha: pr.merge_commit_sha }];
  }
  if (kind === 'workflow_run' && p.action === 'completed' && p.workflow_run?.conclusion === 'failure')
    return [{ type: 'fail', title: `Build failed · ${p.workflow_run.name}`, repo, branch: p.workflow_run.head_branch, sha: p.workflow_run.head_sha }];
  return [];
}

async function signed(secret, body, sig) {
  if (!secret || !sig) return false;
  const key = await crypto.subtle.importKey('raw', new TextEncoder().encode(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const mac = new Uint8Array(await crypto.subtle.sign('HMAC', key, new TextEncoder().encode(body)));
  const want = 'sha256=' + [...mac].map(b => b.toString(16).padStart(2, '0')).join('');
  if (want.length !== sig.length) return false;
  let diff = 0; for (let i = 0; i < want.length; i++) diff |= want.charCodeAt(i) ^ sig.charCodeAt(i);
  return diff === 0;
}

export class Hub {
  constructor(state, env) {
    this.state = state; this.env = env;
    // Keep-alive pings are answered by Cloudflare without waking the hub, so idle viewers use no compute time.
    state.setWebSocketAutoResponse(new WebSocketRequestResponsePair('ping', 'pong'));
  }

  async fetch(req) {
    const url = new URL(req.url);
    if (url.pathname === '/ws') {
      if (req.headers.get('Upgrade') !== 'websocket') return new Response('expected a websocket', { status: 426 });
      const [client, server] = Object.values(new WebSocketPair());
      this.state.acceptWebSocket(server);
      server.send(JSON.stringify({ kind: 'history', events: (await this.state.storage.get('history')) || [] }));
      return new Response(null, { status: 101, webSocket: client });
    }
    if (url.pathname === '/emit') {
      const ev = this.redact(await req.json());
      if (!LIVE_ONLY.has(ev.type)) {
        const h = (await this.state.storage.get('history')) || [];
        if (h.some(x => x.id === ev.id)) return new Response(null, { status: 204 }); // the same push can arrive from the bridge and from GitHub
        h.unshift(ev); await this.state.storage.put('history', h.slice(0, 40));
      }
      const msg = JSON.stringify({ kind: 'event', event: ev });
      for (const ws of this.state.getWebSockets()) { try { ws.send(msg); } catch {} }
      return new Response(null, { status: 204 });
    }
    return new Response('not found', { status: 404 });
  }

  // PUBLIC_DETAILS = "false" hides commit messages, repo names and chat topics from viewers.
  redact(ev) {
    if (this.env.PUBLIC_DETAILS !== 'false') return ev;
    const { title, repo, branch, sha, skill, ...rest } = ev;
    return rest;
  }

  webSocketMessage(ws, msg) { if (msg === 'ping') ws.send('pong'); }
  webSocketClose(ws, code) { try { ws.close(code, 'bye'); } catch {} }
}
