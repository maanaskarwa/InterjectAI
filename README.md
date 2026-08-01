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
