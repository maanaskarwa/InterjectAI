import asyncio
import json
import unittest
from types import SimpleNamespace

from decision_window.contracts import RoomEvent, TranscriptPayload
from decision_window.research import ResearchEngine, parse_query


class FakeBrightData:
    def __init__(self, delay: float = 0) -> None:
        self.delay = delay

    async def discover(self, **_: object) -> object:
        await asyncio.sleep(self.delay)
        return SimpleNamespace(data=[{
            "title": "LiveKit self-hosting",
            "link": "https://docs.livekit.io/home/self-hosting/",
            "description": "LiveKit can be self-hosted.",
        }])


class FakeCompletions:
    async def create(self, **_: object) -> object:
        content = json.dumps({
            "concise_answer": "LiveKit can be self-hosted using its open-source server deployment options.",
            "full_answer": "LiveKit documents self-hosted deployment options.",
            "confidence": 0.92,
        })
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class FakeOpenAI:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions())


class ResearchTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.events: list[RoomEvent] = []

    async def publish(self, event: RoomEvent) -> None:
        self.events.append(event)

    def transcript(self, text: str) -> TranscriptPayload:
        return TranscriptPayload(
            event_id="evt-1",
            speaker_id="alice-1",
            speaker_name="Alice",
            track_sid="track-1",
            text=text,
            sequence=1,
            start_ms=1,
        )

    def test_parse_query(self) -> None:
        self.assertEqual(
            parse_query("Decision Window, verify whether LiveKit can be self-hosted?"),
            "whether LiveKit can be self-hosted",
        )
        self.assertEqual(
            parse_query("Decision Window, can you verify what the capital of India is?"),
            "what the capital of India is",
        )
        self.assertEqual(parse_query("Session window, look up LiveKit"), "LiveKit")
        self.assertIsNone(parse_query("Decision Window."))
        self.assertIsNone(parse_query("Can LiveKit be self-hosted?"))

    async def test_split_wake_phrase_uses_next_turn(self) -> None:
        engine = ResearchEngine(self.publish, brightdata=FakeBrightData(), openai=FakeOpenAI())
        self.assertIsNone(await engine.handle_transcript(self.transcript("Decision Window.")))
        answer = await engine.handle_transcript(self.transcript("Verify what the capital of India is."))
        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertEqual(answer.question, "what the capital of India is")

    async def test_cited_answer(self) -> None:
        engine = ResearchEngine(
            self.publish,
            brightdata=FakeBrightData(),
            openai=FakeOpenAI(),
        )
        answer = await engine.handle_transcript(
            self.transcript("Decision Window, verify whether LiveKit can be self-hosted?"),
        )
        self.assertIsNotNone(answer)
        assert answer is not None
        self.assertTrue(answer.speak)
        self.assertEqual(len(answer.citations), 1)
        self.assertEqual(
            [event.type for event in self.events],
            ["research.started", "answer.card", "research.completed"],
        )

    async def test_timeout_never_answers(self) -> None:
        engine = ResearchEngine(
            self.publish,
            brightdata=FakeBrightData(delay=0.05),
            openai=FakeOpenAI(),
            deadline_seconds=0.01,
        )
        answer = await engine.handle_transcript(
            self.transcript("Decision Window, research LiveKit"),
        )
        self.assertIsNone(answer)
        self.assertEqual(self.events[-1].type, "research.expired")
        self.assertNotIn("answer.card", [event.type for event in self.events])

    async def test_non_trigger_is_ignored(self) -> None:
        engine = ResearchEngine(self.publish, brightdata=FakeBrightData(), openai=FakeOpenAI())
        self.assertIsNone(await engine.handle_transcript(self.transcript("What about LiveKit?")))
        self.assertEqual(self.events, [])


if __name__ == "__main__":
    unittest.main()
