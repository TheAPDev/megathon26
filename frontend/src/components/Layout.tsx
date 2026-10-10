import { Building2, ChevronDown, CloudSun, FileScan, Grip, Home, Landmark, LogOut, MapPin, Menu, MessagesSquare, Settings, SlidersHorizontal, Sun, Wallet } from 'lucide-react'
import { useEffect, useState, type ReactNode } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useConfig, useHome, useMyHomes } from '../api/hooks'
import { signOut } from '../auth/auth'
import { useT } from '../lib/i18n'
import { humanize } from '../lib/format'
import { useSession } from '../state/session'
import { Drawer } from './ui'

export function BrandMark({ size = 40 }: { size?: number }) {
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <path d="M8 34 32 12l24 22h-8v18a2 2 0 0 1-2 2H18a2 2 0 0 1-2-2V34z" fill="#eaf4f4" />
      <path d="M32 50c0-9 5-15 13-16-1 9-6 15-13 16z" fill="#3fd0dc" />
    </svg>
  )
}

export function Layout() {
  const t = useT()
  const [open, setOpen] = useState(false)
  const loc = useLocation()
  const user = useSession((s) => s.user)
  const authMode = useSession((s) => s.authMode)
  const canLend = authMode === 'demo' || user?.role === 'analyst'
  useEffect(() => setOpen(false), [loc.pathname])

  const nav: { to: string; label: string; icon: ReactNode; end?: boolean }[] = [
    { to: '/', label: t('dashboard'), icon: <Home />, end: true },
    { to: '/bill', label: t('billToScore'), icon: <FileScan /> },
    { to: '/studio', label: t('studio'), icon: <SlidersHorizontal /> },
    { to: '/paisa', label: t('paisa'), icon: <Wallet /> },
    { to: '/saathi', label: t('saathi'), icon: <MessagesSquare /> },
    { to: '/garmi', label: t('garmi'), icon: <Sun /> },
    ...(canLend ? [{ to: '/portfolio', label: t('portfolio'), icon: <Landmark /> }] : []),
  ]
  return (
    <div className="shell">
      <aside className={`rail${open ? ' open' : ''}`} aria-label="Main navigation">
        <span className="rail-btn dots" aria-hidden><Grip size={18} /></span>
        {nav.map((n) => (
          <NavLink key={n.to} to={n.to} end={n.end} aria-label={n.label}>{n.icon}<span className="tip">{n.label}</span></NavLink>
        ))}
        <div className="gap" />
        {authMode === 'supabase' && user && (
          <button className="rail-btn" onClick={() => signOut()} aria-label={t('signOut')}><LogOut /><span className="tip">{t('signOut')}</span></button>
        )}
      </aside>
      {open && <div className="drawer-back" style={{ zIndex: 45 }} onClick={() => setOpen(false)} />}
      <div className="main">
        <Topbar onMenu={() => setOpen(true)} />
        <main className="page" id="main"><Outlet /></main>
      </div>
    </div>
  )
}

const TABS = [
  { to: '/', label: 'Overview', end: true },
  { to: '/studio', label: 'Plan' },
  { to: '/paisa', label: 'Money' },
  { to: '/saathi', label: 'Advisor' },
]

function Topbar({ onMenu }: { onMenu: () => void }) {
  const lang = useSession((s) => s.language)
  const setLang = useSession((s) => s.setLanguage)
  const homeId = useSession((s) => s.activeHomeId)
  const home = useHome(homeId)
  const [picker, setPicker] = useState(false)
  const [settings, setSettings] = useState(false)
  const t = useT()
  const [now, setNow] = useState(() => new Date())
  useEffect(() => { const i = setInterval(() => setNow(new Date()), 30000); return () => clearInterval(i) }, [])
  const clock = now.toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' }).toUpperCase()
  return (
    <header className="topbar">
      <button className="icon-btn menu-btn" onClick={onMenu} aria-label="Open menu"><Menu size={18} /></button>
      <NavLink to="/" className="brand-lockup" aria-label="Green Ghar home"><BrandMark size={26} />Green Ghar</NavLink>
      <nav className="top-tabs" aria-label="Sections">
        {TABS.map((x) => <NavLink key={x.to} to={x.to} end={x.end}>{x.label}</NavLink>)}
      </nav>
      <div className="grow" />
      <span className="pill hide-sm"><CloudSun aria-hidden />{clock}</span>
      <button className="pill" onClick={() => setPicker(true)} aria-haspopup="dialog" aria-label={t('switchHome')}>
        <MapPin aria-hidden />
        <span>{homeId ? (home.data ? home.data.city : homeId) : t('addHome')}</span>
        {home.data && <span className="hide-sm muted">{humanize(home.data.dwelling_type)}</span>}
        <ChevronDown size={14} />
      </button>
      <span className="top-sep hide-sm" aria-hidden />
      <button className="icon-btn" onClick={() => setSettings(true)} aria-label="Settings"><Settings size={18} /></button>
      <HomePicker open={picker} onClose={() => setPicker(false)} />
      <Drawer open={settings} onClose={() => setSettings(false)} title="Settings">
        <div className="stack">
          <b className="small">Language</b>
          <div className="lang" role="group" aria-label="Language" style={{ alignSelf: 'flex-start' }}>
            <button aria-pressed={lang === 'en'} onClick={() => setLang('en')}>English</button>
            <button aria-pressed={lang === 'hi'} onClick={() => setLang('hi')} lang="hi">हिन्दी</button>
          </div>
          <p className="small muted">Your score, plans and the AI Saathi follow this choice.</p>
        </div>
      </Drawer>
    </header>
  )
}

function HomePicker({ open, onClose }: { open: boolean; onClose: () => void }) {
  const authMode = useSession((s) => s.authMode)
  const user = useSession((s) => s.user)
  const recent = useSession((s) => s.recentHomes)
  const active = useSession((s) => s.activeHomeId)
  const setActive = useSession((s) => s.setActiveHome)
  const mine = useMyHomes(!!user)
  const cfg = useConfig()
  const nav = useNavigate()
  const [id, setId] = useState('')
  const pick = (h: string) => {
    setActive(h)
    onClose()
  }
  const ids = Array.from(new Set([...(mine.data ?? []).map((h) => h.home_id), ...recent]))
  return (
    <Drawer open={open} onClose={onClose} title="Your homes">
      {ids.length === 0 && <p className="muted">No homes yet. Scan a bill or answer a few questions to add one.</p>}
      <div className="stack">
        {ids.map((h) => {
          const m = mine.data?.find((x) => x.home_id === h)
          return (
            <button key={h} className="card row" style={{ textAlign: 'left', cursor: 'pointer', borderColor: h === active ? 'var(--leaf)' : undefined }} onClick={() => pick(h)}>
              <Building2 size={18} />
              <span style={{ flex: 1 }}><b>{h}</b>{m && <div className="small muted">{m.city} · {humanize(m.dwelling_type)}</div>}</span>
              {h === active && <span className="chip">Current</span>}
            </button>
          )
        })}
      </div>
      <button className="btn primary" onClick={() => { onClose(); nav('/bill') }}><FileScan /> Add a home from a bill</button>
      {authMode === 'demo' && (
        <form className="card stack" onSubmit={(e) => { e.preventDefault(); if (id.trim()) pick(id.trim().toUpperCase()) }}>
          <b>Open a home by ID</b>
          <span className="small muted">Demo mode: any home in the dataset, e.g. {cfg.data?.demo_home_id ?? 'H000011'}.</span>
          <div className="row"><input className="input" aria-label="Home ID" value={id} onChange={(e) => setId(e.target.value)} placeholder="H000011" /><button className="btn ghost">Open</button></div>
        </form>
      )}
    </Drawer>
  )
}
