from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import Agent, AgentServer, AgentSession, AutoSubscribe, JobContext, cli, room_io
from livekit.plugins import inworld

from .contracts import RoomEvent, TranscriptPayload
from .research import ResearchEngine
from .transcriber import RoomTranscriber
from .voice import VoiceOutput

load_dotenv(Path(__file__).resolve().parents[3] / ".env")
server = AgentServer()


def configured_deadline() -> float:
    try:
        value = float(os.getenv("RESEARCH_DEADLINE_SECONDS", "12"))
    except ValueError as error:
        raise RuntimeError("RESEARCH_DEADLINE_SECONDS must be a number") from error
    if value <= 0:
        raise RuntimeError("RESEARCH_DEADLINE_SECONDS must be positive")
    return value


@server.rtc_session(agent_name=os.getenv("LIVEKIT_AGENT_NAME", "decision-window"))
async def decision_window(ctx: JobContext) -> None:
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    session = AgentSession(
        tts=inworld.TTS(
            voice=os.getenv("INWORLD_VOICE", "Sarah"),
            model=os.getenv("INWORLD_TTS_MODEL", "inworld-tts-1.5-max"),
            speaking_rate=1.2,
        ),
    )
    await session.start(
        agent=Agent(instructions="Speak only research answers supplied by Decision Window.", llm=None, stt=None),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            text_input=False,
            audio_input=False,
            video_input=False,
            audio_output=True,
            text_output=False,
            close_on_disconnect=False,
        ),
        record=False,
    )

    voice = VoiceOutput(session)
    background: set[asyncio.Task[Any]] = set()

    async def publish(event: RoomEvent) -> None:
        await ctx.room.local_participant.publish_data(
            event.model_dump_json().encode(),
            reliable=True,
            topic="dw.event",
        )

    research = ResearchEngine(publish, deadline_seconds=configured_deadline())

    async def answer_transcript(transcript: TranscriptPayload) -> None:
        answer = await research.handle_transcript(transcript)
        if answer and answer.speak:
            await voice.say(f"{answer.asker_name}, {answer.concise_answer}")

    def spawn(coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        background.add(task)
        task.add_done_callback(background.discard)

    async def on_transcript(event: RoomEvent) -> None:
        await publish(event)
        if event.type == "transcript.final":
            spawn(answer_transcript(TranscriptPayload.model_validate(event.payload)))

    transcriber = RoomTranscriber(ctx.room, on_transcript, voice.interrupt)
    transcriber.start()

    @ctx.room.on("data_received")
    def on_data(packet: rtc.DataPacket) -> None:
        if packet.topic != "dw.event":
            return
        try:
            event = RoomEvent.model_validate_json(packet.data)
        except ValueError:
            return
        if event.type == "control.stop":
            voice.interrupt()
        elif event.type == "control.research":
            query = str(event.payload.get("query", "")).strip()
            if query:
                spawn(research.run(
                    query,
                    str(event.payload.get("asker_id", "manual")),
                    str(event.payload.get("asker_name", "Participant")),
                ))

    async def shutdown() -> None:
        await transcriber.close()
        for task in background:
            task.cancel()
        await asyncio.gather(*background, return_exceptions=True)

    ctx.add_shutdown_callback(shutdown)
    await publish(RoomEvent.now("agent.state", {"status": "online"}))


def run() -> None:
    cli.run_app(server)


if __name__ == "__main__":
    run()
