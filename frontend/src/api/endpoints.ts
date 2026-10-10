import { api } from './client'
import type * as T from './types'

const h = (id: string) => `/homes/${encodeURIComponent(id)}`

export const Api = {
  config: () => api<T.PublicConfig>('/config'),
  signup: (username: string, password: string) => api<{ username: string; created: boolean }>('/auth/signup', { json: { username, password } }),
  cities: () => api<T.City[]>('/reference/cities'),
  retrofits: () => api<T.Retrofit[]>('/reference/retrofits'),

  myHomes: () => api<T.MyHome[]>('/homes'),
  home: (id: string) => api<T.Home>(h(id)),
  createHome: (body: T.HomeCreate) => api<{ home: T.Home; score: T.ScoreResult }>('/homes', { json: body }),
  score: (id: string) => api<T.ScoreResult>(`${h(id)}/score`),
  plan: (id: string) => api<T.Plan>(`${h(id)}/plan`),
  scenario: (id: string, body: T.ScenarioRequest, signal?: AbortSignal) => api<T.Scenario>(`${h(id)}/scenario`, { json: body, signal }),
  value: (id: string, retrofits: string[]) => api<T.ValueRange>(`${h(id)}/value`, { query: { retrofits } }),
  finance: (id: string, body: { retrofits: string[]; params: Record<string, number>; down_payment_inr: number }) =>
    api<T.Finance>(`${h(id)}/finance`, { json: body }),
  solar: (id: string, kw?: number) => api<T.Solar>(`${h(id)}/solar`, { query: { kw } }),
  subsidyApplication: (id: string) => api<T.SubsidyApplication>(`${h(id)}/subsidy-application`),
  roadmap: (id: string, budget: number, years: number, objective: 'inr' | 'co2' | 'kwh') =>
    api<T.Roadmap>(`${h(id)}/roadmap`, { query: { budget_inr: budget, years, objective } }),
  heatwave: (id: string) => api<T.Heatwave>(`${h(id)}/heatwave`),
  weatherSignature: (id: string) => api<T.WeatherSignature>(`${h(id)}/weather-signature`),
  journey: (id: string) => api<T.Journey>(`${h(id)}/journey`),
  addMemory: (id: string, body: T.MemoryIn) => api<T.MemoryResult>(`${h(id)}/memory`, { json: body }),
  telegramLink: (id: string) => api<T.TelegramLink>(`${h(id)}/telegram-link`, { method: 'POST' }),

  chat: (body: T.ChatIn) => api<T.ChatReply>('/advisor/chat', { json: body, timeoutMs: 60_000 }),
  transcribe: (file: Blob, language?: string) => {
    const form = new FormData()
    form.append('file', file, 'voice.webm')
    return api<T.Transcript>('/speech/transcribe', { form, query: { language }, timeoutMs: 60_000 })
  },
  tts: async (text: string, language: string) => {
    const r = await api<Response>('/speech/tts', { json: { text, language }, raw: true, timeoutMs: 60_000 })
    return r.blob()
  },
  parseBill: (file: File, homeId?: string) => {
    const form = new FormData()
    form.append('file', file, file.name)
    return api<T.BillParse>('/bills/parse', { form, query: { home_id: homeId }, timeoutMs: 90_000 })
  },

  realCity: (city: string) => api<T.CityClimate>(`/reference/real/city/${encodeURIComponent(city)}`),

  portfolioSummary: (city?: string, state?: string) => api<T.PortfolioSummary>('/portfolio/summary', { query: { city, state } }),
  portfolioMap: () => api<T.CityPoint[]>('/portfolio/map'),
  poorHomes: (limit: number, city?: string, state?: string) => api<T.PoorHome[]>('/portfolio/poor-homes', { query: { limit, city, state } }),
  ranking: (limit: number, city?: string, state?: string) => api<T.RankedHome[]>('/portfolio/ranking', { query: { limit, city, state } }),
  targets: (limit: number, city?: string) => api<T.Target[]>('/portfolio/targets', { query: { limit, city } }),
  rwaLeads: (limit: number, minHomes = 4) => api<T.RwaLead[]>('/portfolio/rwa-leads', { query: { limit, min_homes: minHomes } }),
}
