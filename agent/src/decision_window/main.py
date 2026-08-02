from __future__ import annotations

import asyncio
import logging
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

ROOT = Path(os.getenv("DECISION_WINDOW_ROOT", str(Path(__file__).resolve().parents[3])))
load_dotenv(ROOT / ".env")
logger = logging.getLogger(__name__)
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
    routing_buffers: dict[str, list[TranscriptPayload]] = {}
    routing_tasks: dict[str, asyncio.Task[Any]] = {}
    delivery_lock = asyncio.Lock()
    safe_room = "".join(character if character.isalnum() or character in "-_" else "_" for character in ctx.room.name)[:80]
    log_directory = ROOT / "logs" / "rooms"
    log_directory.mkdir(parents=True, exist_ok=True)
    log_path = log_directory / f"{safe_room}-{ctx.job.id}.jsonl"
    log_lock = asyncio.Lock()

    async def store(event: RoomEvent) -> None:
        line = event.model_dump_json()
        logger.info("room_event %s", line)
        async with log_lock:
            await asyncio.to_thread(append_line, log_path, line + "\n")

    async def publish(event: RoomEvent) -> None:
        if event.type == "answer.card":
            answer = AnswerPayload.model_validate(event.payload)
            pending_answers[answer.job_id] = answer
        await store(event)
        try:
            await ctx.room.local_participant.publish_data(
                event.model_dump_json().encode(),
                reliable=True,
                topic="dw.event",
            )
        except Exception as error:
            logger.warning("room_event_publish_failed type=%s error=%s", event.type, error)

    research = ResearchEngine(publish, deadline_seconds=configured_deadline())

    async def answer_transcript(transcript: TranscriptPayload) -> None:
        await research.handle_transcript(transcript, record=False)

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

    def spawn(coroutine: Any) -> asyncio.Task[Any]:
        task = asyncio.create_task(coroutine)
        background.add(task)

        def finish(completed: asyncio.Task[Any]) -> None:
            background.discard(completed)
            if not completed.cancelled() and (error := completed.exception()) is not None:
                logger.error(
                    "background_task_failed error=%s",
                    error,
                    exc_info=(type(error), error, error.__traceback__),
                )

        task.add_done_callback(finish)
        return task

    async def route_after_pause(speaker_id: str) -> None:
        await asyncio.sleep(2)
        turns = routing_buffers.pop(speaker_id)
        transcript = turns[-1].model_copy(update={
            "text": " ".join(turn.text for turn in turns),
            "start_ms": turns[0].start_ms,
        })
        command = transcript.text.lower()
        named = "decision window" in command or "session window" in command
        release = any(phrase in command for phrase in ("answer", "speak", "go ahead", "tell us"))
        if named and release and pending_answers:
            await deliver_answer()
        else:
            await answer_transcript(transcript)

    def schedule_route(speaker_id: str) -> None:
        previous = routing_tasks.get(speaker_id)
        if previous is not None:
            previous.cancel()
        routing_tasks[speaker_id] = spawn(route_after_pause(speaker_id))

    async def on_transcript(event: RoomEvent) -> None:
        await publish(event)
        if event.type == "transcript.partial":
            for speaker_id in tuple(routing_buffers):
                schedule_route(speaker_id)
            return
        if event.type != "transcript.final":
            return
        transcript = TranscriptPayload.model_validate(event.payload)
        research.record_transcript(transcript)
        routing_buffers.setdefault(transcript.speaker_id, []).append(transcript)
        for speaker_id in tuple(routing_buffers):
            schedule_route(speaker_id)

    def on_human_speech() -> None:
        voice.interrupt()
        for speaker_id in tuple(routing_buffers):
            schedule_route(speaker_id)

    transcriber = RoomTranscriber(ctx.room, on_transcript, on_human_speech)
    transcriber.start()

    @ctx.room.on("reconnecting")
    def on_reconnecting() -> None:
        spawn(store(RoomEvent.now("agent.state", {"status": "reconnecting", "room": ctx.room.name})))

    @ctx.room.on("reconnected")
    def on_reconnected() -> None:
        async def recover() -> None:
            await transcriber.restart_tracks()
            await publish(RoomEvent.now("agent.state", {"status": "online", "room": ctx.room.name}))

        spawn(recover())

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
