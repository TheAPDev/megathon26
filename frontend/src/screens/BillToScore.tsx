// Differentiator 1: bill photo -> score. Upload, OCR (Gemini Flash, Tesseract fallback), review every month,
// create the home, store the bill against it, land on the dashboard. Also hands the home over to Telegram.
import { AlertTriangle, CheckCircle2, CircleDashed, FileScan, Loader2, PencilLine, Send, ShieldCheck, UploadCloud } from 'lucide-react'
import { useRef, useState, type DragEvent, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { ApiError, describeError } from '../api/client'
import { Api } from '../api/endpoints'
import { useCities, useConfig, useCreateHome } from '../api/hooks'
import type { BillParse, HomeCreate } from '../api/types'
import { Card, Stepper, useToast } from '../components/ui'
import { MONTHS, num } from '../lib/format'
import { useSession } from '../state/session'

const MIME = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf']
const MAX = 8 * 1024 * 1024
type Stage = 'upload' | 'reading' | 'review'

/** Phone photos are often 5-12 MB: shrink images to 2000 px / JPEG 0.85 before upload. PDFs go as they are. */
async function prepare(file: File): Promise<File> {
  if (!file.type.startsWith('image/') || file.size < 1.5 * 1024 * 1024) return file
  try {
    const bmp = await createImageBitmap(file)
    const s = Math.min(1, 2000 / Math.max(bmp.width, bmp.height))
    const c = document.createElement('canvas')
    c.width = Math.round(bmp.width * s)
    c.height = Math.round(bmp.height * s)
    c.getContext('2d')!.drawImage(bmp, 0, 0, c.width, c.height)
    const blob = await new Promise<Blob | null>((r) => c.toBlob(r, 'image/jpeg', 0.85))
    return blob ? new File([blob], file.name.replace(/\.\w+$/, '.jpg'), { type: 'image/jpeg' }) : file
  } catch {
    return file
  }
}

export default function BillToScore() {
  const [sp] = useSearchParams()
  const first = sp.get('first') === '1'
  const [stage, setStage] = useState<Stage>('upload')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [parsed, setParsed] = useState<BillParse | null>(null)
  const [ocrDown, setOcrDown] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [drag, setDrag] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const choose = async (f: File | undefined) => {
    setErr(null)
    if (!f) return
    if (!MIME.includes(f.type)) return setErr('Use a JPG, PNG or WEBP photo, or a PDF of the bill.')
    const ready = await prepare(f)
    if (ready.size > MAX) return setErr('That file is over 8 MB. Take a closer photo of the bill or export a smaller PDF.')
    setFile(ready)
    setPreview(ready.type.startsWith('image/') ? URL.createObjectURL(ready) : null)
    setStage('reading')
    try {
      const r = await Api.parseBill(ready)
      setParsed(r)
      setStage('review')
    } catch (e) {
      if (e instanceof ApiError && e.code === 'ocr_unavailable') {
        setOcrDown(true)
        setParsed({ monthly_kwh: Array(12).fill(null), months_found: 0, warnings: [] })
        setStage('review')
      } else {
        setErr(describeError(e))
        setStage('upload')
      }
    }
  }
  const manual = () => {
    setParsed({ monthly_kwh: Array(12).fill(null), months_found: 0, warnings: [] })
    setFile(null)
    setStage('review')
  }
  const onDrop = (e: DragEvent) => { e.preventDefault(); setDrag(false); void choose(e.dataTransfer.files?.[0]) }

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Instant bill photo to score</h1>
          <p className="page-sub">{first ? "Let's add your home first. " : ''}Upload your electricity bill and get your home's efficiency score in about a minute.</p>
        </div>
        <div className="meta-card"><FileScan size={20} /><div><b>Works with DISCOM bills</b><div className="tiny">PDF, JPG, PNG or WEBP, up to 8 MB</div></div></div>
      </div>

      <ol className="card row wrap" style={{ listStyle: 'none', margin: 0, gap: 22 }} aria-label="Progress">
        {[['Upload bill', 'PDF or image'], ['Reading', 'We extract your monthly units'], ['Review & score', 'Check the numbers, get your score']].map(([t, d], i) => {
          const idx = { upload: 0, reading: 1, review: 2 }[stage]
          return (
            <li key={t} className="row" aria-current={idx === i ? 'step' : undefined} style={{ flex: 1, minWidth: 200, opacity: idx >= i ? 1 : 0.55 }}>
              <span className="chip" style={{ width: 30, height: 30, justifyContent: 'center', padding: 0, background: idx > i ? 'var(--green)' : idx === i ? 'var(--forest)' : '#e8e6df', color: idx >= i ? '#fff' : 'var(--ink-2)' }}>{idx > i ? <CheckCircle2 size={16} /> : i + 1}</span>
              <span><b className="small">{t}</b><div className="tiny muted">{d}</div></span>
            </li>
          )
        })}
      </ol>

      <div className="grid g-12">
        {stage !== 'review' && (
          <Card className="span-7" title="Step 1: upload your electricity bill">
            <div onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)} onDrop={onDrop}
              className="state" style={{ border: `2px dashed ${drag ? 'var(--leaf)' : 'var(--line)'}`, borderRadius: 14, background: drag ? 'var(--mint-2)' : '#fcfbf8', minHeight: 220 }}>
              {stage === 'reading' ? <Loader2 className="spin" /> : <UploadCloud />}
              <b>{stage === 'reading' ? 'Reading your bill…' : 'Drag and drop your bill here'}</b>
              {stage === 'upload' && (
                <>
                  <button className="btn primary" onClick={() => input.current?.click()}>Choose a photo or PDF</button>
                  <input ref={input} type="file" accept={MIME.join(',')} capture="environment" hidden onChange={(e) => choose(e.target.files?.[0])} aria-label="Bill file" />
                  <button className="btn link" onClick={manual}><PencilLine /> No bill handy? Type your units instead</button>
                </>
              )}
              {err && <span className="err" role="alert">{err}</span>}
            </div>
          </Card>
        )}
        {stage !== 'review' && (
          <Card className="span-5" title="Step 2: reading your bill">
            <ul className="stack" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
              {['Reading the bill', 'Extracting monthly usage (kWh)', 'Checking each reading is plausible', 'Masking your consumer number'].map((s) => (
                <li key={s} className="row small">{stage === 'reading' ? <Loader2 size={16} className="spin" color="var(--leaf)" /> : <CircleDashed size={16} color="var(--ink-3)" />}{s}</li>
              ))}
            </ul>
            {file && preview && <img src={preview} alt="Your bill" style={{ marginTop: 14, maxWidth: '100%', maxHeight: 220, borderRadius: 10, border: '1px solid var(--line)' }} />}
            <p className="tiny muted" style={{ marginTop: 14 }}><ShieldCheck size={13} /> Your bill is only stored if you create a home from it, and only for scoring it (DPDP Act purpose limit).</p>
          </Card>
        )}
        {stage === 'review' && parsed && <Review parsed={parsed} file={file} ocrDown={ocrDown} onRestart={() => { setStage('upload'); setParsed(null); setOcrDown(false) }} />}
        <TelegramCard />
      </div>
    </>
  )
}

function Review({ parsed, file, ocrDown, onRestart }: { parsed: BillParse; file: File | null; ocrDown: boolean; onRestart: () => void }) {
  const cities = useCities()
  const create = useCreateHome()
  const setActive = useSession((s) => s.setActiveHome)
  const nav = useNavigate()
  const toast = useToast()
  const [months, setMonths] = useState<string[]>(parsed.monthly_kwh.map((v) => (v == null ? '' : String(Math.round(v)))))
  const read = parsed.monthly_kwh.map((v) => v != null)
  const [city, setCity] = useState(parsed.city && cities.data?.some((c) => c.city === parsed.city) ? parsed.city : '')
  const [load, setLoad] = useState(parsed.sanctioned_load_kw ?? 3)
  const [d, setD] = useState({ dwelling_type: 'apartment', floor_position: 'middle', tenure: 'owner', carpet_area_m2: '', occupants: 4, n_ac: 1, ac_star: 3, cooking: 'lpg', roof_access: false })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const vals = months.map((m) => (m.trim() === '' ? null : Number(m)))
  const bad = vals.map((v) => v != null && (Number.isNaN(v) || v < 0 || v > 5000))
  const filled = vals.filter((v) => v != null).length

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const errs: Record<string, string> = {}
    if (!city) errs.city = 'Pick the city the home is in.'
    if (bad.some(Boolean)) errs.months = 'Each month must be between 0 and 5,000 kWh.'
    const area = d.carpet_area_m2 ? Number(d.carpet_area_m2) : null
    if (area != null && !(area > 10 && area < 2000)) errs.area = 'Carpet area should be between 10 and 2,000 m².'
    setErrors(errs)
    if (Object.keys(errs).length) return
    const body: HomeCreate = {
      city, monthly_kwh: filled ? vals : null, sanctioned_load_kw: load, data_source: file && !ocrDown ? 'bill_ocr' : 'survey',
      dwelling_type: d.dwelling_type as HomeCreate['dwelling_type'], floor_position: d.floor_position as HomeCreate['floor_position'],
      tenure: d.tenure as HomeCreate['tenure'], carpet_area_m2: area, occupants: d.occupants, n_ac: d.n_ac, ac_star: d.ac_star,
      cooking: d.cooking as HomeCreate['cooking'], roof_access: d.roof_access,
    }
    try {
      const r = await create.mutateAsync(body)
      setActive(r.home.home_id)
      if (file && !ocrDown) Api.parseBill(file, r.home.home_id).catch(() => toast({ kind: 'warn', title: 'Bill not saved', body: 'Your score is fine; the bill image could not be stored.' }))
      toast({ kind: 'ok', title: `Your score is ${r.score.score}/100`, body: `${r.score.band} · ${r.score.confidence} confidence` })
      nav('/')
    } catch (e) {
      if (e instanceof ApiError && e.code === 'validation_error') {
        const m: Record<string, string> = {}
        for (const x of (e.details.errors as { loc: (string | number)[]; msg: string }[]) ?? []) m[String(x.loc.at(-1))] = x.msg
        setErrors({ ...m, form: 'Some details need fixing.' })
      } else setErrors({ form: describeError(e) })
    }
  }
  const set = (k: keyof typeof d, v: unknown) => setD((x) => ({ ...x, [k]: v }))

  return (
    <form className="span-7 stack" style={{ gap: 18 }} onSubmit={submit} noValidate>
      <Card title="Step 3: review your monthly usage (kWh)" actions={<button type="button" className="btn link" onClick={onRestart}>Use a different bill</button>}>
        {ocrDown ? (
          <div className="alert" style={{ marginBottom: 12 }}><AlertTriangle /><span className="small">Bill reading is unavailable right now. Type the units from your last bills; any months you know are enough.</span></div>
        ) : file ? (
          <p className="small muted" style={{ marginBottom: 12 }}>We read {parsed.months_found} of 12 months{parsed.provider ? ` (${parsed.provider})` : ''}. Check them and fill any you know.</p>
        ) : <p className="small muted" style={{ marginBottom: 12 }}>Enter the units (kWh) from your bills. Leave unknown months blank; we never treat a blank as zero.</p>}
        {parsed.warnings.map((w) => <div key={w} className="alert" style={{ marginBottom: 8 }}><AlertTriangle /><span className="small">{w}</span></div>)}
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(104px, 1fr))', gap: 10 }}>
          {MONTHS.map((m, i) => {
            const st = bad[i] ? 'bad' : vals[i] == null ? 'missing' : read[i] && String(Math.round(parsed.monthly_kwh[i]!)) === months[i] ? 'read' : 'typed'
            return (
              <label key={m} className="card" style={{ padding: 10, boxShadow: 'none', borderColor: st === 'bad' ? 'var(--red)' : st === 'missing' ? '#f1d9b4' : undefined, background: st === 'missing' ? 'var(--amber-bg)' : undefined }}>
                <span className="row between small"><b>{m}</b>{st === 'read' ? <CheckCircle2 size={15} color="var(--leaf)" aria-label="Read from bill" /> : st === 'missing' ? <CircleDashed size={15} color="var(--amber)" aria-label="Missing" /> : st === 'bad' ? <AlertTriangle size={15} color="var(--red)" /> : <PencilLine size={15} color="var(--ink-3)" aria-label="Typed" />}</span>
                <span className="row" style={{ gap: 4 }}>
                  <input className="input" style={{ border: 0, padding: '4px 0', fontWeight: 600, fontSize: 17, background: 'transparent' }} inputMode="decimal" value={months[i]} placeholder="––"
                    onChange={(e) => setMonths((s) => s.map((x, j) => (j === i ? e.target.value.replace(/[^\d.]/g, '') : x)))} aria-label={`${m} units in kWh`} aria-invalid={bad[i]} />
                  <span className="tiny muted">kWh</span>
                </span>
              </label>
            )
          })}
        </div>
        <div className="legend" style={{ marginTop: 10 }}><span><CheckCircle2 size={12} color="var(--leaf)" /> Read from bill</span><span><PencilLine size={12} /> Typed by you</span><span><CircleDashed size={12} color="var(--amber)" /> Missing</span></div>
        {errors.months && <p className="err">{errors.months}</p>}
      </Card>
      <Card title="About the home">
        <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 14 }}>
          <label className="field">City *
            <select className="input" value={city} onChange={(e) => setCity(e.target.value)} aria-invalid={!!errors.city} required>
              <option value="">Choose your city</option>{(cities.data ?? []).map((c) => <option key={c.city} value={c.city}>{c.city}, {c.state}</option>)}
            </select>{errors.city && <span className="err">{errors.city}</span>}
          </label>
          <div className="field">Sanctioned load<Stepper label="Sanctioned load in kW" value={load} min={0.5} max={50} step={0.5} format={(v) => `${num(v, 1)} kW`} onChange={setLoad} /></div>
          <label className="field">Home type
            <select className="input" value={d.dwelling_type} onChange={(e) => set('dwelling_type', e.target.value)}><option value="apartment">Apartment</option><option value="independent_house">Independent house</option><option value="row_house">Row house</option></select>
          </label>
          {d.dwelling_type === 'apartment' && (
            <label className="field">Floor
              <select className="input" value={d.floor_position} onChange={(e) => set('floor_position', e.target.value)}><option value="ground">Ground</option><option value="middle">Middle</option><option value="top">Top floor</option></select>
            </label>
          )}
          <label className="field">You
            <select className="input" value={d.tenure} onChange={(e) => set('tenure', e.target.value)}><option value="owner">Own the home</option><option value="tenant">Rent the home</option></select>
          </label>
          <label className="field">Carpet area (m²)
            <input className="input" inputMode="numeric" value={d.carpet_area_m2} onChange={(e) => set('carpet_area_m2', e.target.value.replace(/[^\d.]/g, ''))} placeholder="e.g. 90" aria-invalid={!!errors.area} />{errors.area && <span className="err">{errors.area}</span>}
          </label>
          <div className="field">People living here<Stepper label="Occupants" value={d.occupants} min={1} max={15} onChange={(v) => set('occupants', v)} /></div>
          <div className="field">Air conditioners<Stepper label="Number of ACs" value={d.n_ac} min={0} max={10} onChange={(v) => set('n_ac', v)} /></div>
          {d.n_ac > 0 && (
            <label className="field">AC star rating
              <select className="input" value={d.ac_star} onChange={(e) => set('ac_star', Number(e.target.value))}>{[1, 2, 3, 4, 5].map((s) => <option key={s} value={s}>{s} star</option>)}</select>
            </label>
          )}
          <label className="field">Cooking
            <select className="input" value={d.cooking} onChange={(e) => set('cooking', e.target.value)}><option value="lpg">LPG cylinder</option><option value="png">Piped gas (PNG)</option><option value="induction">Induction</option></select>
          </label>
          <label className="row small" style={{ gap: 8, marginTop: 20 }}><input type="checkbox" checked={d.roof_access} onChange={(e) => set('roof_access', e.target.checked)} />We have our own usable roof</label>
        </div>
      </Card>
      {errors.form && <div className="alert red" role="alert"><AlertTriangle /><span className="small">{errors.form}</span></div>}
      <div className="row wrap" style={{ justifyContent: 'space-between' }}>
        <span className="tiny muted"><ShieldCheck size={13} /> Used only to calculate your efficiency score.</span>
        <button className="btn primary" disabled={create.isPending}>{create.isPending ? 'Scoring…' : 'Generate my efficiency score'}</button>
      </div>
    </form>
  )
}

function TelegramCard() {
  const id = useSession((s) => s.activeHomeId)
  const cfg = useConfig()
  const toast = useToast()
  const [busy, setBusy] = useState(false)
  const bot = cfg.data?.telegram_bot_username
  const go = async () => {
    if (!id) return
    setBusy(true)
    try {
      const r = await Api.telegramLink(id)
      if (r.deep_link) window.open(r.deep_link, '_blank', 'noopener')
      else toast({ kind: 'warn', title: 'Telegram is not set up on this server', body: 'Ask your admin to set TELEGRAM_BOT_USERNAME.' })
    } catch (e) {
      toast({ kind: 'error', title: 'Could not create the Telegram link', body: describeError(e) })
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card className="span-5" title="Prefer Telegram?" icon={<Send />}>
      <ol className="stack small" style={{ paddingLeft: 18, margin: 0 }}>
        <li>Send a photo of your bill to {bot ? <b>@{bot}</b> : 'the Green Ghar bot'}.</li>
        <li>Reply with your city if the bill doesn't say.</li>
        <li>Get your score card, then ask questions by text or voice note, in Hindi or English.</li>
      </ol>
      <div className="sep" />
      <p className="small muted">{id ? `Continue with home ${id} on your phone: the link is signed and expires in 15 minutes.` : 'Create a home first to continue it on Telegram.'}</p>
      <button className="btn ghost" style={{ marginTop: 10 }} onClick={go} disabled={!id || busy || !bot} title={!bot ? 'The Telegram bot is not configured on this server' : undefined}>
        <Send /> {bot ? 'Continue on Telegram' : 'Telegram not configured'}
      </button>
    </Card>
  )
}
