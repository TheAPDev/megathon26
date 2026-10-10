import { api, ApiError, setTokenProvider } from './client'

const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const envelope = (code: string, status = 400) => json(status, { error: { code, message: code, details: { retry_after_s: 12 }, request_id: 'rid1' } })

afterEach(() => {
  vi.unstubAllGlobals()
  setTokenProvider({ get: async () => null, refresh: async () => null, onUnauthorized: () => {} })
})

test('parses the backend error envelope into ApiError', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => envelope('rate_limited', 429)))
  const e = (await api('/x').catch((x) => x)) as ApiError
  expect(e).toBeInstanceOf(ApiError)
  expect([e.status, e.code, e.requestId, e.retryAfter]).toEqual([429, 'rate_limited', 'rid1', 12])
})

test('GET retries a 5xx, but writes are never retried', async () => {
  const f = vi.fn(async () => envelope('internal_error', 500))
  vi.stubGlobal('fetch', f)
  await api('/x').catch(() => null)
  expect(f).toHaveBeenCalledTimes(3)
  f.mockClear()
  await api('/x', { json: { a: 1 } }).catch(() => null)
  expect(f).toHaveBeenCalledTimes(1)
})

test('4xx is not retried', async () => {
  const f = vi.fn(async () => envelope('home_not_found', 404))
  vi.stubGlobal('fetch', f)
  await api('/x').catch(() => null)
  expect(f).toHaveBeenCalledTimes(1)
})

test('401 refreshes the token once and replays with the new bearer', async () => {
  const seen: (string | null)[] = []
  vi.stubGlobal('fetch', vi.fn(async (_u: string, init: RequestInit) => {
    const auth = (init.headers as Record<string, string>).Authorization ?? null
    seen.push(auth)
    return auth === 'Bearer new' ? json(200, { ok: true }) : envelope('invalid_token', 401)
  }))
  setTokenProvider({ get: async () => 'old', refresh: async () => 'new', onUnauthorized: () => {} })
  expect(await api('/x')).toEqual({ ok: true })
  expect(seen).toEqual(['Bearer old', 'Bearer new'])
})

test('sends a request id and repeated query params', async () => {
  const f = vi.fn(async () => json(200, {}))
  vi.stubGlobal('fetch', f)
  await api('/homes/H1/value', { query: { retrofits: ['a', 'b'], skip: undefined } })
  const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit]
  expect(url).toBe('/homes/H1/value?retrofits=a&retrofits=b')
  expect((init.headers as Record<string, string>)['X-Request-ID']).toMatch(/^[0-9a-f]{16}$/)
})
