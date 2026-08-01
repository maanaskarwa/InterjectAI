from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from livekit import rtc
from livekit.agents import stt
from livekit.plugins import inworld

from .contracts import RoomEvent, TranscriptPayload

Publish = Callable[[RoomEvent], Awaitable[None]]
SpeechCallback = Callable[[], None]


def should_transcribe(identity: str) -> bool:
    return not identity.startswith(("decision-window", "agent-"))


class ParticipantTranscriber:
    def __init__(
        self,
        participant_id: str,
        participant_name: str,
        track_sid: str,
        publish: Publish,
        on_speech: SpeechCallback,
        stt_service: Any | None = None,
    ) -> None:
        self.participant_id = participant_id
        self.participant_name = participant_name
        self.track_sid = track_sid
        self._publish = publish
        self._on_speech = on_speech
        self._stt = stt_service or inworld.STT(enable_voice_profile=False)
        self._sequence = 0
        self._stream_started_ms = time.time_ns() // 1_000_000

    async def run(self, track: rtc.Track) -> None:
        audio = rtc.AudioStream(track, sample_rate=16_000, num_channels=1)
        speech = self._stt.stream()

        async def feed() -> None:
            async for frame in audio:
                speech.push_frame(frame.frame)
            speech.end_input()

        producer = asyncio.create_task(feed())
        try:
            async for event in speech:
                await self.handle_event(event)
        finally:
            producer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await producer
            await speech.aclose()
            await audio.aclose()

    async def handle_event(self, event: stt.SpeechEvent) -> None:
        if event.type in (stt.SpeechEventType.START_OF_SPEECH, stt.SpeechEventType.INTERIM_TRANSCRIPT):
            self._on_speech()
        if event.type not in (stt.SpeechEventType.INTERIM_TRANSCRIPT, stt.SpeechEventType.FINAL_TRANSCRIPT):
            return
        if not event.alternatives or not event.alternatives[0].text.strip():
            return

        alternative = event.alternatives[0]
        self._sequence += 1
        payload = TranscriptPayload(
            event_id=f"{self.track_sid}-{uuid.uuid4().hex[:10]}",
            speaker_id=self.participant_id,
            speaker_name=self.participant_name,
            track_sid=self.track_sid,
            text=alternative.text.strip(),
            sequence=self._sequence,
            start_ms=self._stream_started_ms + round(alternative.start_time * 1000),
            end_ms=self._stream_started_ms + round(alternative.end_time * 1000),
        )
        event_type = "transcript.final" if event.type == stt.SpeechEventType.FINAL_TRANSCRIPT else "transcript.partial"
        await self._publish(RoomEvent.now(event_type, payload))


class RoomTranscriber:
    def __init__(self, room: rtc.Room, publish: Publish, on_speech: SpeechCallback) -> None:
        self._room = room
        self._publish = publish
        self._on_speech = on_speech
        self._tasks: dict[str, tuple[str, asyncio.Task[None]]] = {}

    def start(self) -> None:
        self._room.on("track_subscribed", self._on_track_subscribed)
        self._room.on("track_unsubscribed", self._on_track_unsubscribed)
        self._room.on("participant_disconnected", self._on_participant_disconnected)
        for participant in self._room.remote_participants.values():
            for publication in participant.track_publications.values():
                if publication.track is not None:
                    self._on_track_subscribed(publication.track, publication, participant)

    def _on_track_subscribed(
        self,
        track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO or not should_transcribe(participant.identity):
            return
        track_sid = publication.sid
        if track_sid in self._tasks:
            return
        worker = ParticipantTranscriber(
            participant.identity,
            participant.name or participant.identity,
            track_sid,
            self._publish,
            self._on_speech,
        )
        task = asyncio.create_task(worker.run(track))
        self._tasks[track_sid] = (participant.identity, task)
        task.add_done_callback(lambda finished, sid=track_sid: self._remove_finished(sid, finished))

    def _remove_finished(self, track_sid: str, task: asyncio.Task[None]) -> None:
        current = self._tasks.get(track_sid)
        if current and current[1] is task:
            self._tasks.pop(track_sid, None)

    def _on_track_unsubscribed(
        self,
        _track: rtc.Track,
        publication: rtc.RemoteTrackPublication,
        _participant: rtc.RemoteParticipant,
    ) -> None:
        self.stop_track(publication.sid)

    def _on_participant_disconnected(self, participant: rtc.RemoteParticipant) -> None:
        for track_sid, (identity, _) in list(self._tasks.items()):
            if identity == participant.identity:
                self.stop_track(track_sid)

    def stop_track(self, track_sid: str) -> None:
        entry = self._tasks.pop(track_sid, None)
        if entry:
            entry[1].cancel()

    async def close(self) -> None:
        tasks = [task for _, task in self._tasks.values()]
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
