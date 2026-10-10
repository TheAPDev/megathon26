// Indian number formatting: 1,23,456 grouping, ₹, lakh/crore abbreviations.
const nf = (d = 0) => new Intl.NumberFormat('en-IN', { maximumFractionDigits: d, minimumFractionDigits: 0 })

export const num = (v: number | null | undefined, d = 0) => (v == null || Number.isNaN(v) ? '–' : nf(d).format(v))
export const inr = (v: number | null | undefined) => (v == null || Number.isNaN(v) ? '–' : `₹${nf(0).format(Math.round(v))}`)

/** ₹1.96L, ₹1,842 Cr: compact Indian units for tiles. */
export function inrShort(v: number | null | undefined): string {
  if (v == null || Number.isNaN(v)) return '–'
  const a = Math.abs(v)
  const sign = v < 0 ? '−' : ''
  if (a >= 1e7) return `${sign}₹${nf(2).format(a / 1e7)} Cr`
  if (a >= 1e5) return `${sign}₹${nf(2).format(a / 1e5)}L`
  return `${sign}₹${nf(0).format(Math.round(a))}`
}

export const inrRange = (r: [number, number] | null | undefined) =>
  !r ? '–' : Math.round(r[0]) === Math.round(r[1]) ? inr(r[0]) : `${inr(r[0])} – ${inr(r[1])}`
export const kwh = (v: number | null | undefined) => `${num(v)} kWh`
export const kg = (v: number | null | undefined) => `${num(v)} kg`
export const pct = (v: number | null | undefined, d = 0) => (v == null ? '–' : `${nf(d).format(v)}%`)
export const signed = (v: number, d = 0) => `${v > 0 ? '+' : v < 0 ? '−' : ''}${nf(d).format(Math.abs(v))}`
export const years = (v: number | null | undefined) => (v == null ? 'n/a' : `${nf(1).format(v)} yrs`)

export const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export const humanize = (s: string) => s.replace(/_/g, ' ').replace(/^\w/, (c) => c.toUpperCase())

export const BAND_COLOR: Record<string, string> = {
  'Highly efficient': 'var(--band-1)',
  Good: 'var(--band-2)',
  Moderate: 'var(--band-3)',
  Poor: 'var(--band-4)',
  'Very poor': 'var(--band-5)',
}
export const bandOf = (score: number) =>
  score >= 80 ? 'Highly efficient' : score >= 65 ? 'Good' : score >= 50 ? 'Moderate' : score >= 30 ? 'Poor' : 'Very poor'

export const COMPONENT_LABEL: Record<string, string> = {
  energy_efficiency: 'Energy efficiency',
  consumption_intensity: 'Consumption intensity',
  envelope: 'Insulation & envelope',
  cooling_system: 'Cooling system',
  windows_shading: 'Windows & shading',
  renewables: 'Renewables',
  smart_use: 'Smart use',
}
