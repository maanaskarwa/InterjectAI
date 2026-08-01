import asyncio
import unittest

from livekit import rtc
from livekit.agents import stt
from livekit.agents.language import LanguageCode

from decision_window.contracts import RoomEvent
from decision_window.transcriber import ParticipantTranscriber, RoomTranscriber, should_transcribe


class TranscriberTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.events: list[RoomEvent] = []
        self.speech_events = 0

    async def publish(self, event: RoomEvent) -> None:
        self.events.append(event)

    def on_speech(self) -> None:
        self.speech_events += 1

    def test_agent_is_excluded(self) -> None:
        self.assertFalse(should_transcribe("decision-window"))
        self.assertFalse(should_transcribe("decision-window-worker"))
        self.assertFalse(should_transcribe("agent-AJ_example"))
        self.assertTrue(should_transcribe("alice-123"))

    async def test_tracks_keep_independent_attribution(self) -> None:
        alice = ParticipantTranscriber("alice", "Alice", "track-a", self.publish, self.on_speech, object())
        bob = ParticipantTranscriber("bob", "Bob", "track-b", self.publish, self.on_speech, object())
        await alice.handle_event(stt.SpeechEvent(
            type=stt.SpeechEventType.INTERIM_TRANSCRIPT,
            alternatives=[stt.SpeechData(language=LanguageCode("en"), text="hello", start_time=0, end_time=0.2)],
        ))
        await bob.handle_event(stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[stt.SpeechData(language=LanguageCode("en"), text="hi Alice", start_time=0, end_time=0.3)],
        ))
        self.assertEqual(
            [(event.payload["speaker_name"], event.payload["track_sid"]) for event in self.events],
            [("Alice", "track-a"), ("Bob", "track-b")],
        )
        self.assertEqual(self.speech_events, 1)

    async def test_stopping_one_track_leaves_the_other_running(self) -> None:
        manager = RoomTranscriber(rtc.Room(), self.publish, self.on_speech)
        first = asyncio.create_task(asyncio.sleep(60))
        second = asyncio.create_task(asyncio.sleep(60))
        manager._tasks = {"track-a": ("alice", first), "track-b": ("bob", second)}
        manager.stop_track("track-a")
        await asyncio.sleep(0)
        self.assertTrue(first.cancelled())
        self.assertFalse(second.done())
        await manager.close()


if __name__ == "__main__":
    unittest.main()
