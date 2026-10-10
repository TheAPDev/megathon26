import { Building2, ChevronDown, FileScan, Home, Landmark, LogOut, Menu, MessagesSquare, SlidersHorizontal, Sun, Wallet } from 'lucide-react'
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
      <circle cx="32" cy="32" r="30" fill="#e8dcc4" />
      <path d="M14 34 32 18l18 16v14a2 2 0 0 1-2 2H16a2 2 0 0 1-2-2z" fill="#123526" />
      <path d="M32 47c0-8 4-13 11-14-1 8-5 13-11 14z" fill="#7fbf8f" />
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
  ]
  return (
    <div className="shell">
      <aside className={`sidebar${open ? ' open' : ''}`} aria-label="Main navigation">
        <NavLink to="/" className="brand">
          <BrandMark />
          <div><div className="brand-name">Green Ghar</div><div className="brand-tag">Greener homes, brighter tomorrows</div></div>
        </NavLink>
        <nav className="nav">
          {nav.map((n) => <NavLink key={n.to} to={n.to} end={n.end}>{n.icon}{n.label}</NavLink>)}
          {canLend && (
            <>
              <div className="nav-sep" />
              <div className="nav-label">{t('forLenders')}</div>
              <NavLink to="/portfolio"><Landmark />{t('portfolio')}</NavLink>
            </>
          )}
        </nav>
        <div className="sidebar-foot">
          <div className="sidebar-promo">
            <p>Smaller footprints, brighter tomorrows.</p>
            <small>Scores and savings come from your own bills and your city's climate.</small>
          </div>
          {authMode === 'supabase' && user && (
            <button className="btn ghost" style={{ background: 'transparent', color: '#d7e2da', borderColor: 'rgba(255,255,255,.2)' }} onClick={() => signOut()}>
              <LogOut /> {t('signOut')}
            </button>
          )}
          <span>Green Ghar v1.0{authMode === 'demo' ? ' · demo mode' : ''}</span>
        </div>
      </aside>
      {open && <div className="drawer-back" style={{ zIndex: 45 }} onClick={() => setOpen(false)} />}
      <div className="main">
        <Topbar onMenu={() => setOpen(true)} />
        <main className="page" id="main"><Outlet /></main>
      </div>
    </div>
  )
}

function Topbar({ onMenu }: { onMenu: () => void }) {
  const lang = useSession((s) => s.language)
  const setLang = useSession((s) => s.setLanguage)
  const homeId = useSession((s) => s.activeHomeId)
  const home = useHome(homeId)
  const [picker, setPicker] = useState(false)
  const t = useT()
  return (
    <header className="topbar">
      <button className="icon-btn menu-btn" onClick={onMenu} aria-label="Open menu"><Menu size={18} /></button>
      <div className="grow" />
      <button className="home-switch" onClick={() => setPicker(true)} aria-haspopup="dialog" aria-label={t('switchHome')}>
        <span className="ico"><Building2 size={18} /></span>
        <span style={{ flex: 1 }}>
          <b>{homeId ? (home.data ? `${humanize(home.data.dwelling_type)}` : homeId) : t('addHome')}</b>
          <small>{home.data ? `${home.data.city} · ${homeId}` : homeId ? 'Loading…' : 'No home selected'}</small>
        </span>
        <ChevronDown size={16} />
      </button>
      <div className="lang" role="group" aria-label="Language">
        <button aria-pressed={lang === 'en'} onClick={() => setLang('en')}>EN</button>
        <button aria-pressed={lang === 'hi'} onClick={() => setLang('hi')} lang="hi">हि</button>
      </div>
      <HomePicker open={picker} onClose={() => setPicker(false)} />
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
