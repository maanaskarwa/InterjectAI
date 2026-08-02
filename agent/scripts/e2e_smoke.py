#!/usr/bin/env python3
"""Run the live Decision Window path without a browser or microphone."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from livekit import rtc
from livekit.agents.utils import http_context
from livekit.plugins import inworld

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

SCENARIOS = {
    "basic": ["What is the capital of India?"],
    "human-answer": ["What is the capital of India?"],
    "mute-cycle": [
        "Alpha before muting.",
        "Forbidden pineapple while muted.",
        "Omega after unmuting.",
    ],
    "direct": ["Decision Window, can you verify whether LiveKit supports self hosting?"],
    "repeat-guard": [
        "Decision Window, can you verify whether LiveKit supports self hosting?",
        "Okay.",
        "Yeah.",
        "That's right.",
    ],
    "implicit": [
        "We are discussing whether LiveKit fits our deployment needs.",
        "Does it support self hosting?",
    ],
    "ignore": ["We should continue with the next agenda item."],
}


async def connection_details(
    base_url: str,
    room_name: str,
    *,
    participant_name: str = "E2E Test",
    dispatch_agent: bool = True,
) -> dict[str, str]:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{base_url.rstrip('/')}/api/token",
            json={
                "roomName": room_name,
                "participantName": participant_name,
                "participantIdentity": f"e2e-{uuid.uuid4().hex[:8]}",
                "dispatchAgent": dispatch_agent,
            },
        )
        response.raise_for_status()
        return response.json()


async def synthesize(text: str) -> list[rtc.AudioFrame]:
    frames: list[rtc.AudioFrame] = []
    async with http_context.open():
        async with inworld.TTS(
            model="inworld-tts-2",
            voice="Sarah",
            delivery_mode="BALANCED",
        ).synthesize(text) as audio:
            async for chunk in audio:
                frames.append(chunk.frame)
    return frames


async def run(scenario: str, base_url: str) -> dict[str, Any]:
    started = time.monotonic()
    room_name = f"decision-window-e2e-{uuid.uuid4().hex[:8]}"
    details = await connection_details(base_url, room_name)
    room = rtc.Room()
    peer: rtc.Room | None = None
    ready = asyncio.Event()
    terminal = asyncio.Event()
    agent_audio = asyncio.Event()
    events: list[dict[str, Any]] = []
    readers: set[asyncio.Task[None]] = set()

    @room.on("data_received")
    def on_data(packet: rtc.DataPacket) -> None:
        if packet.topic != "dw.event":
            return
        try:
            event = json.loads(packet.data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            return
        events.append(event)
        if event["type"] == "agent.state":
            ready.set()
        elif event["type"] in ("research.completed", "research.expired", "research.failed"):
            terminal.set()

    @room.on("track_subscribed")
    def on_track(
        track: rtc.Track,
        _publication: rtc.RemoteTrackPublication,
        participant: rtc.RemoteParticipant,
    ) -> None:
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        if participant.kind != rtc.ParticipantKind.PARTICIPANT_KIND_AGENT:
            return

        async def detect_audio() -> None:
            stream = rtc.AudioStream.from_track(
                track=track,
                sample_rate=24_000,
                num_channels=1,
                frame_size_ms=20,
            )
            try:
                async for frame in stream:
                    if max(abs(value) for value in frame.frame.data) > 100:
                        agent_audio.set()
                        return
            finally:
                await stream.aclose()

        task = asyncio.create_task(detect_audio())
        readers.add(task)
        task.add_done_callback(readers.discard)

    try:
        await room.connect(details["serverUrl"], details["participantToken"])
        await asyncio.wait_for(ready.wait(), timeout=30)
        if scenario == "human-answer":
            peer = rtc.Room()
            peer_details = await connection_details(
                base_url,
                room_name,
                participant_name="Human Answer",
                dispatch_agent=False,
            )
            await peer.connect(peer_details["serverUrl"], peer_details["participantToken"])

        utterances = [await synthesize(text) for text in SCENARIOS[scenario]]
        source = rtc.AudioSource(24_000, 1, queue_size_ms=200)
        track = rtc.LocalAudioTrack.create_audio_track("microphone", source)
        await room.local_participant.publish_track(
            track,
            rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE),
        )
        await asyncio.sleep(1)
        silence = rtc.AudioFrame.create(24_000, 1, 2_400)
        if scenario == "mute-cycle":
            for frame in utterances[0]:
                await source.capture_frame(frame)
            for _ in range(15):
                await source.capture_frame(silence)
            await source.wait_for_playout()
            track.mute()
            for frame in utterances[1]:
                await source.capture_frame(frame)
            for _ in range(15):
                await source.capture_frame(silence)
            await source.wait_for_playout()
            track.unmute()
            for frame in utterances[2]:
                await source.capture_frame(frame)
            for _ in range(25):
                await source.capture_frame(silence)
        else:
            for utterance in utterances:
                for frame in utterance:
                    await source.capture_frame(frame)
                for _ in range(8 if scenario == "human-answer" else 25):
                    await source.capture_frame(silence)

        if scenario == "human-answer":
            if peer is None:
                raise RuntimeError("Second participant did not connect")
            peer_source = rtc.AudioSource(24_000, 1, queue_size_ms=200)
            peer_track = rtc.LocalAudioTrack.create_audio_track("microphone", peer_source)
            await peer.local_participant.publish_track(
                peer_track,
                rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE),
            )
            await asyncio.sleep(0.5)
            for frame in await synthesize("New Delhi is the capital of India."):
                await peer_source.capture_frame(frame)
            for _ in range(25):
                await peer_source.capture_frame(silence)
            await asyncio.sleep(8)
            research_events = [event for event in events if event["type"].startswith("research.")]
            speakers = {
                event["payload"].get("speaker_name")
                for event in events
                if event["type"] == "transcript.final"
            }
            if research_events or len(speakers) < 2:
                raise RuntimeError({"research_events": research_events, "speakers": list(speakers)})
        elif scenario in ("ignore", "mute-cycle"):
            await asyncio.sleep(8)
            research_events = [event for event in events if event["type"].startswith("research.")]
            if research_events:
                raise RuntimeError(f"Unexpected research events: {research_events}")
            if scenario == "mute-cycle":
                transcript_text = " ".join(
                    str(event["payload"].get("text", ""))
                    for event in events
                    if event["type"] == "transcript.final"
                ).lower()
                resumed = "after unmuting" in transcript_text
                if "alpha" not in transcript_text or not resumed or "pineapple" in transcript_text:
                    raise RuntimeError(f"Mute cycle transcript: {transcript_text}")
        else:
            await asyncio.wait_for(terminal.wait(), timeout=65)
            terminal_event = next(
                event for event in reversed(events)
                if event["type"] in ("research.completed", "research.expired", "research.failed")
            )
            if terminal_event["type"] != "research.completed":
                raise RuntimeError(terminal_event)
            cards = [event["payload"] for event in events if event["type"] == "answer.card"]
            jobs = [event["payload"] for event in events if event["type"] == "research.started"]
            finals = [event["payload"] for event in events if event["type"] == "transcript.final"]
            if not cards or not jobs or len(finals) < len(utterances):
                raise RuntimeError({"cards": cards, "jobs": jobs, "finals": finals})
            if scenario == "basic" and jobs[-1].get("route") != "INSTANT":
                raise RuntimeError(f"Basic fact took {jobs[-1].get('route')} route")
            if jobs[-1].get("route") == "QUICK" and not cards[-1].get("citations"):
                raise RuntimeError(f"QUICK answer has no citations: {cards[-1]}")
            if scenario == "repeat-guard":
                await asyncio.sleep(6)
                jobs = [event["payload"] for event in events if event["type"] == "research.started"]
                if len(jobs) != 1:
                    raise RuntimeError(f"Filler speech started {len(jobs)} research jobs")
            await asyncio.sleep(1)
            if agent_audio.is_set():
                raise RuntimeError("Agent spoke before the answer was released")
            await room.local_participant.publish_data(
                json.dumps({
                    "type": "control.speak",
                    "ts_ms": time.time_ns() // 1_000_000,
                    "payload": {"job_id": cards[-1]["job_id"]},
                }).encode(),
                reliable=True,
                topic="dw.event",
            )
            await asyncio.wait_for(agent_audio.wait(), timeout=25)

        return {
            "scenario": scenario,
            "passed": True,
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "event_types": [event["type"] for event in events],
            "room": room_name,
        }
    finally:
        if peer is not None:
            await peer.disconnect()
        await room.disconnect()
        for task in readers:
            task.cancel()
        await asyncio.gather(*readers, return_exceptions=True)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=SCENARIOS, nargs="?", default="direct")
    parser.add_argument("--base-url", default="https://decision-window.pages.dev")
    args = parser.parse_args()
    try:
        result = await run(args.scenario, args.base_url)
    except Exception as error:
        result = {"scenario": args.scenario, "passed": False, "error": str(error)}
        print(json.dumps(result, indent=2))
        raise SystemExit(1) from error
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
