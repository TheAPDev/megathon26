import { AlertTriangle, CheckCircle2, Inbox, Info, Loader2, Lock, RefreshCw, X, XCircle } from 'lucide-react'
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { ApiError, describeError } from '../api/client'
import { BAND_COLOR } from '../lib/format'

export function Card({ title, icon, actions, children, className = '', serif = false, id }: {
  title?: ReactNode; icon?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string; serif?: boolean; id?: string
}) {
  return (
    <section className={`card ${className}`} aria-labelledby={id ? `${id}-t` : undefined} id={id}>
      {(title || actions) && (
        <div className="card-h">
          {title && <h2 className={`card-t${serif ? ' serif' : ''}`} id={id ? `${id}-t` : undefined}>{icon}{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  )
}

export const Skeleton = ({ h = 16, w = '100%', r }: { h?: number; w?: number | string; r?: number }) => (
  <div className="skeleton" style={{ height: h, width: w, borderRadius: r }} aria-hidden />
)

export function Loading({ lines = 3, label = 'Loading' }: { lines?: number; label?: string }) {
  return (
    <div className="stack" role="status" aria-label={label}>
      {Array.from({ length: lines }, (_, i) => <Skeleton key={i} h={i === 0 ? 28 : 14} w={`${90 - i * 12}%`} />)}
    </div>
  )
}

export function ErrorState({ error, onRetry, compact }: { error: unknown; onRetry?: () => void; compact?: boolean }) {
  const e = error instanceof ApiError ? error : null
  if (e?.status === 403)
    return (
      <div className="state" role="alert"><Lock /><b>You don't have access to this.</b>
        <span className="small">{e.code === 'forbidden' ? e.message : 'Sign in with an account that can see it.'}</span></div>
    )
  return (
    <div className={`state${compact ? ' small' : ''}`} role="alert">
      <XCircle />
      <span>{describeError(error)}</span>
      {onRetry && e?.status !== 404 && e?.status !== 422 && (
        <button className="btn ghost" onClick={onRetry}><RefreshCw /> Try again</button>
      )}
      {e?.requestId && <span className="rid">Reference {e.requestId}</span>}
    </div>
  )
}

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="state">
      {icon ?? <Inbox />}
      <b>{title}</b>
      {children}
    </div>
  )
}

/** Generic query renderer: loading -> error -> data. */
export function Q<T>({ q, children, lines, empty }: {
  q: { data: T | undefined; isLoading: boolean; error: unknown; refetch: () => unknown; isFetching?: boolean }
  children: (d: T) => ReactNode; lines?: number; empty?: (d: T) => ReactNode | null
}) {
  if (q.isLoading) return <Loading lines={lines} />
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  if (q.data === undefined) return null
  const e = empty?.(q.data)
  return <>{e ?? children(q.data)}</>
}

export function BandChip({ band }: { band: string }) {
  return (
    <span className="chip" style={{ background: `color-mix(in srgb, ${BAND_COLOR[band] ?? 'var(--leaf)'} 14%, white)`, color: BAND_COLOR[band] }}>
      {band}
    </span>
  )
}

export function ScorePill({ score }: { score: number }) {
  const c = score >= 80 ? 'var(--band-1)' : score >= 65 ? 'var(--band-2)' : score >= 50 ? 'var(--band-3)' : score >= 30 ? 'var(--band-4)' : 'var(--band-5)'
  return <span className="score-pill" style={{ background: `color-mix(in srgb, ${c} 16%, white)`, color: `color-mix(in srgb, ${c} 80%, black)` }}>{score}</span>
}

export function Estimated({ show, children }: { show?: boolean; children: ReactNode }) {
  if (!show) return <>{children}</>
  return <span title="Estimated from your home's data and city climate" style={{ borderBottom: '1px dotted var(--ink-3)' }}>{children}</span>
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return <button type="button" role="switch" aria-checked={checked} aria-label={label} className="toggle" onClick={() => onChange(!checked)} />
}

export function Stepper({ value, onChange, step = 1, min = 0, max = 1e12, format = String, label }: {
  value: number; onChange: (v: number) => void; step?: number; min?: number; max?: number; format?: (v: number) => string; label: string
}) {
  const clamp = (v: number) => Math.min(max, Math.max(min, Math.round(v / step) * step))
  const [text, setText] = useState(format(value))
  useEffect(() => setText(format(value)), [value, format])
  return (
    <div className="stepper" role="group" aria-label={label}>
      <button type="button" aria-label={`Decrease ${label}`} onClick={() => onChange(clamp(value - step))} disabled={value <= min}>−</button>
      <input aria-label={label} value={text} inputMode="decimal" onChange={(e) => setText(e.target.value)}
        onBlur={() => { const n = Number(text.replace(/[^\d.]/g, '')); if (!Number.isNaN(n)) onChange(clamp(n)); else setText(format(value)) }}
        onKeyDown={(e) => e.key === 'Enter' && (e.target as HTMLInputElement).blur()} />
      <button type="button" aria-label={`Increase ${label}`} onClick={() => onChange(clamp(value + step))} disabled={value >= max}>+</button>
    </div>
  )
}

export function Tabs<K extends string>({ tabs, value, onChange, label }: { tabs: { key: K; label: ReactNode }[]; value: K; onChange: (k: K) => void; label: string }) {
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={value === t.key} onClick={() => onChange(t.key)}>{t.label}</button>
      ))}
    </div>
  )
}

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const k = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', k)
    ref.current?.focus()
    return () => window.removeEventListener('keydown', k)
  }, [open, onClose])
  if (!open) return null
  return (
    <>
      <div className="drawer-back" onClick={onClose} />
      <div className="drawer" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <div className="row between"><h2 className="card-t serif">{title}</h2><button className="icon-btn" onClick={onClose} aria-label="Close"><X size={18} /></button></div>
        {children}
      </div>
    </>
  )
}

/* ---- toasts ------------------------------------------------------------------------------------ */
type Toast = { id: number; kind: 'ok' | 'warn' | 'error' | 'info'; title: string; body?: string }
const ToastCtx = createContext<(t: Omit<Toast, 'id'>) => void>(() => {})
export const useToast = () => useContext(ToastCtx)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((t: Omit<Toast, 'id'>) => {
    const id = Date.now() + Math.random()
    setItems((s) => [...s.slice(-3), { ...t, id }])
    setTimeout(() => setItems((s) => s.filter((x) => x.id !== id)), t.kind === 'error' ? 8000 : 5000)
  }, [])
  const Icon = { ok: CheckCircle2, warn: AlertTriangle, error: XCircle, info: Info }
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {items.map((t) => {
          const I = Icon[t.kind]
          return (
            <div key={t.id} className={`toast ${t.kind}`} role={t.kind === 'error' ? 'alert' : 'status'}>
              <I />
              <div style={{ flex: 1 }}><b>{t.title}</b>{t.body && <div className="small muted">{t.body}</div>}</div>
              <button className="btn link" aria-label="Dismiss" onClick={() => setItems((s) => s.filter((x) => x.id !== t.id))}><X size={16} /></button>
            </div>
          )
        })}
      </div>
    </ToastCtx.Provider>
  )
}

export const Spinner = () => <Loader2 className="spin" size={16} style={{ animation: 'spin 1s linear infinite' }} aria-hidden />

/** Debounced value: the studio and calculators wait for the user to stop sliding before calling the engine. */
export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

/** Countdown for 429 responses. */
export function useCooldown() {
  const [left, setLeft] = useState(0)
  useEffect(() => {
    if (left <= 0) return
    const t = setTimeout(() => setLeft((x) => x - 1), 1000)
    return () => clearTimeout(t)
  }, [left])
  return [left, setLeft] as const
}
