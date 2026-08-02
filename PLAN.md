# Decision Window — Today’s Build Plan

**Target:** a live, public MVP in 6–7 hours.

**Current state:** the public UI and token function are deployed at `https://decision-window.pages.dev/`; the Python worker runs as a managed LiveKit Cloud agent in `us-east`. Per-track Inworld STT, contextual routing, bounded Bright Data/OpenAI research, queued TTS, reconnect handling, and audio health telemetry are implemented and live-tested. Rotate any credentials that were exposed during early setup.

## End-of-day acceptance test

The build is done only when this exact flow works twice in a row:

1. Two browsers join the same public, audio-only room with different names.
2. Both participants hear each other.
3. Each microphone is transcribed independently and shown with the correct participant name.
4. A participant says: **“Decision Window, verify whether LiveKit can be self-hosted.”**
5. The UI immediately shows a `QUICK` research job and a visible 30-second deadline.
6. Bright Data retrieves live public evidence; OpenAI produces a concise grounded answer.
7. A card appears first with answer, source titles, and URLs.
8. A participant releases the queued answer and hears a concise response through Inworld TTS.
9. A human starts speaking while the agent speaks; the agent stops.
10. A deliberately delayed result is marked `EXPIRED` and is never spoken.

The research input remains generic: the rehearsed LiveKit question proves reliability, but any explicit public-web question can use the same path.

## Scope locked for today

### Required

- React/Vite frontend on Cloudflare Pages with one `/api/token` Pages Function
- LiveKit Cloud audio room with separate participant tracks
- Managed Python worker deployed to LiveKit Cloud; local mode remains available for development
- One Inworld streaming STT stream per human track
- Speaker-labelled partial/final transcripts
- LLM router evaluates every final turn against the last 16 speaker-labelled turns
- Human-first grace period defers routing while another participant answers; resolved questions are ignored
- Explicit wake phrase remains a deterministic fallback, not the primary route
- `INSTANT` for stable common knowledge; `QUICK` with a deterministic 30-second deadline for current evidence
- Bright Data search with one result on `QUICK` to absorb provider tail latency
- OpenAI synthesis receives retrieved evidence plus the same transcript snapshot
- Cited answer card before voice output
- Multiple pending answer cards with per-answer **Speak** and **Dismiss** controls
- Inworld TTS-2, released explicitly by UI or a named voice command
- Automatic barge-in on human speech-start/interim speech; interrupted answers remain queued
- Expired-result suppression
- Manual **Research last turn** and **Stop agent** controls as demo fallbacks

### Not required

- Local/private RAG or repository ingestion
- Real multi-query `DEEP` execution
- Automatic meeting-stage classification
- Tenstorrent integration
- Zoom/Meet/Teams integration
- Diarization or shared-microphone support
- Video, recording, login, database, persistent history, vector database
- Standalone backend beyond the minimal Cloudflare token function

Add excluded features only after the acceptance test passes twice.

## Minimal architecture

```text
Browser A mic ─┐
Browser B mic ─┼─> LiveKit Cloud <─> managed Python worker
               │                         ├─ one Inworld STT stream per human track
Pages web + /api/token <────┘             ├─ Bright Data Discover
  receives room data events              ├─ OpenAI grounded synthesis
                                         └─ Inworld TTS agent audio
```

LiveKit is the realtime transport, event channel, and managed worker host—not the RAG/data layer. Bright Data supplies public-web evidence. A minimal Cloudflare Pages Function mints participant tokens with server-side secrets; there is no separate application backend.

## Repository shape

Keep this small enough to integrate under time pressure:

```text
.
├── PLAN.md
├── README.md
├── .gitignore
├── .env.example
├── contracts/
│   └── events.schema.json
├── web/
│   └── src/
│       ├── App.tsx
│       ├── events.ts
│       └── App.css
└── agent/
    ├── pyproject.toml
    ├── src/decision_window/
    │   ├── main.py
    │   ├── contracts.py
    │   ├── transcriber.py
    │   ├── research.py
    │   └── voice.py
    └── tests/
        ├── test_research.py
        └── test_transcriber.py
```

Do not add provider interfaces, an event-bus framework, or a meeting-adapter abstraction today. LiveKit plugins are already the replaceable boundary; `main.py` can wire the five components directly with `asyncio`.

## Frozen event contract

All cross-language room data uses topic `dw.event` and one envelope:

```json
{
  "type": "transcript.final",
  "ts_ms": 0,
  "payload": {}
}
```

Required event types:

- `agent.state`
- `transcript.partial`
- `transcript.final`
- `research.started`
- `research.completed`
- `research.expired`
- `research.failed`
- `answer.card`
- `control.research`
- `control.stop`

Minimum fields:

- Transcript: event ID, speaker ID/name, track SID, text, partial/final sequence, start/end time
- Research: job ID, asker ID/name, query, route, status, created/deadline time
- Answer: job ID, concise/full answer, confidence, citations, expired flag, speak flag

Only final transcripts enter history or launch research. A partial transcript may interrupt active TTS but cannot launch a job.

## Credential and provider preflight — 0:00–0:40

The user handles account/browser setup while the integrator scaffolds the repository. Store secrets only in `agent/.env`; commit names and placeholders only.

1. **LiveKit Cloud**
   - Create a temporary project and record URL, API key, and API secret.
   - Put those values in ignored local env files and Cloudflare server-side secrets only.
   - Use the `/api/token` Pages Function; Create embeds one `RoomAgentDispatch`, while Join mints an ordinary participant token.
2. **Inworld** — access available; rotate the exposed credential first
   - Revoke/rotate the credential that appeared in the added examples and this session before making any request.
   - Store only the replacement credential in `agent/.env`; never commit it.
   - Verify the current LiveKit Agents STT and TTS package names and one minimal request/session.
3. **Bright Data**
   - Create API access required by the current search/fetch product.
   - Run one search for `LiveKit self-hosting documentation` and retain title, URL, and snippet.
4. **OpenAI**
   - Create an API key with billing/quota available.
   - Run one small structured-output response.
5. **Cloudflare Pages**
   - Confirm deploy access.
   - Use `pnpm dlx wrangler` if CLI deployment is needed; do not install Wrangler globally.
6. **Local tools**
   - Install the LiveKit CLI from current official instructions only if the selected starter requires it.

**Gate:** by 0:40, LiveKit credentials and successful Bright Data/OpenAI calls must exist. If signup blocks, do not let agents independently invent provider workarounds; pick one fallback from the ladder below.

## Parallel ownership

Create one clean bootstrap commit before starting worktrees. Keep `Ideation Chat.pdf` local via `.git/info/exclude` unless the user explicitly chooses to publish it.

| Owner | Files | Deliverable |
|---|---|---|
| Integrator/Pi | root files, `contracts/**`, `agent/**/contracts.py`, `agent/**/main.py`, merges/deploy | Frozen contract and end-to-end wiring |
| Web worker | `web/**` only | Two-user room, audio, event UI, fallback controls |
| Media worker | `transcriber.py`, `voice.py`, media test | Per-track Inworld STT, agent TTS, interruption |
| Research worker | `research.py`, research test | Trigger, deadline, Bright Data, OpenAI, cited result |

Agents return isolated commits/diffs. Merge in this order:

1. bootstrap/contracts
2. web room
3. media
4. research
5. integrator wiring only

No agent may modify another owner’s files or redesign the event contract.

## Timed execution

### 0:00–0:40 — Bootstrap and credentials

- Complete provider preflight above.
- Initialize Vite/React and uv projects with current official package versions.
- Write `.env.example` and the event schema.
- Commit the baseline; start three isolated workers.

**Verify:** provider smoke calls pass; repository is clean; workers have non-overlapping ownership.

### 0:40–1:30 — Room and event shell

Web worker:

- Use official LiveKit React components rather than custom conference UI.
- Add display name, room code, Create, and Join controls.
- Publish microphone only; include the room audio renderer.
- Ensure only Create dispatches `decision-window`; Join must not dispatch duplicates.
- Render fixture `dw.event` messages.
- Make the first Cloudflare Pages deployment early.

Integrator:

- Start the local worker and publish an `agent.state` event.

**Gate 1 at 1:30:** two browsers hear one another and both display the same backend status event. Stop UI work until this passes.

### 1:30–2:30 — Speaker-labelled transcription

Media worker:

- Register track listeners before enumerating existing tracks.
- Create exactly one transcriber task and one Inworld STT stream per remote human track SID.
- Ignore the agent’s own identity/track.
- Forward partial and final transcript events with participant metadata.
- Cancel only the affected task on unpublish/disconnect/reconnect.
- Preserve independent sequences when speakers overlap.

Web worker renders partial text separately and appends finals once.

**Gate 2 at 2:30:** each browser’s speech appears under the correct name; overlapping speech produces two sequences; agent audio is not transcribed.

### 2:30–3:30 — Transcript to cited card

Research worker:

- Route every final turn through a structured LLM decision: `IGNORE` or `QUICK`.
- Give the router the last 16 speaker-labelled turns so it can resolve implicit references.
- Keep explicit wake matching only as a fallback when routing fails.
- Create `QUICK` jobs with a 30-second monotonic deadline.
- Retrieve one Bright Data search result without full-page content.
- Send retrieved evidence and the transcript snapshot to OpenAI while treating pages as untrusted data.
- Require concise answer, detailed answer, confidence, title, and URL.
- On timeout, publish `research.expired`; never produce speakable output.
- Keep at most two jobs active with `asyncio.Semaphore(2)`.

Integrator wires transcript → research → room data event.

**Gate 3 at 3:30:** a live implicit contextual question and an explicit invocation each produce a real cited card; an irrelevant turn produces none. If routing fails, use the manual Research button.

### 3:30–4:20 — Voice output

Media worker:

- Publish every answer card immediately and retain it independently of voice state.
- Queue multiple completed answers; do not speak automatically.
- Release a selected answer through its **Speak** button or release the oldest through a named voice command.
- Briefly identify the earlier question before giving its concise answer.
- **Dismiss** removes only queued voice delivery; the card remains visible.
- Keep one active speech handle and preserve an interrupted answer in the queue.
- Interrupt on a human speech-start event or first substantive interim transcript.
- Expose manual `interrupt()` for the Stop button.

**Gate 4 at 4:20:** both browsers hear a released answer; speaking over it stops it while leaving it available to retry.

### 4:20–5:00 — Decision Window behavior

Integrator:

- Add a visible countdown from deadline timestamps.
- Prevent late results from calling TTS even if network tasks finish later.
- Add one test proving timeout → expired → no speech.
- Add clear states for searching, answering, expired, failed, and agent offline.
- Re-run refresh, mute/unmute, disconnect, and duplicate-dispatch cases.

**Gate 5 at 5:00:** the required demo flow passes once end to end on two browsers.

### 5:00–5:45 — Public deployment and network test

- Deploy the frontend and `/api/token` function to a dedicated Cloudflare Pages project.
- Keep all provider keys in the local worker or encrypted Cloudflare server-side secrets.
- Test one browser on normal Wi-Fi and one on a phone hotspot/mobile network.
- Keep the Python worker local; disable laptop sleep.
- Confirm browser autoplay is unlocked by the explicit Join action.

**Gate 6 at 5:45:** the public URL completes the end-to-end flow.

### 5:45–6:30 — Failure hardening

Test only likely demo failures:

- participant joins after worker
- refresh/reconnect creates a new track
- mute/unmute
- two people overlap
- Bright Data returns no result or times out
- OpenAI returns malformed output
- TTS fails after card publication
- human interrupts TTS
- result crosses its deadline
- repeated question within ten seconds
- agent worker disconnects

Fix blockers only. No feature additions.

### 6:30–7:00 — Rehearsal and backup

- Run the exact acceptance flow twice.
- Record one successful backup video.
- Keep both laptops on headphones to prevent acoustic cross-contamination.
- Warm the room and worker before judging.
- Rotate or remove temporary LiveKit and Cloudflare secrets after the event.

## Fallback ladder

Use the first level that preserves a coherent demo; do not hide a fallback as a live integration.

1. **Full:** Inworld STT/TTS + Bright Data + OpenAI + automatic barge-in.
2. **STT/TTS provider issue:** use a currently supported LiveKit/OpenAI plugin by changing plugin wiring, while keeping Inworld integration as the first post-demo fix.
3. **Bright Data issue:** use OpenAI’s supported web-search tool if available; otherwise use a clearly labelled cached Bright Data response for the rehearsed question.
4. **Automatic trigger issue:** manual **Research last turn** button.
5. **Automatic interruption issue:** manual **Stop agent** button.
6. **Cloudflare issue:** mint short-lived participant tokens locally and serve Vite on the LAN; never expose the LiveKit secret to the browser.
7. **Voice issue:** preserve the cited card and deadline behavior; do not read uncited or expired text aloud.

## Small checks, not a test suite

- `test_research.py`: explicit trigger creates a job; timeout is expired; expired output is never speakable; citations are required.
- `test_transcriber.py`: self-track excluded; two track SIDs remain independently attributed; disconnect removes one stream only.
- TypeScript diagnostics and `pnpm build`.
- Python diagnostics and the two targeted tests.
- Two-browser manual acceptance checklist.

## Stretch order after the MVP passes twice

1. Host-selected phase: Explore / Decide / Wrap with different fixed deadlines.
2. Real `DEEP` route with two parallel searches and at most two fetched pages.
3. Generic local-folder search using `rg` snippets.
4. Passive question detection, card-only by default.
5. Tenstorrent-backed route classifier.
6. Speculation from partial transcripts.

## First action after plan approval

1. Keep the PDF untracked locally.
2. Scaffold the minimal repository and frozen contracts.
3. Start account setup and provider smoke tests in parallel.
4. Create the bootstrap commit.
5. Launch the three isolated implementation workers.
