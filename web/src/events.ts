export const topic = 'dw.event'

export type DwEvent = {
  type: string
  ts_ms: number
  payload: Record<string, unknown>
}

export type Transcript = {
  event_id: string
  speaker_name: string
  track_sid: string
  text: string
  sequence: number
  start_ms: number
}

export type ResearchJob = {
  job_id: string
  asker_name: string
  query: string
  route: 'INSTANT' | 'QUICK'
  status: 'searching' | 'completed' | 'expired' | 'failed'
  deadline_at_ms: number
}

export type Answer = {
  job_id: string
  question: string
  concise_answer: string
  confidence: number
  citations: Array<{ title: string; url: string }>
}

const text = (value: unknown) => (typeof value === 'string' ? value : '')
const number = (value: unknown) => (typeof value === 'number' ? value : 0)

export function decodeEvent(data: Uint8Array): DwEvent | null {
  try {
    const value: unknown = JSON.parse(new TextDecoder().decode(data))
    if (!value || typeof value !== 'object') return null
    const event = value as Partial<DwEvent>
    if (typeof event.type !== 'string' || typeof event.ts_ms !== 'number') return null
    if (!event.payload || typeof event.payload !== 'object') return null
    return event as DwEvent
  } catch {
    return null
  }
}

export function transcript(payload: Record<string, unknown>): Transcript | null {
  const event_id = text(payload.event_id)
  const track_sid = text(payload.track_sid)
  if (!event_id || !track_sid) return null
  return {
    event_id,
    track_sid,
    speaker_name: text(payload.speaker_name) || 'Unknown',
    text: text(payload.text),
    sequence: number(payload.sequence),
    start_ms: number(payload.start_ms),
  }
}

export function research(payload: Record<string, unknown>): ResearchJob | null {
  const job_id = text(payload.job_id)
  if (!job_id) return null
  return {
    job_id,
    asker_name: text(payload.asker_name),
    query: text(payload.query),
    route: text(payload.route) === 'INSTANT' ? 'INSTANT' : 'QUICK',
    status: (text(payload.status) || 'searching') as ResearchJob['status'],
    deadline_at_ms: number(payload.deadline_at_ms),
  }
}

export function answer(payload: Record<string, unknown>): Answer | null {
  const job_id = text(payload.job_id)
  if (!job_id) return null
  const citations = Array.isArray(payload.citations)
    ? payload.citations.flatMap((item) => {
        if (!item || typeof item !== 'object') return []
        const source = item as Record<string, unknown>
        const url = text(source.url)
        return /^https?:\/\//.test(url) ? [{ title: text(source.title) || url, url }] : []
      })
    : []
  return {
    job_id,
    question: text(payload.question),
    concise_answer: text(payload.concise_answer),
    confidence: number(payload.confidence),
    citations,
  }
}
