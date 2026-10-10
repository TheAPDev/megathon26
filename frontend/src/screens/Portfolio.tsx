// Screen 5: Lender portfolio (analyst role). Loan book efficiency, financed emissions, worst homes, upgrade
// ranking, green-finance targets and RWA common-solar leads.
import { useQuery } from '@tanstack/react-query'
import { ArrowDownUp, Download, Factory, Gauge as GaugeIcon, Info, Landmark, MapPin, RotateCcw, Users } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Api } from '../api/endpoints'
import { useCities, usePlan, useScenario, useScore } from '../api/hooks'
import type { Band, PoorHome, RankedHome, RwaLead, Target } from '../api/types'
import { CityDots, Donut, Gauge, Histogram, Waterfall } from '../components/charts'
import { BandChip, Card, Drawer, Empty, ErrorState, Loading, Q, ScorePill, Tabs } from '../components/ui'
import { BAND_COLOR, COMPONENT_LABEL, bandOf, humanize, inr, num, pct, years } from '../lib/format'

type TabKey = 'poor' | 'ranking' | 'targets' | 'rwa'
const BANDS: Band[] = ['Highly efficient', 'Good', 'Moderate', 'Poor', 'Very poor']
const listOf = (v: string[] | string) => (Array.isArray(v) ? v : (() => { try { return JSON.parse(v) as string[] } catch { return v ? [v] : [] } })())

export default function Portfolio() {
  const [sp, setSp] = useSearchParams()
  const city = sp.get('city') ?? undefined
  const state = sp.get('state') ?? undefined
  const tab = (sp.get('tab') as TabKey) ?? 'poor'
  const set = (k: string, v?: string) => setSp((p) => { const n = new URLSearchParams(p); if (v) n.set(k, v); else n.delete(k); return n }, { replace: true })
  const cities = useCities()
  const states = useMemo(() => Array.from(new Set((cities.data ?? []).map((c) => c.state))).sort(), [cities.data])
  const sum = useQuery({ queryKey: ['pf', 'summary', city, state], queryFn: () => Api.portfolioSummary(city, state), staleTime: 5 * 60_000 })
  const map = useQuery({ queryKey: ['pf', 'map'], queryFn: Api.portfolioMap, staleTime: 5 * 60_000 })
  const [home, setHome] = useState<{ id: string; pkg?: string[] } | null>(null)

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Lender portfolio</h1>
          <p className="page-sub">Track impact, manage risk and scale green home financing across India.</p>
        </div>
        <div className="row wrap" style={{ gap: 10 }}>
          <label className="field">City
            <select className="input" value={city ?? ''} onChange={(e) => set('city', e.target.value || undefined)} aria-label="City filter">
              <option value="">All cities</option>{(cities.data ?? []).filter((c) => !state || c.state === state).map((c) => <option key={c.city}>{c.city}</option>)}
            </select>
          </label>
          <label className="field">State
            <select className="input" value={state ?? ''} onChange={(e) => { set('state', e.target.value || undefined); set('city') }} aria-label="State filter">
              <option value="">All states</option>{states.map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
          <button className="btn ghost" style={{ alignSelf: 'flex-end' }} onClick={() => setSp({}, { replace: true })}><RotateCcw /> Reset</button>
        </div>
      </div>

      <Q q={sum} lines={2}>
        {(s) => s.homes_with_loans === 0 ? <Empty title="No homes with loans match these filters" /> : (
          <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12 }}>
            <Kpi icon={<Landmark />} label="Loan book outstanding" value={`₹${num(s.loan_book_outstanding_cr, 1)} Cr`} />
            <Kpi icon={<Users />} label="Homes with loans" value={num(s.homes_with_loans)} />
            <Kpi icon={<Factory />} label="Financed emissions" value={`${num(s.financed_emissions_t_co2)} t CO₂`} hint={s.method} />
            <Kpi icon={<Factory />} label="Reduction potential" value={`${num(s.financed_emissions_reduction_potential_t_co2)} t CO₂`} />
            <Kpi icon={<GaugeIcon />} label="Mean / median score" value={`${num(s.mean_score, 1)} / ${num(s.median_score)}`} />
            <Kpi icon={<Info />} label="Poor or very poor" value={pct(100 * s.poor_or_very_poor_share, 1)} />
            <Kpi icon={<Info />} label="Low-confidence scores" value={pct(100 * s.low_confidence_share, 1)} warn={s.low_confidence_share > 0.3} />
          </div>
        )}
      </Q>

      <div className="grid g-12">
        <Card className="span-4" title="Portfolio by score band">
          <Q q={sum} lines={5}>
            {(s) => (
              <div className="row wrap" style={{ gap: 18 }}>
                <Donut parts={BANDS.map((b) => ({ label: b, value: s.band_counts[b] ?? 0, color: BAND_COLOR[b] }))} center={num(s.homes_with_loans)} sub="homes" />
                <div className="stack" style={{ gap: 6 }}>
                  {BANDS.map((b) => (
                    <span key={b} className="small row" style={{ gap: 8 }}><i style={{ width: 10, height: 10, borderRadius: 3, background: BAND_COLOR[b], display: 'inline-block' }} />{b}<b style={{ marginLeft: 'auto' }}>{pct(s.homes_with_loans ? (100 * (s.band_counts[b] ?? 0)) / s.homes_with_loans : 0)}</b></span>
                  ))}
                </div>
              </div>
            )}
          </Q>
        </Card>
        <Card className="span-4" title="Distribution of Green Ghar Scores">
          <Q q={sum} lines={5}>{(s) => <Histogram edges={s.score_histogram.bin_edges} counts={s.score_histogram.counts} />}</Q>
        </Card>
        <Card className="span-4" title="Financed emissions by city" icon={<MapPin />} actions={<span className="tiny muted">All India</span>}>
          <Q q={map} lines={5}>
            {(m) => (
              <>
                <CityDots selected={city} onPick={(c) => set('city', c === city ? undefined : c)}
                  points={m.map((p) => ({ city: p.city, lat: p.lat, lon: p.lon, size: p.financed_emissions_t, color: BAND_COLOR[bandOf(p.mean_score)],
                    title: `${p.city}: ${num(p.homes)} homes, mean score ${num(p.mean_score, 1)}, ${num(p.financed_emissions_t)} t CO₂ financed` }))} />
                <p className="tiny muted" style={{ marginTop: 6 }}>Circle size: financed emissions. Colour: mean score band. Click a city to filter.</p>
              </>
            )}
          </Q>
        </Card>

        <Card className="span-12">
          <Tabs label="Portfolio lists" value={tab} onChange={(k) => set('tab', k)}
            tabs={[{ key: 'poor', label: 'Poor homes' }, { key: 'ranking', label: 'Upgrade ranking' }, { key: 'targets', label: 'Green-finance targets' }, { key: 'rwa', label: 'RWA leads' }]} />
          <div style={{ marginTop: 14 }}>
            {tab === 'poor' && <PoorTable city={city} state={state} onOpen={(id) => setHome({ id })} />}
            {tab === 'ranking' && <RankTable city={city} state={state} onOpen={(id, pkg) => setHome({ id, pkg })} />}
            {tab === 'targets' && <TargetTable city={city} onOpen={(id) => setHome({ id })} />}
            {tab === 'rwa' && <RwaTable />}
          </div>
        </Card>
      </div>
      <HomeDrawer home={home} onClose={() => setHome(null)} />
    </>
  )
}

function Kpi({ icon, label, value, hint, warn }: { icon: ReactNode; label: string; value: string; hint?: string; warn?: boolean }) {
  return (
    <div className="card" style={{ padding: 14, background: warn ? 'var(--amber-bg)' : undefined }} title={hint}>
      <div className="row tiny muted" style={{ gap: 6 }}>{icon && <span style={{ color: 'var(--leaf)', display: 'grid' }}>{icon}</span>}{label}</div>
      <div style={{ fontFamily: 'var(--serif)', fontSize: 24, marginTop: 6 }}>{value}</div>
    </div>
  )
}

/* ---- tables: server order by default, client sort within loaded rows, load more, CSV export ---------- */
type Col<T> = { key: string; label: string; get: (r: T) => string | number; render?: (r: T) => ReactNode; num?: boolean }

function DataTable<T>({ name, rows, cols, onRow, limit, setLimit, max, note }: {
  name: string; rows: T[]; cols: Col<T>[]; onRow?: (r: T) => void; limit: number; setLimit: (n: number) => void; max: number; note?: string
}) {
  const [sort, setSort] = useState<{ k: string; dir: 1 | -1 } | null>(null)
  const sorted = useMemo(() => {
    if (!sort) return rows
    const c = cols.find((x) => x.key === sort.k)!
    return [...rows].sort((a, b) => { const x = c.get(a), y = c.get(b); return (x < y ? -1 : x > y ? 1 : 0) * sort.dir })
  }, [rows, sort, cols])
  const csv = () => {
    // quote every cell and neutralise spreadsheet formulas (CSV injection)
    const esc = (v: unknown) => { const t = String(v); return `"${(/^[=+\-@]/.test(t) && Number.isNaN(Number(t)) ? `'${t}` : t).replace(/"/g, '""')}"` }
    const body = [cols.map((c) => esc(c.label)).join(','), ...sorted.map((r) => cols.map((c) => esc(c.get(r))).join(','))].join('\n')
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([(note ? `# ${note}\n` : '') + body], { type: 'text/csv' }))
    a.download = `greenghar_${name}_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}.csv`
    a.click()
    URL.revokeObjectURL(a.href)
  }
  return (
    <div className="stack">
      <div className="row between wrap">
        <span className="small muted">Showing {num(rows.length)} rows{sort ? ` · sorted within these ${num(rows.length)}` : ''}{note ? ` · ${note}` : ''}</span>
        <button className="btn ghost" onClick={csv} disabled={!rows.length}><Download /> Export CSV</button>
      </div>
      {rows.length === 0 ? <Empty title="No rows for these filters" /> : (
        <div className="table-wrap table-scroll">
          <table className="table">
            <thead><tr>{cols.map((c) => (
              <th key={c.key} scope="col" aria-sort={sort?.k === c.key ? (sort.dir === 1 ? 'ascending' : 'descending') : 'none'}>
                <button onClick={() => setSort((s) => (s?.k === c.key ? (s.dir === 1 ? { k: c.key, dir: -1 } : null) : { k: c.key, dir: 1 }))}>{c.label}<ArrowDownUp size={12} /></button>
              </th>))}</tr></thead>
            <tbody>
              {sorted.map((r, i) => (
                <tr key={i} className={onRow ? 'clickable' : undefined} onClick={() => onRow?.(r)} tabIndex={onRow ? 0 : undefined} onKeyDown={(e) => e.key === 'Enter' && onRow?.(r)}>
                  {cols.map((c) => <td key={c.key} style={{ textAlign: c.num ? 'right' : undefined }}>{c.render ? c.render(r) : c.get(r)}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {rows.length >= limit && limit < max && <button className="btn ghost" onClick={() => setLimit(Math.min(max, limit + 200))}>Load {Math.min(200, max - limit)} more</button>}
    </div>
  )
}

function useList<T>(key: unknown[], fn: (limit: number) => Promise<T[]>) {
  const [limit, setLimit] = useState(50)
  const q = useQuery({ queryKey: [...key, limit], queryFn: () => fn(limit), staleTime: 5 * 60_000, placeholderData: (p) => p })
  return { q, limit, setLimit }
}

function PoorTable({ city, state, onOpen }: { city?: string; state?: string; onOpen: (id: string) => void }) {
  const { q, limit, setLimit } = useList(['pf', 'poor', city, state], (l) => Api.poorHomes(l, city, state))
  const cols: Col<PoorHome>[] = [
    { key: 'home', label: 'Home', get: (r) => r.home_id }, { key: 'cust', label: 'Customer', get: (r) => r.customer_id }, { key: 'city', label: 'City', get: (r) => r.city },
    { key: 'score', label: 'Score', get: (r) => r.score, render: (r) => <ScorePill score={r.score} /> }, { key: 'band', label: 'Band', get: (r) => r.band },
    { key: 'issue', label: 'Key issue', get: (r) => COMPONENT_LABEL[r.key_issue.replace(/ /g, '_')] ?? humanize(r.key_issue) },
    { key: 'conf', label: 'Confidence', get: (r) => r.confidence }, { key: 'warn', label: 'Warnings', get: (r) => listOf(r.warnings).length, num: true },
  ]
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  if (!q.data) return <Loading lines={6} />
  return <DataTable name="poor_homes" rows={q.data} cols={cols} limit={limit} setLimit={setLimit} max={500} onRow={(r) => onOpen(r.home_id)} />
}

function RankTable({ city, state, onOpen }: { city?: string; state?: string; onOpen: (id: string, pkg: string[]) => void }) {
  const { q, limit, setLimit } = useList(['pf', 'rank', city, state], (l) => Api.ranking(l, city, state))
  const cols: Col<RankedHome>[] = [
    { key: 'home', label: 'Home', get: (r) => r.home_id }, { key: 'city', label: 'City', get: (r) => r.city },
    { key: 'score', label: 'Score → after', get: (r) => r.score, render: (r) => <span className="row" style={{ gap: 6 }}><ScorePill score={r.score} />→<ScorePill score={r.score_after_package} /></span> },
    { key: 'imp', label: 'Improvement', get: (r) => r.improvement_potential_pct, render: (r) => pct(r.improvement_potential_pct, 1), num: true },
    { key: 'inr', label: 'Saving / yr', get: (r) => r.package_saving_inr_year, render: (r) => inr(r.package_saving_inr_year), num: true },
    { key: 'co2', label: 'CO₂ t/yr', get: (r) => r.co2_saving_t_year, render: (r) => num(r.co2_saving_t_year, 2), num: true },
    { key: 'fco2', label: 'Financed CO₂ t/yr', get: (r) => r.financed_co2_reduction_t_year, render: (r) => num(r.financed_co2_reduction_t_year, 3), num: true },
    { key: 'pkg', label: 'Measures', get: (r) => listOf(r.package).length, num: true },
  ]
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  if (!q.data) return <Loading lines={6} />
  return <DataTable name="upgrade_ranking" rows={q.data} cols={cols} limit={limit} setLimit={setLimit} max={500} onRow={(r) => onOpen(r.home_id, listOf(r.package))} />
}

function TargetTable({ city, onOpen }: { city?: string; onOpen: (id: string) => void }) {
  const { q, limit, setLimit } = useList(['pf', 'targets', city], (l) => Api.targets(l, city))
  const cols: Col<Target>[] = [
    { key: 'cust', label: 'Customer', get: (r) => r.customer_id }, { key: 'home', label: 'Home', get: (r) => r.home_id }, { key: 'city', label: 'City', get: (r) => r.city },
    { key: 'score', label: 'Score', get: (r) => r.score, render: (r) => <ScorePill score={r.score} /> }, { key: 'offer', label: 'Offer', get: (r) => r.offer },
    { key: 'inr', label: 'Saving / yr', get: (r) => r.package_saving_inr_year, render: (r) => inr(r.package_saving_inr_year), num: true },
    { key: 'imp', label: 'Improvement', get: (r) => r.improvement_potential_pct, render: (r) => pct(r.improvement_potential_pct, 1), num: true },
    { key: 'credit', label: 'Credit band', get: (r) => r.credit_band }, { key: 'lang', label: 'Language', get: (r) => r.language },
  ]
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  if (!q.data) return <Loading lines={6} />
  return <DataTable name="green_finance_targets" rows={q.data} cols={cols} limit={limit} setLimit={setLimit} max={1000} onRow={(r) => onOpen(r.home_id)} note="Marketing-consented customers only" />
}

function RwaTable() {
  const { q, limit, setLimit } = useList(['pf', 'rwa'], (l) => Api.rwaLeads(l))
  const cols: Col<RwaLead>[] = [
    { key: 'soc', label: 'Society', get: (r) => r.society_id }, { key: 'city', label: 'City', get: (r) => r.city },
    { key: 'cust', label: 'Customers', get: (r) => r.customers, num: true }, { key: 'noroof', label: 'Without private roof', get: (r) => r.without_private_roof, num: true },
    { key: 'score', label: 'Mean score', get: (r) => r.mean_score, render: (r) => num(r.mean_score, 1), num: true },
    { key: 'kw', label: 'Common solar kW', get: (r) => r.suggested_common_solar_kw, num: true },
    { key: 'sub', label: 'RWA subsidy', get: (r) => r.rwa_subsidy_inr, render: (r) => inr(r.rwa_subsidy_inr), num: true },
  ]
  if (q.error && !q.data) return <ErrorState error={q.error} onRetry={() => q.refetch()} />
  if (!q.data) return <Loading lines={6} />
  return <DataTable name="rwa_leads" rows={q.data} cols={cols} limit={limit} setLimit={setLimit} max={500} note="All India, societies with 4+ customers" />
}

function HomeDrawer({ home, onClose }: { home: { id: string; pkg?: string[] } | null; onClose: () => void }) {
  const id = home?.id ?? null
  const score = useScore(id)
  const plan = usePlan(home && !home.pkg ? id : null)
  const pkg = home?.pkg ?? (plan.data?.recommendations ?? []).filter((r) => !['Infeasible', 'Excluded'].includes(r.suitability)).map((r) => r.retrofit_id)
  const sc = useScenario(id, pkg, {})
  return (
    <Drawer open={!!home} onClose={onClose} title={`Home ${home?.id ?? ''}`}>
      <Q q={score} lines={5}>
        {(s) => (
          <div className="stack">
            <div className="row" style={{ gap: 18 }}>
              <Gauge score={s.score} size={120} hatched={s.confidence === 'low'} />
              <div className="stack" style={{ gap: 6 }}><BandChip band={s.band} /><span className="small">Confidence: <b>{s.confidence}</b></span><span className="small">Use: <b>{num(s.annual_grid_kwh)} kWh/yr</b></span></div>
            </div>
            <div className="stack" style={{ gap: 4 }}>
              {s.components.map((c) => <div key={c.component} className="row between small"><span>{COMPONENT_LABEL[c.component] ?? c.component}</span><b>{Math.round(c.score)}</b></div>)}
            </div>
          </div>
        )}
      </Q>
      <div className="card">
        <b>Projected improvement (full package)</b>
        {sc.isLoading || plan.isLoading ? <Loading lines={4} /> : sc.error ? <ErrorState error={sc.error} /> : !sc.data ? <p className="small muted">No feasible measures.</p> : (
          <div className="stack" style={{ marginTop: 8 }}>
            <div className="row wrap" style={{ gap: 16 }}><span>Score <b>{sc.data.score_before} → {sc.data.score_after}</b></span><span>Saves <b>{inr(sc.data.saving_inr_year)}/yr</b></span><span>CO₂ <b>{num(sc.data.co2_saving_kg_year / 1000, 2)} t/yr</b></span></div>
            <Waterfall start={sc.data.baseline.grid_kwh} end={sc.data.after.grid_kwh} unit="kWh" startLabel="Today" endLabel="After"
              steps={sc.data.steps.map((x) => ({ label: x.name, delta: -x.saving_kwh_electricity }))} />
            <span className="small">Upfront after subsidy: <b>{inr(sc.data.steps.reduce((a, x) => a + x.net_cost_inr[0], 0))} – {inr(sc.data.steps.reduce((a, x) => a + x.net_cost_inr[1], 0))}</b> · payback {years(sc.data.saving_inr_year > 0 ? sc.data.steps.reduce((a, x) => a + (x.net_cost_inr[0] + x.net_cost_inr[1]) / 2, 0) / sc.data.saving_inr_year : null)}</span>
          </div>
        )}
      </div>
      <p className="tiny muted">Customer details beyond the ID are not shown here; contact goes through your CRM using the customer ID.</p>
    </Drawer>
  )
}
