# Interject

A deadline-aware voice research participant for live meetings.

Today’s scope and gates are in [`PLAN.md`](PLAN.md).

Public app: <https://interjectai.pages.dev/>  
Legacy URL: <https://decision-window.pages.dev/>

## Credential setup

Do not paste credentials into chat or commit them.

1. Copy root `.env.example` to root `.env` and fill it. The Inworld value must be the rotated replacement credential without the `Basic` prefix.
2. For local Pages Function testing, link it with `ln -s ../.env web/.dev.vars`.
3. In Cloudflare Pages, add `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` as encrypted server-side secrets. They must never use a `VITE_` prefix.
4. Cloudflare serves the web app and `/api/token`; LiveKit Cloud runs the persistent Python worker.

## Development

```text
cd web
pnpm build
pnpm dlx wrangler pages dev dist
```

For local worker development:

```text
cd agent
uv run decision-window dev
```

Deploy the managed worker from the repository root without committing secrets:

```text
lk agent deploy --secrets-file .env --ignore-empty-secrets agent
lk agent status agent
```

Reusable live checks:

```text
cd agent
uv run python scripts/e2e_smoke.py basic
uv run python scripts/e2e_smoke.py direct
uv run python scripts/e2e_smoke.py repeat-guard
uv run python scripts/e2e_smoke.py implicit
uv run python scripts/e2e_smoke.py human-answer
uv run python scripts/e2e_smoke.py mute-cycle
uv run python scripts/e2e_smoke.py ignore
```

Answers appear as cards and remain visible. A short human-first grace period suppresses research when another participant answers. Use each card’s **Speak** or **Dismiss** control; dismissing removes only the queued voice delivery.

## Telemetry

Managed-worker logs include room events, per-track mute state, five-second audio-frame health, research lifecycle, and reconnect state:

```text
lk agent logs agent
```

Local sessions also append `logs/rooms/<room>-<job>.jsonl`; local SDK logs use `/tmp/decision-window-worker.log`. Raw audio is never stored.
