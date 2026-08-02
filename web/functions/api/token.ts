import { AccessToken, RoomAgentDispatch, RoomConfiguration } from 'livekit-server-sdk'

type Env = {
  LIVEKIT_URL: string
  LIVEKIT_API_KEY: string
  LIVEKIT_API_SECRET: string
  LIVEKIT_AGENT_NAME?: string
}

type Context = { request: Request; env: Env }

const json = (body: object, status = 200) => new Response(JSON.stringify(body), {
  status,
  headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' },
})

export async function onRequestPost({ request, env }: Context): Promise<Response> {
  let value: unknown
  try {
    value = await request.json()
  } catch {
    return json({ error: 'Invalid JSON' }, 400)
  }
  if (!value || typeof value !== 'object') return json({ error: 'Invalid request' }, 400)

  const body = value as Record<string, unknown>
  const roomCode = typeof body.roomName === 'string' ? body.roomName.trim() : ''
  const roomSlug = roomCode
    .replace(/^decision-window-/i, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 60)
  const roomName = `decision-window-${roomSlug}`
  const participantName = typeof body.participantName === 'string' ? body.participantName.trim() : ''
  const participantIdentity = typeof body.participantIdentity === 'string' ? body.participantIdentity : ''
  if (!roomSlug) return json({ error: 'Enter a room code' }, 400)
  if (!participantName || participantName.length > 80 || !/^[a-z0-9-]{1,80}$/i.test(participantIdentity)) {
    return json({ error: 'Invalid participant' }, 400)
  }
  if (!env.LIVEKIT_URL || !env.LIVEKIT_API_KEY || !env.LIVEKIT_API_SECRET) {
    return json({ error: 'LiveKit is not configured' }, 503)
  }

  const token = new AccessToken(env.LIVEKIT_API_KEY, env.LIVEKIT_API_SECRET, {
    identity: participantIdentity,
    name: participantName,
    ttl: '1h',
  })
  token.addGrant({
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canSubscribe: true,
    canPublishData: true,
  })
  if (body.dispatchAgent === true) {
    token.roomConfig = new RoomConfiguration({
      agents: [new RoomAgentDispatch({ agentName: env.LIVEKIT_AGENT_NAME || 'interject-build' })],
    })
  }

  return json({ roomName, serverUrl: env.LIVEKIT_URL, participantToken: await token.toJwt() })
}
