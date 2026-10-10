// Screen 4 (AI Saathi) + Differentiator 2 (verified-number advisor). Every figure in an answer is checked by the
// backend against the engine's tool outputs; the verification panel shows which ones, and what produced them.
import { useMutation } from '@tanstack/react-query'
import {
  AlertTriangle, ArrowRight, Bot, CheckCircle2, CircleDot, Database, History, Mic, Plus, Send, ShieldCheck, Square, User, Wrench,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ApiError, describeError } from '../api/client'
import { Api } from '../api/endpoints'
import { useAddMemory, useJourney, useRetrofits } from '../api/hooks'
import type { ChatReply, Journey } from '../api/types'
import { Card, Empty, Q, Tabs, Toggle, useCooldown, useToast } from '../components/ui'
import { figures, segments } from '../lib/figures'
import { humanize, inr, num } from '../lib/format'
import { retrofitIcon } from '../lib/icons'
import { useSession } from '../state/session'

type Msg = { id: string; role: 'user' | 'assistant'; text: string; reply?: ChatReply; status: 'sending' | 'done' | 'error'; error?: string; at: Date }

const PROMPTS = {
  en: ['Why is my score what it is?', 'What if I set the AC to 26?', 'Is rooftop solar worth it?', 'Cheapest fix under ₹10,000'],
  hi: ['Mera score kam kyun hai?', 'AC 26 pe rakhun to kya hoga?', 'Kya solar lagwana sahi hai?', '₹10,000 se kam ka sabse sasta upay'],
}
// Where each engine tool's numbers can be seen in full in the app.
const TOOL_LINK: Record<string, { to: string; label: string }> = {
  get_score: { to: '/', label: 'Open dashboard' },
  get_recommendations: { to: '/studio', label: 'Open studio' },
  run_scenario: { to: '/studio', label: 'Open studio' },
  get_finance_plan: { to: '/paisa', label: 'Open Paisa' },
  get_solar_quote: { to: '/paisa', label: 'Open Paisa' },
  get_roadmap: { to: '/paisa', label: 'Open Paisa' },
  get_heatwave: { to: '/garmi', label: 'Open Garmi mode' },
}

export default function Saathi() {
  const id = useSession((s) => s.activeHomeId)!
  const lang = useSession((s) => s.language)
  const [msgs, setMsgs] = useState<Msg[]>([])
  const [text, setText] = useState('')
  const [useLlm, setUseLlm] = useState(true)
  const [speak, setSpeak] = useState(false)
  const [voiceOk, setVoiceOk] = useState(true)
  const [cool, setCool] = useCooldown()
  const [focus, setFocus] = useState<string | null>(null)
  const [tab, setTab] = useState<'verify' | 'memory' | 'journey'>('verify')
  const listRef = useRef<HTMLDivElement>(null)
  const toast = useToast()
  useEffect(() => setMsgs([]), [id])
  useEffect(() => listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' }), [msgs])

  const chat = useMutation({ mutationFn: Api.chat })
  const playing = useRef<HTMLAudioElement | null>(null)

  const send = async (message: string) => {
    const m = message.trim()
    if (!m || chat.isPending || cool > 0) return
    const uid = crypto.randomUUID(), aid = crypto.randomUUID()
    setMsgs((s) => [...s, { id: uid, role: 'user', text: m, status: 'done', at: new Date() }, { id: aid, role: 'assistant', text: '', status: 'sending', at: new Date() }])
    setText('')
    try {
      const r = await chat.mutateAsync({ home_id: id, message: m, language: lang, use_llm: useLlm })
      setMsgs((s) => s.map((x) => (x.id === aid ? { ...x, text: r.answer, reply: r, status: 'done', at: new Date() } : x)))
      setFocus(aid)
      setTab('verify')
      if (speak && voiceOk) {
        try {
          const blob = await Api.tts(r.answer.slice(0, 1500), r.language)
          playing.current?.pause()
          const url = URL.createObjectURL(blob)
          const a = new Audio(url)
          a.onended = () => URL.revokeObjectURL(url)
          playing.current = a
          await a.play()
        } catch (e) {
          if (e instanceof ApiError && e.code === 'tts_unavailable') { setSpeak(false); toast({ kind: 'warn', title: 'Spoken replies are unavailable right now' }) }
        }
      }
    } catch (e) {
      if (e instanceof ApiError && e.code === 'rate_limited') setCool(e.retryAfter ?? 60)
      setMsgs((s) => s.map((x) => (x.id === aid ? { ...x, status: 'error', error: describeError(e) } : x)))
    }
  }
  const retry = (aid: string) => {
    const i = msgs.findIndex((x) => x.id === aid)
    const q = msgs[i - 1]?.text
    setMsgs((s) => s.filter((_, j) => j !== i && j !== i - 1))
    if (q) void send(q)
  }
  const focused = msgs.find((m) => m.id === focus)?.reply ?? [...msgs].reverse().find((m) => m.reply)?.reply ?? null

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">AI Saathi: advisor, voice & memory</h1>
          <p className="page-sub">Answers from your own home's numbers, with every figure checked.</p>
        </div>
        <span className="chip"><ShieldCheck /> Numbers checked against your home data</span>
      </div>
      <div className="grid g-12">
        <Card className="span-8" title={<><Bot /> Conversation</>}>
          <div ref={listRef} className="stack" style={{ gap: 14, maxHeight: '58vh', minHeight: 320, overflowY: 'auto', paddingRight: 4 }} aria-live="polite">
            {msgs.length === 0 && <Greeting onPick={send} lang={lang} />}
            {msgs.map((m) => m.role === 'user' ? (
              <div key={m.id} className="row" style={{ justifyContent: 'flex-end', alignItems: 'flex-start' }}>
                <div style={{ background: 'var(--mint-2)', border: '1px solid var(--line)', borderRadius: '14px 14px 4px 14px', padding: '10px 14px', maxWidth: '80%' }}>{m.text}</div>
                <span className="icon-btn" aria-hidden><User size={16} /></span>
              </div>
            ) : (
              <AssistantBubble key={m.id} m={m} selected={focus === m.id} onSelect={() => { setFocus(m.id); setTab('verify') }} onRetry={() => retry(m.id)} />
            ))}
          </div>
          {msgs.length > 0 && (
            <div className="row wrap" style={{ gap: 8, marginTop: 12 }}>
              {PROMPTS[lang].map((p) => <button key={p} className="chip outline" style={{ cursor: 'pointer' }} onClick={() => send(p)} disabled={chat.isPending}>{p}</button>)}
            </div>
          )}
          <Composer text={text} setText={setText} onSend={() => send(text)} busy={chat.isPending} cool={cool}
            voiceOk={voiceOk} setVoiceOk={setVoiceOk} onTranscript={(t) => send(t)} lang={lang}
            useLlm={useLlm} setUseLlm={setUseLlm} speak={speak} setSpeak={setSpeak} />
        </Card>

        <div className="span-4 stack" style={{ gap: 18 }}>
          <div className="card" style={{ padding: 0 }}>
            <div style={{ padding: '6px 14px 0' }}>
              <Tabs label="Side panel" value={tab} onChange={setTab} tabs={[{ key: 'verify', label: 'Verification' }, { key: 'memory', label: 'Memory' }, { key: 'journey', label: 'Journey' }]} />
            </div>
            <div style={{ padding: 18 }}>
              {tab === 'verify' && <Verification r={focused} />}
              {tab === 'memory' && <MemoryVault id={id} />}
              {tab === 'journey' && <JourneyPanel id={id} />}
            </div>
          </div>
        </div>
      </div>
    </>
  )
}

function Greeting({ onPick, lang }: { onPick: (s: string) => void; lang: 'en' | 'hi' }) {
  return (
    <div className="stack" style={{ alignItems: 'flex-start', gap: 14, padding: '8px 0' }}>
      <div className="row"><span className="tile-ico"><Bot /></span><div><b>Namaste! I'm your Green Ghar Saathi.</b><div className="small muted">Ask about your score, a measure, solar or savings, in English, Hindi or Hinglish.</div></div></div>
      <div className="row wrap" style={{ gap: 8 }}>{PROMPTS[lang].map((p) => <button key={p} className="chip outline" style={{ cursor: 'pointer' }} onClick={() => onPick(p)}>{p} <ArrowRight /></button>)}</div>
    </div>
  )
}

function Highlighted({ text, unsupported }: { text: string; unsupported: string[] }) {
  const segs = useMemo(() => segments(text, unsupported), [text, unsupported])
  return (
    <p style={{ whiteSpace: 'pre-wrap', lineHeight: 1.7 }}>
      {segs.map((s, i) => !s.status ? <span key={i}>{s.text}</span> : (
        <mark key={i} title={s.status === 'verified' ? 'Matches an engine output' : 'Could not be matched to an engine output'}
          style={{ background: s.status === 'verified' ? 'var(--mint)' : 'var(--amber-bg)', color: s.status === 'verified' ? 'var(--green)' : '#8a5714', borderRadius: 6, padding: '1px 5px', fontWeight: 600 }}>
          {s.text}{s.status === 'unverified' && ' ⚠'}
        </mark>
      ))}
    </p>
  )
}

function AssistantBubble({ m, selected, onSelect, onRetry }: { m: Msg; selected: boolean; onSelect: () => void; onRetry: () => void }) {
  if (m.status === 'sending')
    return <div className="row small muted" role="status"><span className="tile-ico" style={{ width: 34, height: 34 }}><Bot size={16} /></span><SendingText /></div>
  if (m.status === 'error')
    return (
      <div className="alert red" role="alert"><AlertTriangle /><div className="small" style={{ flex: 1 }}>{m.error}</div><button className="btn ghost" onClick={onRetry}>Retry</button></div>
    )
  const r = m.reply!
  const g = r.grounding
  return (
    <div className="row" style={{ alignItems: 'flex-start' }}>
      <span className="tile-ico" style={{ width: 34, height: 34 }} aria-hidden><Bot size={16} /></span>
      <div className="card" style={{ flex: 1, padding: 16, boxShadow: 'none', borderColor: selected ? 'var(--leaf)' : undefined }}>
        <div className="row between wrap">
          <button className={`chip ${g.grounded ? '' : 'amber'}`} onClick={onSelect} style={{ cursor: 'pointer', border: 0 }} aria-label={`${g.badge}. Show verification`}>
            {g.grounded ? <CheckCircle2 /> : <AlertTriangle />}{g.badge}
          </button>
          <span className="tiny muted">{m.at.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}{r.cached ? ' · instant' : ''}</span>
        </div>
        <div style={{ margin: '10px 0' }}><Highlighted text={r.answer} unsupported={g.unsupported} /></div>
        <div className="row wrap" style={{ gap: 6 }}>
          {r.tool_calls.map((t, i) => <span key={i} className="chip grey" title={JSON.stringify(t.args)}><Wrench />{t.tool}</span>)}
        </div>
        {r.provider === 'template' && <p className="tiny muted" style={{ marginTop: 8 }}>{r.fallback_reason ? 'The AI draft contained figures that could not be verified, so this answer was built directly from your numbers.' : 'Answered directly from your numbers without the AI model.'}</p>}
        {r.caveats.length > 0 && <p className="tiny muted" style={{ marginTop: 4 }}>{r.caveats.join(' ')}</p>}
      </div>
    </div>
  )
}

function SendingText() {
  const [slow, setSlow] = useState(false)
  useEffect(() => { const t = setTimeout(() => setSlow(true), 1500); return () => clearTimeout(t) }, [])
  return <span>{slow ? 'Checking the numbers…' : 'Thinking…'}</span>
}

function Verification({ r }: { r: ChatReply | null }) {
  if (!r) return <Empty title="No answer yet" icon={<ShieldCheck />}><span className="small">Ask a question; each figure in the answer is listed here with whether it matched the engine.</span></Empty>
  const g = r.grounding
  const bad = new Set(g.unsupported)
  const figs = figures(r.answer).filter((f) => f.counted)
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="row"><span className="tile-ico" style={{ background: g.grounded ? 'var(--mint)' : 'var(--amber-bg)', color: g.grounded ? 'var(--green)' : 'var(--amber)' }}>{g.grounded ? <CheckCircle2 /> : <AlertTriangle />}</span>
        <div><b>Figure verification</b><div className="small muted">{g.verified} of {g.total} figures verified</div></div></div>
      {figs.length === 0 ? <p className="small muted">This answer contains no figures to check.</p> : (
        <table className="table">
          <thead><tr><th scope="col">Figure</th><th scope="col">Status</th></tr></thead>
          <tbody>
            {figs.map((f, i) => (
              <tr key={i}><td><b>{f.token}</b></td><td>{bad.has(f.token) ? <span className="chip amber"><AlertTriangle />Not verified</span> : <span className="chip"><CheckCircle2 />Matches engine output</span>}</td></tr>
            ))}
          </tbody>
        </table>
      )}
      <div>
        <b className="small">Calculations used for this answer</b>
        <div className="stack" style={{ marginTop: 8, gap: 6 }}>
          {r.tool_calls.length === 0 && <span className="small muted">None.</span>}
          {r.tool_calls.map((t, i) => (
            <div key={i} className="list-item" style={{ padding: 10 }}>
              <Wrench size={16} />
              <span style={{ flex: 1, minWidth: 0 }}><b className="small">{t.tool}</b><div className="tiny muted" style={{ overflowWrap: 'anywhere' }}>{Object.keys(t.args).length ? JSON.stringify(t.args) : 'your home data'}</div></span>
              {TOOL_LINK[t.tool] && <Link className="tiny" to={TOOL_LINK[t.tool].to}>{TOOL_LINK[t.tool].label}</Link>}
            </div>
          ))}
        </div>
      </div>
      <p className="tiny muted">Answered by {r.provider === 'template' ? 'Green Ghar templates' : `${r.provider}${r.model ? ` (${r.model})` : ''}`} in {num(r.latency_s, 2)} s. Figures come from the Green Ghar engine: your bills, BEE appliance data, state tariffs and CEA emission factors. A figure that cannot be matched is never shown as fact.</p>
    </div>
  )
}

const MEMORY_KEYS: { key: string; label: string; kind: 'constraint' | 'preference'; input: 'number' | 'retrofit' | 'tenure' | 'language' }[] = [
  { key: 'budget_inr', label: 'Budget limit (₹)', kind: 'constraint', input: 'number' },
  { key: 'exclude', label: "Don't suggest", kind: 'constraint', input: 'retrofit' },
  { key: 'tenure', label: 'I rent / own', kind: 'constraint', input: 'tenure' },
  { key: 'language', label: 'Preferred language', kind: 'preference', input: 'language' },
]
const memLabel = (k: string) => ({ budget_inr: 'Budget limit', exclude: 'Excluded', include: 'Allowed again', tenure: 'Tenure', language: 'Language', rejected: 'Rejected', accepted: 'Accepted', saved_plan: 'Saved plan' } as Record<string, string>)[k] ?? humanize(k)

function MemoryVault({ id }: { id: string }) {
  const j = useJourney(id)
  const cat = useRetrofits()
  const names = Object.fromEntries((cat.data ?? []).map((r) => [r.retrofit_id, r.name]))
  const add = useAddMemory(id)
  const toast = useToast()
  const [key, setKey] = useState(MEMORY_KEYS[0].key)
  const [val, setVal] = useState('')
  const spec = MEMORY_KEYS.find((k) => k.key === key)!
  const fmt = (k: string, raw: string) => {
    let v: unknown = raw
    try { v = JSON.parse(raw) } catch { /* plain string */ }
    if (k === 'budget_inr') return Number(v) ? inr(Number(v)) : 'none'
    if (k === 'exclude' || k === 'include' || k === 'rejected' || k === 'accepted') return names[String(v)] ?? humanize(String(v))
    if (k === 'saved_plan') { try { return (JSON.parse(String(v)) as string[]).map((x) => names[x] ?? x).join(', ') } catch { return String(v) } }
    return humanize(String(v))
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    const value: string | number = spec.input === 'number' ? Number(val.replace(/[^\d]/g, '')) : val
    if (value === '' || (spec.input === 'number' && !(Number(value) >= 1000))) return
    add.mutate({ kind: spec.kind, key, value }, {
      onSuccess: (r) => {
        const c = r.what_changed.changes
        toast({ kind: 'ok', title: 'Saathi will remember that', body: c.length ? c.slice(0, 3).map((x) => `${names[x.retrofit_id] ?? x.retrofit_id}: ${x.change === 'suitability' ? `now ${String(x.to)}` : x.change === 'over_budget' ? (x.to ? 'over budget' : 'within budget') : x.change}`).join('; ') : 'Your plan stays the same.' })
        setVal('')
      },
      onError: (e) => toast({ kind: 'error', title: 'Could not save', body: describeError(e) }),
    })
  }
  return (
    <div className="stack">
      <div className="row"><Database size={18} /><b>What Saathi remembers about you</b></div>
      <Q q={j} lines={4} empty={(d) => (d.memory.length ? null : <p className="small muted">Nothing yet. Add a budget, an exclusion or your language below.</p>)}>
        {(d: Journey) => (
          <div className="stack" style={{ gap: 6 }}>
            {d.memory.slice(-12).reverse().map((m) => (
              <div key={m.memory_id} className="row between small" style={{ borderBottom: '1px solid var(--line-2)', paddingBottom: 6 }}>
                <span className="muted">{memLabel(m.key)}</span><b style={{ textAlign: 'right' }}>{fmt(m.key, m.value)}</b>
              </div>
            ))}
          </div>
        )}
      </Q>
      <form className="card stack" style={{ boxShadow: 'none', padding: 12 }} onSubmit={submit}>
        <b className="small row"><Plus size={16} /> Add a new preference</b>
        <div className="row">
          <select className="input" value={key} onChange={(e) => { setKey(e.target.value); setVal('') }} aria-label="What to remember">
            {MEMORY_KEYS.map((k) => <option key={k.key} value={k.key}>{k.label}</option>)}
          </select>
        </div>
        <div className="row">
          {spec.input === 'number' && <input className="input" inputMode="numeric" placeholder="2,00,000" value={val} onChange={(e) => setVal(e.target.value)} aria-label="Budget in rupees" />}
          {spec.input === 'retrofit' && (
            <select className="input" value={val} onChange={(e) => setVal(e.target.value)} aria-label="Measure"><option value="">Choose a measure</option>{(cat.data ?? []).map((r) => <option key={r.retrofit_id} value={r.retrofit_id}>{r.name}</option>)}</select>
          )}
          {spec.input === 'tenure' && (
            <select className="input" value={val} onChange={(e) => setVal(e.target.value)} aria-label="Tenure"><option value="">Choose</option><option value="renting">I rent this home</option><option value="owning">I own this home</option></select>
          )}
          {spec.input === 'language' && (
            <select className="input" value={val} onChange={(e) => setVal(e.target.value)} aria-label="Language"><option value="">Choose</option><option value="en">English</option><option value="hi">Hindi</option><option value="hinglish">Hinglish</option></select>
          )}
          <button className="btn primary" disabled={add.isPending || !val}>Add</button>
        </div>
      </form>
    </div>
  )
}

function JourneyPanel({ id }: { id: string }) {
  const j = useJourney(id)
  const cat = useRetrofits()
  const names = Object.fromEntries((cat.data ?? []).map((r) => [r.retrofit_id, r.name]))
  return (
    <Q q={j} lines={5}>
      {(d) => (
        <div className="stack">
          <div className="row"><History size={18} /><b>Your journey</b></div>
          {d.completed_retrofits.length === 0 ? <p className="small muted">No completed upgrades recorded yet.</p> : d.completed_retrofits.map((e, i) => {
            const I = retrofitIcon(e.retrofit_id)
            return (
              <div key={i} className="row"><CheckCircle2 size={18} color="var(--leaf)" /><span className="tile-ico" style={{ width: 34, height: 34 }}><I size={16} /></span>
                <span style={{ flex: 1 }}><b className="small">{names[e.retrofit_id] ?? humanize(e.retrofit_id)}</b><div className="tiny muted">{String(e.completed_month ?? '')}{typeof e.cost_inr === 'number' ? ` · ${inr(e.cost_inr)}` : ''}</div></span></div>
            )
          })}
          <div className="sep" />
          <b className="small">Upcoming, from your plan</b>
          {d.plan.recommendations.filter((r) => !['Infeasible', 'Excluded'].includes(r.suitability)).slice(0, 3).map((r, i) => (
            <Link key={r.retrofit_id} className="list-item" to={`/studio?r=${r.retrofit_id}`} style={{ padding: 10 }}>
              <span className="chip grey">{i + 1}</span>
              <span style={{ flex: 1 }}><b className="small">{r.name}</b><div className="tiny muted">Save {inr(r.saving_inr_year)}/year</div></span><CircleDot size={14} />
            </Link>
          ))}
        </div>
      )}
    </Q>
  )
}

function Composer({ text, setText, onSend, busy, cool, voiceOk, setVoiceOk, onTranscript, lang, useLlm, setUseLlm, speak, setSpeak }: {
  text: string; setText: (s: string) => void; onSend: () => void; busy: boolean; cool: number; voiceOk: boolean; setVoiceOk: (b: boolean) => void
  onTranscript: (t: string) => void; lang: string; useLlm: boolean; setUseLlm: (b: boolean) => void; speak: boolean; setSpeak: (b: boolean) => void
}) {
  const [rec, setRec] = useState<MediaRecorder | null>(null)
  const [secs, setSecs] = useState(0)
  const [hearing, setHearing] = useState(false)
  const toast = useToast()
  useEffect(() => {
    if (!rec) return
    const t = setInterval(() => setSecs((s) => { if (s >= 59) rec.stop(); return s + 1 }), 1000)
    return () => clearInterval(t)
  }, [rec])
  const start = async () => {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setVoiceOk(false); return }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const r = new MediaRecorder(stream)
      const chunks: Blob[] = []
      r.ondataavailable = (e) => chunks.push(e.data)
      r.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop())
        setRec(null)
        setSecs(0)
        setHearing(true)
        try {
          const t = await Api.transcribe(new Blob(chunks, { type: r.mimeType || 'audio/webm' }), lang)
          if (t.text) onTranscript(t.text)
          else toast({ kind: 'warn', title: "Didn't catch that", body: 'Try again a little closer to the mic.' })
        } catch (e) {
          if (e instanceof ApiError && e.code === 'stt_unavailable') setVoiceOk(false)
          toast({ kind: 'error', title: 'Voice is unavailable right now', body: 'Please type your question.' })
        } finally { setHearing(false) }
      }
      r.start()
      setRec(r)
    } catch {
      toast({ kind: 'warn', title: 'Microphone blocked', body: 'Allow microphone access in your browser settings, then try again.' })
    }
  }
  const len = text.length
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSend() }} className="card" style={{ boxShadow: 'none', padding: 12, marginTop: 14 }}>
      <textarea className="input" rows={2} maxLength={2000} placeholder="Ask anything about your home, savings or upgrades…" value={text}
        onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); onSend() } }}
        aria-label="Message" style={{ border: 0, resize: 'none', padding: 4 }} />
      <div className="row wrap between" style={{ marginTop: 6 }}>
        <span className="tiny" style={{ color: len > 1800 ? 'var(--red)' : 'var(--ink-3)' }}>{len}/2000{cool > 0 ? ` · try again in ${cool}s` : ''}</span>
        <div className="row wrap" style={{ gap: 14 }}>
          <label className="row small" style={{ gap: 6 }}><Toggle checked={speak} onChange={setSpeak} label="Speak replies" />Speak replies</label>
          <label className="row small" style={{ gap: 6 }}><Toggle checked={useLlm} onChange={setUseLlm} label="Use AI model" />Use AI</label>
          {voiceOk && (
            <button type="button" className="icon-btn" onClick={() => (rec ? rec.stop() : start())} aria-label={rec ? 'Stop recording' : 'Record a voice question'} disabled={hearing || busy}
              style={rec ? { background: 'var(--red-bg)', color: 'var(--red)' } : undefined}>
              {rec ? <Square size={16} /> : <Mic size={16} />}
            </button>
          )}
          {rec && <span className="tiny" style={{ color: 'var(--red)' }}>Recording {secs}s</span>}
          {hearing && <span className="tiny muted">Listening…</span>}
          <button className="btn primary" disabled={busy || !text.trim() || cool > 0 || len > 2000} aria-label="Send"><Send /></button>
        </div>
      </div>
    </form>
  )
}
