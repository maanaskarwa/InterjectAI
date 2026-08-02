# Decision Window

A deadline-aware voice research participant for live meetings.

Today’s scope and gates are in [`PLAN.md`](PLAN.md).

Preview: <https://decision-window.pages.dev/?demo=1>

## Credential setup

Do not paste credentials into chat or commit them.

1. Copy root `.env.example` to root `.env` and fill it. The Inworld value must be the rotated replacement credential without the `Basic` prefix.
2. For local Pages Function testing, link it with `ln -s ../.env web/.dev.vars`.
3. In Cloudflare Pages, add `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` as encrypted server-side secrets. They must never use a `VITE_` prefix.
4. Keep the Python worker local. Cloudflare serves the web app and the small `/api/token` function.

## Development

```text
cd web
pnpm build
pnpm dlx wrangler pages dev dist
```

In another terminal:

```text
cd agent
uv run decision-window dev
```

Reusable live checks:

```text
cd agent
uv run python scripts/e2e_smoke.py basic
uv run python scripts/e2e_smoke.py direct
uv run python scripts/e2e_smoke.py implicit
uv run python scripts/e2e_smoke.py human-answer
uv run python scripts/e2e_smoke.py mute-cycle
uv run python scripts/e2e_smoke.py ignore
```

Answers appear as cards and remain visible. A short human-first grace period suppresses research when another participant answers. Use each card’s **Speak** or **Dismiss** control; dismissing removes only the queued voice delivery. “Decision Window, answer the previous question” releases the oldest queued answer.

## Local telemetry

Each agent session appends room events to `logs/rooms/<room>-<job>.jsonl`: partial/final transcripts, research lifecycle, cited answer cards, controls, and agent state. Raw audio is not stored. Worker SDK logs remain at `/tmp/decision-window-worker.log` for the active demo process.
