import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'

export type Lang = 'en' | 'hi'
export type Role = 'customer' | 'analyst'

export interface SessionUser {
  sub: string
  role: Role
  email?: string | null
  phone?: string | null
}

interface SessionState {
  user: SessionUser | null
  authMode: 'supabase' | 'demo' | 'pending'
  activeHomeId: string | null
  recentHomes: string[]
  language: Lang
  setUser: (u: SessionUser | null) => void
  setAuthMode: (m: SessionState['authMode']) => void
  setActiveHome: (id: string | null) => void
  forgetHome: (id: string) => void
  setLanguage: (l: Lang) => void
}

// localStorage can throw (private mode, blocked storage): fall back to memory silently.
const safeStorage = createJSONStorage(() => {
  try {
    const k = '__gg_probe'
    localStorage.setItem(k, '1')
    localStorage.removeItem(k)
    return localStorage
  } catch {
    const m = new Map<string, string>()
    return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => void m.set(k, v), removeItem: (k) => void m.delete(k) }
  }
})

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      user: null,
      authMode: 'pending',
      activeHomeId: null,
      recentHomes: [],
      language: 'en',
      setUser: (user) => set({ user }),
      setAuthMode: (authMode) => set({ authMode }),
      setActiveHome: (id) =>
        set((s) => ({ activeHomeId: id, recentHomes: id ? [id, ...s.recentHomes.filter((x) => x !== id)].slice(0, 6) : s.recentHomes })),
      forgetHome: (id) =>
        set((s) => {
          const recent = s.recentHomes.filter((x) => x !== id)
          return { recentHomes: recent, activeHomeId: s.activeHomeId === id ? (recent[0] ?? null) : s.activeHomeId }
        }),
      setLanguage: (language) => set({ language }),
    }),
    { name: 'gg-session', storage: safeStorage, partialize: (s) => ({ activeHomeId: s.activeHomeId, recentHomes: s.recentHomes, language: s.language }) },
  ),
)
