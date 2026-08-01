from __future__ import annotations

from typing import Any


class VoiceOutput:
    def __init__(self, session: Any) -> None:
        self._session = session
        self._handle: Any | None = None

    async def say(self, text: str) -> None:
        words = text.split()
        if not words:
            return
        self.interrupt()
        handle = self._session.say(" ".join(words[:25]), allow_interruptions=True)
        self._handle = handle
        try:
            await handle.wait_for_playout()
        finally:
            if self._handle is handle:
                self._handle = None

    def interrupt(self) -> None:
        if self._handle is not None and not self._handle.done():
            self._handle.interrupt()
