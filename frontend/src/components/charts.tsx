// Small hand-built SVG charts (no chart library): each one draws exactly what the engine returned.
import { useId, useState } from 'react'
import { BAND_COLOR, MONTHS, bandOf, num } from '../lib/format'

/** Radial score gauge (0-100). Hatched when the score rests on low-confidence data. */
export function Gauge({ score, size = 168, stroke = 14, color, hatched = false, label }: {
  score: number; size?: number; stroke?: number; color?: string; hatched?: boolean; label?: string
}) {
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const id = useId()
  const col = color ?? BAND_COLOR[bandOf(score)]
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={label ?? `Score ${score} out of 100`}>
      <defs>
        <pattern id={`h${id}`} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="6" height="6" fill={col} /><line x1="0" y1="0" x2="0" y2="6" stroke="#fff" strokeWidth="2.5" />
        </pattern>
      </defs>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#ebe9e2" strokeWidth={stroke} />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={hatched ? `url(#h${id})` : col} strokeWidth={stroke} strokeLinecap="round"
        strokeDasharray={`${(c * Math.max(0, Math.min(100, score))) / 100} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x="50%" y="50%" textAnchor="middle" dominantBaseline="central" style={{ font: `500 ${size * 0.27}px var(--serif)` }} fill="var(--ink)">{score}</text>
      <text x="50%" y={size / 2 + size * 0.2} textAnchor="middle" fontSize={size * 0.075} fill="var(--ink-3)">/ 100</text>
    </svg>
  )
}

/** Horizontal labelled bar, value 0..max. */
export function HBar({ value, max = 100, color = 'var(--green)', height = 9 }: { value: number; max?: number; color?: string; height?: number }) {
  return (
    <div className="bar-track" style={{ height }}>
      <div className="bar-fill" style={{ width: `${Math.max(0, Math.min(100, (value / max) * 100))}%`, background: color }} />
    </div>
  )
}

/** Monthly bars; one or two series. null months are drawn as dashed placeholders, never as zero. */
export function MonthlyBars({ a, b, aLabel = 'Current home', bLabel = 'With this plan', height = 190, unit = 'kWh', width = 640 }: {
  a: (number | null)[]; b?: (number | null)[]; aLabel?: string; bLabel?: string; height?: number; unit?: string; width?: number
}) {
  const W = width, H = height, pl = 40, pb = 22, pt = 8
  const all = [...a, ...(b ?? [])].filter((x): x is number => x != null)
  const max = niceMax(Math.max(1, ...all))
  const slot = (W - pl) / 12
  const bw = b ? slot * 0.3 : slot * 0.5
  const y = (v: number) => pt + (H - pb - pt) * (1 - v / max)
  const [hover, setHover] = useState<number | null>(null)
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`Monthly ${unit}: ${aLabel}${b ? ` vs ${bLabel}` : ''}`}>
        {ticks(max).map((t) => (
          <g key={t}><line x1={pl} x2={W} y1={y(t)} y2={y(t)} stroke="#eeece5" /><text x={pl - 6} y={y(t) + 4} textAnchor="end" fontSize="10.5" fill="var(--ink-3)">{num(t)}</text></g>
        ))}
        {MONTHS.map((m, i) => {
          const x0 = pl + i * slot + (slot - (b ? bw * 2 + 3 : bw)) / 2
          const va = a[i], vb = b?.[i]
          return (
            <g key={m} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={pl + i * slot} y={pt} width={slot} height={H - pb - pt} fill={hover === i ? '#f4f3ee' : 'transparent'} />
              {va != null ? <rect x={x0} y={y(va)} width={bw} height={y(0) - y(va)} rx="3" fill={b ? 'var(--blue)' : 'var(--leaf-2)'} />
                : <rect x={x0} y={y(0) - 24} width={bw} height={24} rx="3" fill="none" stroke="#cfcbbf" strokeDasharray="3 3" />}
              {b && vb != null && <rect x={x0 + bw + 3} y={y(vb)} width={bw} height={y(0) - y(vb)} rx="3" fill="var(--green)" />}
              <text x={pl + i * slot + slot / 2} y={H - 6} textAnchor="middle" fontSize="10.5" fill="var(--ink-3)">{m}</text>
            </g>
          )
        })}
      </svg>
      <div className="row between small">
        <div className="legend">
          <span><i style={{ background: b ? 'var(--blue)' : 'var(--leaf-2)' }} />{aLabel}</span>
          {b && <span><i style={{ background: 'var(--green)' }} />{bLabel}</span>}
          {a.some((v) => v == null) && <span><i style={{ border: '1px dashed #bbb', background: 'none' }} />No reading</span>}
        </div>
        <span className="muted" aria-live="polite">
          {hover != null && `${MONTHS[hover]}: ${a[hover] == null ? 'no reading' : `${num(a[hover])} ${unit}`}${b ? ` → ${b[hover] == null ? '–' : `${num(b[hover])} ${unit}`}` : ''}`}
        </span>
      </div>
    </div>
  )
}

/** Waterfall: baseline, one negative step per retrofit in engine order, then the result. */
export function Waterfall({ start, steps, end, startLabel, endLabel, unit }: {
  start: number; steps: { label: string; delta: number }[]; end: number; startLabel: string; endLabel: string; unit: string
}) {
  const n = steps.length + 2
  const W = Math.max(520, n * 92), H = 230, pl = 46, pb = 46, pt = 22
  const max = niceMax(Math.max(start, end, 1))
  const min = Math.min(0, end, ...steps.map((_, i) => start + steps.slice(0, i + 1).reduce((s, x) => s + x.delta, 0)))
  const span = max - min
  const y = (v: number) => pt + (H - pb - pt) * (1 - (v - min) / span)
  const slot = (W - pl) / n
  const bw = Math.min(56, slot * 0.62)
  let run = start
  const bars = steps.map((s) => {
    const from = run
    run += s.delta
    return { ...s, from, to: run }
  })
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label={`${startLabel} ${num(start)} ${unit} to ${endLabel} ${num(end)} ${unit}`}>
      {ticks(max).map((t) => (
        <g key={t}><line x1={pl} x2={W} y1={y(t)} y2={y(t)} stroke="#eeece5" /><text x={pl - 6} y={y(t) + 4} textAnchor="end" fontSize="10.5" fill="var(--ink-3)">{num(t)}</text></g>
      ))}
      <WBar x={pl + slot * 0.5} w={bw} y0={y(start)} y1={y(0)} fill="var(--sand)" label={num(start)} name={startLabel} H={H} />
      {bars.map((b, i) => {
        const top = y(Math.max(b.from, b.to)), bot = y(Math.min(b.from, b.to))
        const up = b.delta > 0
        return (
          <g key={b.label + i}>
            <line x1={pl + slot * (i + 0.5) + bw / 2} x2={pl + slot * (i + 1.5) - bw / 2} y1={y(b.from)} y2={y(b.from)} stroke="#cfcbbf" strokeDasharray="3 3" />
            <rect x={pl + slot * (i + 1.5) - bw / 2} y={top} width={bw} height={Math.max(2, bot - top)} rx="4" fill={up ? 'var(--band-4)' : 'var(--leaf-2)'} />
            <text x={pl + slot * (i + 1.5)} y={top - 6} textAnchor="middle" fontSize="11" fontWeight="600" fill={up ? 'var(--red)' : 'var(--green)'}>{up ? '+' : '−'}{num(Math.abs(b.delta))}</text>
            <foreignObject x={pl + slot * (i + 1)} y={H - pb + 6} width={slot} height={pb - 6}>
              <div style={{ fontSize: 10.5, lineHeight: 1.2, textAlign: 'center', color: 'var(--ink-2)' }}>{b.label}</div>
            </foreignObject>
          </g>
        )
      })}
      <WBar x={pl + slot * (n - 0.5)} w={bw} y0={y(end)} y1={y(0)} fill="var(--green)" label={num(end)} name={endLabel} H={H} bold />
    </svg>
  )
}

function WBar({ x, w, y0, y1, fill, label, name, H, bold }: { x: number; w: number; y0: number; y1: number; fill: string; label: string; name: string; H: number; bold?: boolean }) {
  return (
    <g>
      <rect x={x - w / 2} y={y0} width={w} height={Math.max(2, y1 - y0)} rx="4" fill={fill} />
      <text x={x} y={y0 - 6} textAnchor="middle" fontSize="11.5" fontWeight="600" fill="var(--ink)">{label}</text>
      <foreignObject x={x - 50} y={H - 40} width={100} height={40}>
        <div style={{ fontSize: 10.5, lineHeight: 1.2, textAlign: 'center', color: 'var(--ink-2)', fontWeight: bold ? 600 : 400 }}>{name}</div>
      </foreignObject>
    </g>
  )
}

/** Line with area, plus optional heat cells behind it (Garmi mode). */
export function HeatLine({ months, values, heat, heatTitle, height = 220 }: {
  months: string[]; values: (number | null)[]; heat?: (number | null)[]; heatTitle?: (i: number) => string; height?: number
}) {
  const W = 760, H = height, pl = 44, pb = 34, pt = heat ? 34 : 10
  const vs = values.filter((v): v is number => v != null)
  const max = niceMax(Math.max(1, ...vs))
  const slot = (W - pl) / months.length
  const x = (i: number) => pl + slot * (i + 0.5)
  const y = (v: number) => pt + (H - pb - pt) * (1 - v / max)
  const pts = values.map((v, i) => (v == null ? null : [x(i), y(v)] as const))
  const path = pts.reduce((d, p, i) => (p ? d + `${d && pts[i - 1] ? 'L' : 'M'}${p[0]},${p[1]}` : d), '')
  const hmax = Math.max(1, ...(heat ?? []).map((h) => h ?? 0))
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Monthly electricity use against heat">
      {heat?.map((h, i) => (
        <rect key={i} x={pl + slot * i + 1} y={4} width={slot - 2} height={22} rx="3"
          fill={h == null ? '#f2f0ea' : heatColor((h ?? 0) / hmax)} data-testid="heat-cell"><title>{`${months[i]}: ${heatTitle ? heatTitle(i) : h ?? 'no data'}`}</title></rect>
      ))}
      {ticks(max).map((t) => (
        <g key={t}><line x1={pl} x2={W} y1={y(t)} y2={y(t)} stroke="#eeece5" /><text x={pl - 6} y={y(t) + 4} textAnchor="end" fontSize="10.5" fill="var(--ink-3)">{num(t)}</text></g>
      ))}
      <path d={path} fill="none" stroke="var(--leaf)" strokeWidth="2" />
      {pts.map((p, i) => p && <circle key={i} cx={p[0]} cy={p[1]} r="3.5" fill="var(--leaf)"><title>{`${months[i]}: ${num(values[i])} kWh`}</title></circle>)}
      {months.map((m, i) => (i % Math.ceil(months.length / 12) === 0 ? <text key={m + i} x={x(i)} y={H - 12} textAnchor="middle" fontSize="10.5" fill="var(--ink-3)">{m}</text> : null))}
    </svg>
  )
}
export const heatColor = (t: number) => (t <= 0 ? '#fbf3e4' : t < 0.34 ? '#f8dcae' : t < 0.67 ? '#f0a76a' : '#d9533b')

export function Histogram({ edges, counts, height = 200 }: { edges: number[]; counts: number[]; height?: number }) {
  const W = 480, H = height, pl = 40, pb = 22, pt = 8
  const max = niceMax(Math.max(1, ...counts))
  const bw = (W - pl) / counts.length
  const y = (v: number) => pt + (H - pb - pt) * (1 - v / max)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Distribution of scores">
      {ticks(max).map((t) => (
        <g key={t}><line x1={pl} x2={W} y1={y(t)} y2={y(t)} stroke="#eeece5" /><text x={pl - 6} y={y(t) + 4} textAnchor="end" fontSize="10.5" fill="var(--ink-3)">{num(t)}</text></g>
      ))}
      {counts.map((c, i) => (
        <rect key={i} x={pl + i * bw + 1} y={y(c)} width={bw - 2} height={y(0) - y(c)} rx="2" fill={BAND_COLOR[bandOf(edges[i] + 2.5)]}>
          <title>{`Score ${edges[i]}–${edges[i + 1]}: ${num(c)} homes`}</title>
        </rect>
      ))}
      {[0, 20, 40, 60, 80, 100].map((t) => (
        <text key={t} x={pl + ((W - pl) * t) / 100} y={H - 6} textAnchor="middle" fontSize="10.5" fill="var(--ink-3)">{t}</text>
      ))}
    </svg>
  )
}

export function Donut({ parts, size = 170, center, sub }: { parts: { label: string; value: number; color: string }[]; size?: number; center: string; sub: string }) {
  const total = parts.reduce((s, p) => s + p.value, 0) || 1
  const r = size / 2 - 14, c = 2 * Math.PI * r
  let off = 0
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={parts.map((p) => `${p.label} ${p.value}`).join(', ')}>
      {parts.map((p) => {
        const len = (c * p.value) / total
        const el = <circle key={p.label} cx={size / 2} cy={size / 2} r={r} fill="none" stroke={p.color} strokeWidth="24" strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-off} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
        off += len
        return el
      })}
      <text x="50%" y="47%" textAnchor="middle" style={{ font: `500 ${size * 0.15}px var(--serif)` }} fill="var(--ink)">{center}</text>
      <text x="50%" y="60%" textAnchor="middle" fontSize="11" fill="var(--ink-3)">{sub}</text>
    </svg>
  )
}

/** Low-high range on an axis, with the point estimate. */
export function RangeBar({ lo, hi, mid, min, max, format }: { lo: number; hi: number; mid?: number; min: number; max: number; format: (v: number) => string }) {
  const p = (v: number) => `${((v - min) / (max - min || 1)) * 100}%`
  return (
    <div style={{ padding: '18px 0 4px' }}>
      <div style={{ position: 'relative', height: 6, background: '#edeee8', borderRadius: 99 }}>
        <div style={{ position: 'absolute', left: p(lo), width: `calc(${p(hi)} - ${p(lo)})`, top: 0, bottom: 0, background: 'var(--leaf-2)', borderRadius: 99 }} />
        {mid != null && <div style={{ position: 'absolute', left: p(mid), top: -5, width: 16, height: 16, marginLeft: -8, borderRadius: '50%', background: 'var(--green)', border: '3px solid #fff', boxShadow: '0 0 0 1px var(--line)' }} />}
      </div>
      <div className="row between tiny muted" style={{ marginTop: 8 }}><span>{format(lo)}</span><span>{format(hi)}</span></div>
    </div>
  )
}

/** Cities placed by latitude/longitude (equirectangular over India's bounding box). */
export function CityDots({ points, onPick, selected }: {
  points: { city: string; lat: number; lon: number; size: number; color: string; title: string }[]; onPick?: (c: string) => void; selected?: string
}) {
  const W = 420, H = 440
  const [lo0, lo1, la0, la1] = [67.5, 97.5, 7, 35.5]
  const x = (lon: number) => ((lon - lo0) / (lo1 - lo0)) * W
  const y = (lat: number) => ((la1 - lat) / (la1 - la0)) * H
  const smax = Math.max(1, ...points.map((p) => p.size))
  const labelled = new Set([...points].sort((a, b) => b.size - a.size).slice(0, 8).map((p) => p.city))
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Financed emissions by city" style={{ background: '#eef3ef', borderRadius: 12 }}>
      {[10, 15, 20, 25, 30, 35].map((l) => <line key={l} x1="0" x2={W} y1={y(l)} y2={y(l)} stroke="#dfe8e2" />)}
      {[70, 75, 80, 85, 90, 95].map((l) => <line key={l} y1="0" y2={H} x1={x(l)} x2={x(l)} stroke="#dfe8e2" />)}
      {[...points].sort((a, b) => b.size - a.size).map((p) => {
        const r = 5 + 17 * Math.sqrt(p.size / smax)
        return (
          <g key={p.city} onClick={() => onPick?.(p.city)} style={{ cursor: onPick ? 'pointer' : 'default' }}>
            <circle cx={x(p.lon)} cy={y(p.lat)} r={r} fill={p.color} fillOpacity="0.78" stroke={selected === p.city ? 'var(--ink)' : '#fff'} strokeWidth={selected === p.city ? 2.5 : 1.5}>
              <title>{p.title}</title>
            </circle>
            {labelled.has(p.city) && <text x={x(p.lon)} y={y(p.lat) - r - 3} textAnchor="middle" fontSize="10.5" fill="var(--ink-2)">{p.city}</text>}
          </g>
        )
      })}
    </svg>
  )
}

function niceMax(v: number) {
  const p = 10 ** Math.floor(Math.log10(v))
  for (const m of [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]) if (m * p >= v) return m * p
  return 10 * p
}
function ticks(max: number) {
  return [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(max * f))
}
