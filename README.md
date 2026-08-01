# Decision Window

A deadline-aware voice research participant for live meetings.

Today’s scope and gates are in [`PLAN.md`](PLAN.md).

## Credential setup

Do not paste credentials into chat or commit them.

1. Copy `agent/.env.example` to `agent/.env` and add the rotated Inworld credential plus LiveKit, Bright Data, and OpenAI values.
2. Copy `web/.dev.vars.example` to `web/.dev.vars` and add the three LiveKit values for local Pages Function testing.
3. In Cloudflare Pages, add `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` as encrypted server-side secrets. They must never use a `VITE_` prefix.
4. Keep the Python worker local. Cloudflare serves the web app and the small `/api/token` function.

## Development

```text
cd web
pnpm build
pnpm dlx wrangler pages dev dist
```

The Python worker command will be added with its LiveKit wiring.
