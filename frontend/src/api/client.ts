// One fetch wrapper for the whole app: request ids, the backend's error envelope, auth headers,
// timeouts, safe retries (GET only) and a single token refresh on 401.

export const API_BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
    public requestId: string | null = null,
  ) {
    super(message)
  }
  get retryAfter(): number | null {
    const v = this.details?.retry_after_s
    return typeof v === 'number' ? v : null
  }
}

type TokenProvider = { get: () => Promise<string | null>; refresh: () => Promise<string | null>; onUnauthorized: () => void }
let tokens: TokenProvider = { get: async () => null, refresh: async () => null, onUnauthorized: () => {} }
export function setTokenProvider(p: TokenProvider) {
  tokens = p
}

export interface RequestOpts {
  method?: 'GET' | 'POST'
  query?: Record<string, string | number | boolean | string[] | null | undefined>
  json?: unknown
  form?: FormData
  signal?: AbortSignal
  timeoutMs?: number
  raw?: boolean // return the Response (binary bodies)
}

function buildUrl(path: string, query?: RequestOpts['query']) {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v === undefined || v === null || v === '') continue
    if (Array.isArray(v)) v.forEach((x) => qs.append(k, x))
    else qs.append(k, String(v))
  }
  const s = qs.toString()
  return `${API_BASE}${path}${s ? `?${s}` : ''}`
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

async function once(path: string, o: RequestOpts, token: string | null): Promise<Response> {
  const headers: Record<string, string> = { 'X-Request-ID': crypto.randomUUID().replace(/-/g, '').slice(0, 16) }
  if (token) headers.Authorization = `Bearer ${token}`
  let body: BodyInit | undefined
  if (o.json !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(o.json)
  } else if (o.form) body = o.form
  const timeout = AbortSignal.timeout(o.timeoutMs ?? 30_000)
  const signal = o.signal ? AbortSignal.any([o.signal, timeout]) : timeout
  return fetch(buildUrl(path, o.query), { method: o.method ?? (body ? 'POST' : 'GET'), headers, body, signal })
}

async function toError(r: Response): Promise<ApiError> {
  const rid = r.headers.get('X-Request-ID')
  try {
    const j = await r.json()
    const e = j?.error ?? {}
    return new ApiError(r.status, e.code ?? 'http_error', e.message ?? r.statusText, e.details ?? {}, e.request_id ?? rid)
  } catch {
    return new ApiError(r.status, 'http_error', r.statusText || 'Request failed', {}, rid)
  }
}

export async function api<T>(path: string, o: RequestOpts = {}): Promise<T> {
  const method = o.method ?? (o.json !== undefined || o.form ? 'POST' : 'GET')
  const attempts = method === 'GET' ? 3 : 1 // never auto-retry writes
  let token = await tokens.get()
  let refreshed = false
  for (let i = 0; ; i++) {
    let r: Response
    try {
      r = await once(path, { ...o, method }, token)
    } catch (e) {
      if ((e as Error).name === 'AbortError' && o.signal?.aborted) throw e
      if (i + 1 < attempts) {
        await sleep(400 * 2 ** i)
        continue
      }
      const timedOut = (e as Error).name === 'TimeoutError'
      throw new ApiError(0, timedOut ? 'timeout' : 'network_error', timedOut ? 'The server took too long to answer.' : 'Could not reach the server. Check your connection.')
    }
    if (r.ok) return (o.raw ? r : r.status === 204 ? undefined : await r.json()) as T
    if (r.status === 401 && !refreshed) {
      refreshed = true
      const t = await tokens.refresh()
      if (t) {
        token = t
        i--
        continue
      }
      tokens.onUnauthorized()
    }
    if (method === 'GET' && r.status >= 500 && i + 1 < attempts) {
      await sleep(400 * 2 ** i)
      continue
    }
    throw await toError(r)
  }
}

/** Human message for an error, never the raw stack. */
export function describeError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === 'rate_limited') return `Too many requests. Try again in ${e.retryAfter ?? 60} seconds.`
    if (e.status === 0) return e.message
    return e.message || 'Something went wrong.'
  }
  return 'Something went wrong.'
}
