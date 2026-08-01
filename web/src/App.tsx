import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  LiveKitRoom,
  RoomAudioRenderer,
  useDataChannel,
  useLocalParticipant,
  useParticipants,
  useRoomContext,
} from '@livekit/components-react'
import '@livekit/components-styles'
import './App.css'
import {
  answer,
  decodeEvent,
  research,
  topic,
  transcript,
  type Answer,
  type ResearchJob,
  type Transcript,
} from './events'

type Connection = { token: string; serverUrl: string; room: string; name: string; identity: string }

const env = import.meta.env
const tokenEndpoint = (env.VITE_LIVEKIT_TOKEN_ENDPOINT as string | undefined) || '/api/token'
const fallbackServerUrl = env.VITE_LIVEKIT_URL as string | undefined
const defaultRoom = (env.VITE_DEFAULT_ROOM as string | undefined) || 'decision-window-demo'

function identityFor(name: string) {
  const key = 'decision-window.identity'
  let suffix = localStorage.getItem(key)
  if (!suffix) {
    suffix = crypto.randomUUID().slice(0, 8)
    localStorage.setItem(key, suffix)
  }
  return `${name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'guest'}-${suffix}`
}

async function getConnection(room: string, name: string, create: boolean): Promise<Connection> {
  const identity = identityFor(name)
  const response = await fetch(tokenEndpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      roomName: room,
      participantName: name,
      participantIdentity: identity,
      dispatchAgent: create,
    }),
  })
  if (!response.ok) throw new Error(`Token request failed (${response.status})`)

  const body = (await response.json()) as Record<string, unknown>
  const token = String(body.participantToken || body.participant_token || body.token || '')
  const serverUrl = String(body.serverUrl || body.server_url || body.url || fallbackServerUrl || '')
  if (!token || !serverUrl) throw new Error('Token response is missing token or server URL')
  return { token, serverUrl, room, name, identity }
}

function App() {
  const [name, setName] = useState('')
  const [room, setRoom] = useState(defaultRoom)
  const [connection, setConnection] = useState<Connection | null>(null)
  const [error, setError] = useState('')

  const join = async (create: boolean) => {
    if (!name.trim() || !room.trim()) return setError('Enter a display name and room code')
    setError('')
    try {
      setConnection(await getConnection(room.trim(), name.trim(), create))
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to join')
    }
  }

  if (connection) {
    return (
      <LiveKitRoom
        token={connection.token}
        serverUrl={connection.serverUrl}
        audio
        video={false}
        connect
        onDisconnected={() => setConnection(null)}
        data-lk-theme="default"
      >
        <RoomAudioRenderer />
        <Meeting connection={connection} />
      </LiveKitRoom>
    )
  }

  return (
    <main className="lobby">
      <form className="card" onSubmit={(event) => event.preventDefault()}>
        <p className="eyebrow">Realtime meeting research</p>
        <h1>Decision Window</h1>
        <label>Display name<input value={name} onChange={(event) => setName(event.target.value)} autoFocus /></label>
        <label>Room code<input value={room} onChange={(event) => setRoom(event.target.value)} /></label>
        <div className="actions">
          <button type="button" onClick={() => void join(true)}>Create room</button>
          <button type="button" className="secondary" onClick={() => void join(false)}>Join room</button>
        </div>
        {error && <p className="error">{error}</p>}
      </form>
    </main>
  )
}

function Meeting({ connection }: { connection: Connection }) {
  const room = useRoomContext()
  const participants = useParticipants()
  const { localParticipant, isMicrophoneEnabled } = useLocalParticipant()
  const [partials, setPartials] = useState<Record<string, Transcript>>({})
  const [finals, setFinals] = useState<Transcript[]>([])
  const [jobs, setJobs] = useState<Record<string, ResearchJob>>({})
  const [answers, setAnswers] = useState<Answer[]>([])
  const [agent, setAgent] = useState('waiting')
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  const onMessage = useCallback((message: { payload: Uint8Array }) => {
    const event = decodeEvent(message.payload)
    if (!event) return

    if (event.type === 'transcript.partial' || event.type === 'transcript.final') {
      const line = transcript(event.payload)
      if (!line) return
      if (event.type === 'transcript.partial') {
        setPartials((current) => ({ ...current, [line.track_sid]: line }))
      } else {
        setPartials((current) => {
          const next = { ...current }
          delete next[line.track_sid]
          return next
        })
        setFinals((current) => [...current.filter((item) => item.event_id !== line.event_id), line].slice(-50))
      }
      return
    }

    if (event.type.startsWith('research.')) {
      const job = research(event.payload)
      if (job) setJobs((current) => ({ ...current, [job.job_id]: job }))
      return
    }

    if (event.type === 'answer.card') {
      const card = answer(event.payload)
      if (card) setAnswers((current) => [card, ...current].slice(0, 5))
      return
    }

    if (event.type === 'agent.state') setAgent(String(event.payload.status || 'online'))
  }, [])

  const { send, isSending } = useDataChannel(topic, onMessage)
  const orderedTranscripts = useMemo(
    () => [...finals, ...Object.values(partials)].sort((a, b) => a.start_ms - b.start_ms),
    [finals, partials],
  )
  const latest = finals.at(-1)?.text || ''

  const control = async (type: 'control.research' | 'control.stop') => {
    await send(
      new TextEncoder().encode(JSON.stringify({
        type,
        ts_ms: Date.now(),
        payload: {
          asker_id: connection.identity,
          asker_name: connection.name,
          ...(type === 'control.research' ? { query: latest } : {}),
        },
      })),
      { reliable: true, topic },
    )
  }

  return (
    <main className="meeting">
      <header>
        <div><p className="eyebrow">Room {connection.room}</p><h1>Decision Window</h1></div>
        <span className={`agent ${agent === 'online' ? 'online' : ''}`}>Agent: {agent}</span>
      </header>

      <nav className="actions">
        <button type="button" onClick={() => void localParticipant.setMicrophoneEnabled(!isMicrophoneEnabled)}>
          {isMicrophoneEnabled ? 'Mute' : 'Unmute'}
        </button>
        <button type="button" className="secondary" disabled={!latest || isSending} onClick={() => void control('control.research')}>Research last turn</button>
        <button type="button" className="danger" onClick={() => void control('control.stop')}>Stop agent</button>
        <button type="button" className="secondary" onClick={() => void room.disconnect()}>Leave</button>
      </nav>

      <div className="grid">
        <section className="panel participants">
          <h2>Participants</h2>
          {participants.map((participant) => (
            <p key={participant.sid}><span className={participant.isSpeaking ? 'dot speaking' : 'dot'} />{participant.name || participant.identity}</p>
          ))}
        </section>

        <section className="panel transcript">
          <h2>Transcript</h2>
          {orderedTranscripts.length === 0 && <p className="muted">Waiting for speech…</p>}
          {orderedTranscripts.map((line) => (
            <p key={`${line.event_id}-${line.sequence}`} className={partials[line.track_sid] === line ? 'partial' : ''}>
              <strong>{line.speaker_name}:</strong> {line.text}
            </p>
          ))}
        </section>

        <section className="panel research">
          <h2>Research</h2>
          {Object.values(jobs).length === 0 && <p className="muted">Say “Decision Window, verify…”</p>}
          {Object.values(jobs).map((job) => (
            <article key={job.job_id}>
              <strong>{job.route} · {job.status.toUpperCase()}</strong>
              <span>{Math.max(0, Math.ceil((job.deadline_at_ms - now) / 1000))}s</span>
              <p>{job.query}</p>
            </article>
          ))}
          {answers.map((card) => (
            <article key={card.job_id} className="answer">
              <p>{card.concise_answer}</p>
              <small>{Math.round(card.confidence * 100)}% confidence</small>
              {card.citations.map((source) => (
                <button
                  key={source.url}
                  type="button"
                  className="source"
                  onClick={() => window.open(source.url, '_blank', 'noopener,noreferrer')}
                >
                  {source.title}
                </button>
              ))}
            </article>
          ))}
        </section>
      </div>
    </main>
  )
}

export default App
