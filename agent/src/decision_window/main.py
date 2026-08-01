from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import Agent, AgentServer, AgentSession, AutoSubscribe, JobContext, cli, room_io
from livekit.plugins import inworld

from .contracts import AnswerPayload, RoomEvent, TranscriptPayload
from .research import ResearchEngine
from .transcriber import RoomTranscriber
from .voice import VoiceOutput

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")
server = AgentServer()


def append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as output:
        output.write(line)


def configured_deadline() -> float:
    try:
        value = float(os.getenv("RESEARCH_DEADLINE_SECONDS", "12"))
    except ValueError as error:
        raise RuntimeError("RESEARCH_DEADLINE_SECONDS must be a number") from error
    if value <= 0:
        raise RuntimeError("RESEARCH_DEADLINE_SECONDS must be positive")
    return value


@server.rtc_session(agent_name=os.getenv("LIVEKIT_AGENT_NAME", "interject-build"))
async def decision_window(ctx: JobContext) -> None:
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    session = AgentSession(
        tts=inworld.TTS(
            voice=os.getenv("INWORLD_VOICE", "Sarah"),
            model=os.getenv("INWORLD_TTS_MODEL", "inworld-tts-2"),
            speaking_rate=1.2,
            delivery_mode="BALANCED",
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
    pending_answers: dict[str, AnswerPayload] = {}
    delivery_lock = asyncio.Lock()
    safe_room = "".join(character if character.isalnum() or character in "-_" else "_" for character in ctx.room.name)[:80]
    log_directory = ROOT / "logs" / "rooms"
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / f"{safe_room}-{ctx.job.id}.jsonl"
    log_lock = asyncio.Lock()

    async def store(event: RoomEvent) -> None:
        async with log_lock:
            await asyncio.to_thread(append_line, log_path, event.model_dump_json() + "\n")

    async def publish(event: RoomEvent) -> None:
        if event.type == "answer.card":
            answer = AnswerPayload.model_validate(event.payload)
            pending_answers[answer.job_id] = answer
        await store(event)
        await ctx.room.local_participant.publish_data(
            event.model_dump_json().encode(),
            reliable=True,
            topic="dw.event",
        )

    research = ResearchEngine(publish, deadline_seconds=configured_deadline())

    async def answer_transcript(transcript: TranscriptPayload) -> None:
        await research.handle_transcript(transcript)

    async def deliver_answer(job_id: str | None = None) -> None:
        if not pending_answers or (job_id is not None and job_id not in pending_answers):
            return
        selected_id = job_id or next(iter(pending_answers))
        answer = pending_answers[selected_id]
        question = " ".join(answer.question.rstrip("?.!").split()[:10])
        async with delivery_lock:
            delivered = await voice.say(f"On the earlier question, {question}: {answer.concise_answer}")
        if delivered:
            pending_answers.pop(selected_id, None)

    async def manual_research(query: str, asker_id: str, asker_name: str) -> None:
        await research.run(query, asker_id, asker_name)

    def spawn(coroutine: Any) -> None:
        task = asyncio.create_task(coroutine)
        background.add(task)
        task.add_done_callback(background.discard)

    async def on_transcript(event: RoomEvent) -> None:
        await publish(event)
        if event.type == "transcript.final":
            transcript = TranscriptPayload.model_validate(event.payload)
            command = transcript.text.lower()
            named = "decision window" in command or "session window" in command
            release = any(phrase in command for phrase in ("answer", "speak", "go ahead", "tell us"))
            if named and release and pending_answers:
                spawn(deliver_answer())
            else:
                spawn(answer_transcript(transcript))

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
        spawn(store(event))
        job_id = str(event.payload.get("job_id", "")) or None
        if event.type == "control.stop":
            voice.interrupt()
        elif event.type == "control.dismiss" and job_id is not None:
            pending_answers.pop(job_id, None)
        elif event.type == "control.speak":
            spawn(deliver_answer(job_id))
        elif event.type == "control.research":
            query = str(event.payload.get("query", "")).strip()
            if query:
                spawn(manual_research(
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
    await publish(RoomEvent.now("agent.state", {
        "status": "online",
        "room": ctx.room.name,
        "event_log": str(log_path.relative_to(ROOT)),
    }))


def run() -> None:
    cli.run_app(server)


if __name__ == "__main__":
    run()
