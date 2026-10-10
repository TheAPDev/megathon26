// Mirror of greenghar/llm/verifier.py `extract`: the same tokens the backend counted are the ones we highlight.
// A token is "unverified" when the backend listed it in grounding.unsupported; every other counted token was matched.

const NUM = /(?<![\w.])[-−]?\d[\d,]*(?:\.\d+)?(?:\s*(?:lakh|lakhs|crore|cr|k)\b)?(?:\s*%)?/gi
const DEVANAGARI = '०१२३४५६७८९'

export const normaliseDigits = (s: string) => s.replace(/[०-९]/g, (d) => String(DEVANAGARI.indexOf(d)))

function parse(tok: string): { v: number; step: number } | null {
  let t = tok.trim().toLowerCase().replace('−', '-').replace(/%$/, '').trim()
  let mult = 1
  for (const [w, m] of [['lakhs', 1e5], ['lakh', 1e5], ['crore', 1e7], ['cr', 1e7], ['k', 1e3]] as const) {
    if (t.endsWith(w)) {
      mult = m
      t = t.slice(0, -w.length).trim()
      break
    }
  }
  t = t.replace(/,/g, '')
  const v = Number(t)
  if (t === '' || Number.isNaN(v)) return null
  const decimals = t.includes('.') ? t.split('.')[1].length : 0
  return { v: v * mult, step: 10 ** -decimals * mult }
}

export interface Figure { start: number; end: number; token: string; counted: boolean }

/** Every number-like token with its position; `counted` matches the verifier's exemptions (small counts, years). */
export function figures(text: string): Figure[] {
  const norm = normaliseDigits(text) // same length: one Devanagari digit -> one ASCII digit
  const out: Figure[] = []
  for (const m of norm.matchAll(NUM)) {
    const tok = m[0]
    const p = parse(tok)
    if (!p) continue
    const pct = tok.trimEnd().endsWith('%')
    const multFree = !/lakh|crore|cr|k/i.test(tok)
    const isInt = Number.isInteger(p.v)
    const exempt = (isInt && p.v >= 0 && p.v <= 12 && p.step >= 1 && multFree && !pct) || (isInt && p.v >= 1990 && p.v <= 2060 && !pct)
    out.push({ start: m.index!, end: m.index! + tok.length, token: tok.trim(), counted: !exempt })
  }
  return out
}

export type Segment = { text: string; status?: 'verified' | 'unverified' }

/** Split an answer into plain text and highlighted figures. */
export function segments(text: string, unsupported: string[]): Segment[] {
  const bad = new Set(unsupported.map((u) => normaliseDigits(u).trim()))
  const segs: Segment[] = []
  let i = 0
  for (const f of figures(text)) {
    if (!f.counted) continue
    if (f.start > i) segs.push({ text: text.slice(i, f.start) })
    segs.push({ text: text.slice(f.start, f.end), status: bad.has(f.token) ? 'unverified' : 'verified' })
    i = f.end
  }
  if (i < text.length) segs.push({ text: text.slice(i) })
  return segs
}
