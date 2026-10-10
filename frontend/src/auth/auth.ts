// Username + password sign-in (Supabase Auth) when the backend publishes its project URL + anon key (/config), otherwise demo mode
// (GG_ENV=dev backends accept anonymous calls). The anon key is public by design; no secret lives here.
import type { SupabaseClient } from '@supabase/supabase-js'
import { setTokenProvider } from '../api/client'
import { Api } from '../api/endpoints'
import type { PublicConfig } from '../api/types'
import { useSession, type SessionUser } from '../state/session'

let sb: SupabaseClient | null = null

function userFromToken(token: string | undefined | null): SessionUser | null {
  if (!token) return null
  try {
    const p = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')))
    return { sub: p.sub, role: p.app_metadata?.app_role === 'analyst' ? 'analyst' : 'customer', email: p.email ?? null, phone: p.phone ?? null }
  } catch {
    return null
  }
}

export async function initAuth(cfg: PublicConfig): Promise<void> {
  const { supabase_url, supabase_anon_key } = cfg.auth
  if (cfg.auth.username_domain) usernameDomain = cfg.auth.username_domain
  const s = useSession.getState()
  if (!supabase_url || !supabase_anon_key) {
    s.setAuthMode('demo')
    s.setUser(null)
    if (!s.activeHomeId && cfg.demo_home_id) s.setActiveHome(cfg.demo_home_id)
    return
  }
  const { createClient } = await import('@supabase/supabase-js') // only loaded when auth is configured
  sb = createClient(supabase_url, supabase_anon_key, { auth: { persistSession: true, autoRefreshToken: true } })
  const { data } = await sb.auth.getSession()
  s.setAuthMode('supabase')
  s.setUser(userFromToken(data.session?.access_token))
  sb.auth.onAuthStateChange((_e, session) => useSession.getState().setUser(userFromToken(session?.access_token)))
  setTokenProvider({
    get: async () => (await sb!.auth.getSession()).data.session?.access_token ?? null,
    refresh: async () => (await sb!.auth.refreshSession()).data.session?.access_token ?? null,
    onUnauthorized: () => {
      void sb!.auth.signOut()
      useSession.getState().setUser(null)
    },
  })
}

// Usernames map to a private, never-mailed address; the server publishes the domain in /config.
let usernameDomain = 'gg-users.example.com'

export const USERNAME_RE = /^[a-z0-9][a-z0-9_.]{2,29}$/

export function normalizeUsername(raw: string): string {
  const u = raw.trim().toLowerCase()
  if (!USERNAME_RE.test(u) || u.includes('..') || u.endsWith('.'))
    throw new Error('Username must be 3-30 characters: letters, numbers, dot or underscore.')
  return u
}

export function checkPassword(pw: string, username: string): void {
  if (pw.length < 8 || pw.length > 72) throw new Error('Password must be 8 to 72 characters.')
  if (pw.toLowerCase() === username || /^\d+$/.test(pw) || /^[A-Za-z]+$/.test(pw))
    throw new Error('Use a mix of letters and numbers, and not your username.')
}

export async function signInWithPassword(username: string, password: string) {
  if (!sb) throw new Error('Sign-in is not configured on this server.')
  const u = normalizeUsername(username)
  const { error } = await sb.auth.signInWithPassword({ email: `${u}@${usernameDomain}`, password })
  if (error) throw new Error(/invalid login/i.test(error.message) ? 'Wrong username or password.' : error.message)
}

export async function signUpWithPassword(username: string, password: string) {
  const u = normalizeUsername(username)
  checkPassword(password, u)
  await Api.signup(u, password) // server creates the confirmed account (service key stays server-side)
  await signInWithPassword(u, password)
}

export async function signOut() {
  if (sb) await sb.auth.signOut()
  const s = useSession.getState()
  s.setUser(null)
  s.setActiveHome(null)
}
