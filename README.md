# Decision Window

A deadline-aware voice research participant for live meetings.

Today’s scope and gates are in [`PLAN.md`](PLAN.md).

## Credential setup

Do not paste credentials into chat or commit them.

1. Copy `agent/.env.example` to `agent/.env` and add the rotated Inworld credential plus LiveKit, Bright Data, and OpenAI values.
2. Copy `web/.env.example` to `web/.env.local` and add only the public LiveKit URL/token endpoint values.
3. Keep the Python worker local; only the static web app is publicly deployed.

## Development

Commands will be finalized after the current LiveKit/Inworld package smoke test.
