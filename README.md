# HP3000 Hacker Replicant

An AI tutor/copilot that sits next to a Raspberry Pi-hosted HP3000 Series II
replica: a web page with the real terminal console on the left, and a chat
panel on the right that knows MPE (Hewlett-Packard's "Multi-Programming
Executive") and the HP3000's stack-machine architecture and history — and,
if you let it, can type into the console itself.

This is part of a small family of "Hacker Replicant" packages built for
different retrocomputing replicas; this one is HP3000/MPE-specific, but the
pattern (a tiny `screen`-reading boot-API + a chat panel + an LLM backend)
is reusable for other machines too.

Unlike some of its siblings, this repo does **not** bundle a web console —
see "Bring your own console" below for why, and what to point it at.

## How it works

```
Browser
 │
 ├─ Left panel:  <iframe> → CONSOLE_URL (your own existing web console)
 │
 └─ Right panel: chat → POST /api/chat (SSE stream)
      │  this Node service (server.js)
      │
      ├─ LLM backend: any OpenAI-compatible /chat/completions API
      │  (local Ollama by default, or a hosted provider -- see below)
      │
      └─ when the control toggle is ON, two tools only:
           send_keys   → POST  <BOOTAPI_BASE>/keys    {"text": "..."}
           read_screen → GET   <BOOTAPI_BASE>/screen
           (served by hp3000-bootapi.py, included in this repo)
```

There's no SIMH API involved anywhere. The machine's console runs inside a
GNU `screen` session (named `hp3000` by default); the chat agent's tools
talk to that session via two simple, stateless `screen` primitives:

- `screen -X stuff <text>` — types text into the session, as if someone
  sat down and typed it.
- `screen -X hardcopy <file>` — writes a plain-text snapshot of the current
  screen contents to a file, which the boot-API reads back.

That's the entire "control" surface for the agent: no shell access, no
filesystem access, nothing beyond what's visible in the same terminal your
own web console already shows.

## Bring your own console

This repo includes the chat backend and the boot-API, but not a web
console app for the left panel. That's a deliberate difference from some of
the other Hacker Replicant packages: the original internal build's left
panel pointed at an existing HP3000 web console that isn't part of this
project and isn't generic enough to publish as a template here.

Point `CONSOLE_URL` at whatever you're already using to show/drive the
HP3000 terminal in a browser — a `screen`-to-xterm.js bridge, ttyd, a
telnet-to-websocket proxy, anything that gives you a page or endpoint you
can embed in an `<iframe>`. If you don't have one yet, the `webconsole/`
FastAPI app from the sibling PiDP-11 Hacker Replicant package (a small
`screen -x <session>` over a WebSocket into xterm.js) is a reasonable
starting point — swap the session name and you're most of the way there.

The chat panel and the boot-API don't care what's actually driving the left
panel; they only need `CONSOLE_URL` for the iframe/back-link, and
`BOOTAPI_BASE` for the agent's own read/type access.

## LLM-agnostic by design

The chat backend talks to **any backend that speaks the OpenAI-compatible
`/chat/completions` API with tool/function calling** — that's one code
path for both:

- **Local** (default, free): point it at a local [Ollama](https://ollama.com)
  install. Ollama has spoken this API since mid-2024, nothing extra to
  configure beyond pulling a model that supports tool calling (`qwen3`,
  `llama3.1`+, `mistral-nemo`, etc. all do).
- **Cloud** (optional, for a faster/smarter option): point it at OpenAI,
  Groq, Together, Fireworks, DeepSeek, Mistral, OpenRouter, a hosted
  vLLM/TGI endpoint — anything OpenAI-compatible. See `.env.example` for
  examples.

No vendor SDK, no hard dependency on any single provider, no API key
required at all if you only use the local backend.

**A heads-up on local "thinking" models:** Ollama's OpenAI-compatible
endpoint (what the local backend uses) doesn't currently expose a way to
turn off a reasoning model's internal "thinking" step the way Ollama's own
native API does (`think: false`). For `qwen3` specifically this means every
reply carries a few hundred tokens of hidden reasoning, adding roughly
10-20 extra seconds per turn. `LLM_TIMEOUT_MS` already accounts for this
(default 180s), so nothing breaks, it just feels slower than it has to. If
snappier replies matter more to you than using a reasoning model locally,
point `LOCAL_MODEL` at a non-thinking model instead (`llama3.1`,
`mistral-nemo`, etc. all support tool calling without this overhead).

## Setup

### Prerequisites

- GNU `screen`, installed on the Pi running the HP3000 replica
  (`apt install screen` on Debian/Raspberry Pi OS if it isn't already).
  `hp3000-bootapi.py` shells out to it directly.
- A SIMH-based HP3000 Series II simulation running MPE, inside a named
  `screen` session (default: `hp3000`).
- Your own existing web console pointed at that same session (see "Bring
  your own console" above).
- Node.js 18+ and Python 3 on the host running the boot-API.
- [Ollama](https://ollama.com) running somewhere reachable (for the free
  local backend), or an API key for a cloud provider.

The chat backend can run anywhere and just point `CONSOLE_URL`/
`BOOTAPI_BASE` at the HP3000's host over the network. The boot-API needs to
run on that host itself (it shells out to `screen` directly).

### Install

```bash
git clone <this-repo-url>
cd hp3000-hacker-replicant
npm install
cp .env.example .env
# edit .env: at minimum set CONSOLE_URL and BOOTAPI_BASE to match your setup
```

### Run the boot-API (on the HP3000's host, bridges the chat agent to the console)

```bash
python3 hp3000-bootapi.py
```

Edit the `SESSIONS` dict at the top of `hp3000-bootapi.py` if your `screen`
session isn't named `hp3000`.

### Run the chat backend (right panel)

```bash
npm start
```

Open `http://<host>:8097/` (or whatever `PORT` you set) — `CONSOLE_URL`
should point at your own web console (e.g. `http://<pi-host>:8080`).

### Running as services

See `docs/hp3000-bootapi.service.example` and
`docs/hp3000-hacker-replicant.service.example` for ready-to-adapt systemd
units.

## Configuration reference

All configuration is environment variables — see `.env.example` for the
full list with examples. The short version:

| Variable | What |
|---|---|
| `PORT` | Port the chat backend listens on |
| `CONSOLE_URL` | Your existing web console, shown in the left panel |
| `BOOTAPI_BASE` | Where `hp3000-bootapi.py` is reachable |
| `ACTION_LIMIT` | Tool calls per turn before the agent must ask to continue |
| `LOCAL_BASE_URL` / `LOCAL_API_KEY` / `LOCAL_MODEL` | Local (default) backend |
| `CLOUD_BASE_URL` / `CLOUD_API_KEY` / `CLOUD_MODEL` | Optional cloud backend |

## Safety model

- The control toggle is **off** on every page load — by default the agent
  only talks, it never touches the machine.
- When on, the agent gets exactly two tools (`send_keys`, `read_screen`),
  nothing else — no shell, no filesystem, no network access beyond the
  boot-API.
- After `ACTION_LIMIT` tool calls in one turn, the agent is cut off from
  further tool calls and must ask in plain text whether it may continue —
  no silent, unbounded action streak. A hard iteration cap (20) sits
  underneath as a defensive backstop against a broken loop.
- Everything the agent types is visible live in the same terminal session
  your own web console shows — no black box.
- This does **not** protect you from the agent typing something wrong (it's
  an LLM, it can make mistakes) — the boundary is on *what* it can touch,
  not on *how well* it types. Use a local/free backend if you want to
  experiment without any cost risk.
- The included `skills/mpe-tutor.md` describes a demo HP3000 configured for
  frictionless exploration: logging in via `HELLO MANAGER.SYS` with no
  password. That's a reasonable default for a machine meant to be freely
  explored by visitors — if your own replica holds anything you care about,
  set a real password and update the skill file accordingly.

## About the HP3000 and MPE

The HP3000 (1972) ran **MPE — Multi-Programming Executive** — HP's
business-oriented operating system, a world away from the more
scientific/academic reputation of contemporary PDP and VAX systems. A few
things that make it worth a tutor of its own:

- **A stack machine, not a register machine.** Unlike the PDP-8, PDP-10,
  PDP-11, or VAX, the HP3000 has no general-purpose register bank: local
  variables, parameters, and intermediate results all live on a hardware
  stack (4 top-of-stack registers with microcode-driven spill/fill to
  memory), closer in spirit to the Burroughs B5000 or a Forth machine than
  to anything DEC built.
- **A 3-level file hierarchy** (`ACCOUNT → GROUP → file`, fully qualified
  as `filename.groupname.accountname`) that looks nothing like a Unix
  filesystem, plus MPE's own job-control language for batch work
  (`!JOB` / `!EOJ`, submitted via `STREAM`).
- **IMAGE/TurboIMAGE**, a network/hierarchical database bundled free with
  the OS since 1972 — a big part of the platform's commercial success,
  underpinning early ERP systems like MANMAN.
- **An unusually long production life**: HP announced end-of-life in 2001,
  but official support didn't end until 2010, and plenty of MPE/iX shops
  kept running (often via hardware emulation) for years after that.

`skills/mpe-tutor.md` is the system prompt driving all of this — MPE
commands (`LISTF`, `FCOPY`, `RUN`, `STREAM`, UDCs), the COOLSTART/
WARMSTART/COLDSTART distinction, and the platform's history (including its
brief 1978 stint as the first computer in the White House). It's written in
Dutch, matching the author's own working language; translate it if you'd
prefer an English-only persona.

## Repository layout

```
server.js               Chat backend (Node/Express, SSE, LLM-agnostic)
public/                 Chat panel UI (right side)
hp3000-bootapi.py        screen -X stuff/hardcopy bridge for the chat agent's tools
skills/mpe-tutor.md      System prompt: MPE/HP3000 knowledge + behavior rules (Dutch)
docs/                    Example systemd units (not installed automatically)
```

## Adapting this for a different replica

`hp3000-bootapi.py` is deliberately small and machine-specific only in its
`SESSIONS` entries — it's a reasonable starting point for wiring up the
same pattern on a different PDP/VAX/HP/whatever replica: same two
primitives (`screen -X stuff` / `screen -X hardcopy`), same tiny HTTP
wrapper. The `SESSIONS` dict can hold more than one `{name: session}` pair
if you ever co-locate multiple simulators on the same host — each gets its
own `/api/<name>/screen` and `/api/<name>/keys` for free. For a
single-machine HP3000 setup, the `hp3000` entry is all you need.

`skills/mpe-tutor.md` is the only file that's actually HP3000/MPE-specific
content; swap it for a system prompt about your own machine and point
`server.js` at the new file.

## Credits

Built by Rolf Peters with Seb (his homelab AI assistant). Unlike the
PDP-series replicas in this family, the HP3000 replica this was built
against is not one of Oscar Vermeulen's PiDP kits — there is no commercial
or hobbyist HP3000 front-panel replica design being credited here; this
project is just the SIMH-based HP3000/MPE simulation plus this chat layer.

## License

MIT — see `LICENSE`.
