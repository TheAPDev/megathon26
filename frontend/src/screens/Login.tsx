// Username + password sign-in and account creation (Supabase Auth). Only shown when the server has auth configured.
import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { describeError } from '../api/client'
import { checkPassword, normalizeUsername, signInWithPassword, signUpWithPassword } from '../auth/auth'
import { BrandMark } from '../components/Layout'
import { useSession } from '../state/session'

export default function Login() {
  const mode = useSession((s) => s.authMode)
  const user = useSession((s) => s.user)
  const [sp] = useSearchParams()
  const next = sp.get('next') || '/'
  const nav = useNavigate()
  const [tab, setTab] = useState<'in' | 'up'>('in')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  if (mode !== 'supabase' || user) return <Navigate to={next} replace />

  const switchTab = (t: 'in' | 'up') => { setTab(t); setErr(null); setPassword(''); setConfirm('') }

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setErr(null)
    setBusy(true)
    try {
      if (tab === 'up') {
        const u = normalizeUsername(username)
        checkPassword(password, u)
        if (password !== confirm) throw new Error('The two passwords do not match.')
        await signUpWithPassword(u, password)
      } else {
        await signInWithPassword(username, password)
      }
      nav(next, { replace: true })
    } catch (x) {
      setErr(x instanceof Error && !('status' in x) ? x.message : describeError(x))
    } finally {
      setBusy(false)
    }
  }
  const up = tab === 'up'
  return (
    <div style={{ minHeight: '100%', display: 'grid', placeItems: 'center', background: 'radial-gradient(900px 600px at 55% 35%, #1f6b6f, #0b2a33 60%, #07141a)', padding: 16 }}>
      <form className="card stack" style={{ width: 'min(420px, 100%)', gap: 14 }} onSubmit={submit}>
        <div className="row"><BrandMark /><div><b style={{ font: '500 24px var(--serif)' }}>Green Ghar</b><div className="small muted">{up ? 'Create your account' : 'Sign in to see your home'}</div></div></div>
        <div className="row" role="tablist" aria-label="Account">
          <button type="button" role="tab" aria-selected={!up} className={`btn ${!up ? 'primary' : 'ghost'}`} onClick={() => switchTab('in')}>Sign in</button>
          <button type="button" role="tab" aria-selected={up} className={`btn ${up ? 'primary' : 'ghost'}`} onClick={() => switchTab('up')}>Sign up</button>
        </div>
        <label className="field">Username
          <input className="input" autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} onChange={(e) => setUsername(e.target.value)} required />
        </label>
        <label className="field">Password
          <input className="input" type="password" autoComplete={up ? 'new-password' : 'current-password'} value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        {up && (
          <label className="field">Confirm password
            <input className="input" type="password" autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} required />
          </label>
        )}
        {up && <span className="small muted">3-30 letters, numbers, dot or underscore. Password: 8+ characters with letters and numbers.</span>}
        {err && <span className="err" role="alert">{err}</span>}
        <button className="btn primary" disabled={busy}>{busy ? 'Please wait…' : up ? 'Create account' : 'Sign in'}</button>
      </form>
    </div>
  )
}
