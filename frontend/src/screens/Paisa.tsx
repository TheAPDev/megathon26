// Screen 3: Paisa. Can I afford it and is it worth it? Finance, subsidy, payback, value, solar, roadmap.
import { CalendarRange, Check, CheckCircle2, ClipboardCopy, ExternalLink, FileText, Home, Landmark, Pencil, Plus, Sun, Timer, Wallet, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { describeError } from '../api/client'
import { Api } from '../api/endpoints'
import { useFinance, usePlan, useRetrofits, useRoadmap, useSolar, useValue } from '../api/hooks'
import type { SubsidyApplication } from '../api/types'
import { RangeBar } from '../components/charts'
import { Card, Drawer, Empty, ErrorState, Loading, Q, Stepper, Tabs, useDebounced, useToast } from '../components/ui'
import { humanize, inr, inrRange, inrShort, kwh, num, years } from '../lib/format'
import { useSelection } from '../lib/selection'
import { useSession } from '../state/session'

export default function Paisa() {
  const id = useSession((s) => s.activeHomeId)!
  const cat = useRetrofits()
  const order = useMemo(() => Object.fromEntries((cat.data ?? []).map((r) => [r.retrofit_id, r.order_rank])), [cat.data])
  const names = useMemo(() => Object.fromEntries((cat.data ?? []).map((r) => [r.retrofit_id, r.name])), [cat.data])
  const sel = useSelection(order)
  const plan = usePlan(id)
  const [down, setDown] = useState(0)
  const dDown = useDebounced(down, 300)
  const fin = useFinance(id, sel.selected, sel.params, dDown)
  const val = useValue(id, sel.selected)
  const recommended = (plan.data?.recommendations ?? []).filter((r) => r.suitability === 'High').map((r) => r.retrofit_id)
  const addable = (plan.data?.recommendations ?? []).filter((r) => !['Infeasible', 'Excluded'].includes(r.suitability) && !sel.selected.includes(r.retrofit_id))

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Paisa: value, finance & solar</h1>
          <p className="page-sub">Make the numbers work for your home.</p>
        </div>
      </div>

      <div className="grid g-12">
        <Card className="span-8" title="Package summary" serif icon={<Wallet />} actions={<Link className="btn link" to={`/studio?${sel.qs}`}><Pencil /> Edit in studio</Link>}>
          <div className="row wrap" style={{ gap: 8 }}>
            {sel.selected.map((r) => (
              <span key={r} className="chip outline">{names[r] ?? humanize(r)}<button aria-label={`Remove ${names[r] ?? r}`} onClick={() => sel.toggle(r)}><X size={14} /></button></span>
            ))}
            {addable.length > 0 && (
              <select className="input" style={{ width: 'auto' }} value="" onChange={(e) => e.target.value && sel.toggle(e.target.value)} aria-label="Add an upgrade">
                <option value="">+ Add upgrade</option>
                {addable.map((r) => <option key={r.retrofit_id} value={r.retrofit_id}>{r.name}</option>)}
              </select>
            )}
            <span style={{ flex: 1 }} />
            <span className="field" style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>Down payment
              <Stepper label="Down payment in rupees" value={down} step={5000} min={0} max={10_000_000} format={(v) => inr(v)} onChange={setDown} />
            </span>
          </div>
          <div className="sep" />
          {sel.selected.length === 0 ? (
            <Empty title="Pick the upgrades to finance">
              <span className="small">Choose them in the studio, or start from the recommended package.</span>
              <div className="row">
                {recommended.length > 0 && <button className="btn primary" onClick={() => sel.setSelected(recommended)}><Plus /> Use recommended package</button>}
                <Link className="btn ghost" to="/studio">Open studio</Link>
              </div>
            </Empty>
          ) : fin.isLoading ? <Loading lines={4} /> : fin.error && !fin.data ? <ErrorState error={fin.error} onRetry={() => fin.refetch()} /> : fin.data && (
            <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, opacity: fin.isFetching ? 0.6 : 1 }}>
              <div className="card" style={{ boxShadow: 'none' }}>
                <span className="small muted">Estimated bill savings</span>
                <div className="num">{inr(fin.data.bill_saving_inr_month)} <span className="small muted">/mo</span></div>
                <div className="bar-track" style={{ marginTop: 8 }}><div className="bar-fill" style={{ width: `${Math.min(100, (100 * fin.data.bill_saving_inr_month) / Math.max(1, fin.data.bill_saving_inr_month, fin.data.total_emi_inr_month))}%` }} /></div>
              </div>
              <div className="card" style={{ boxShadow: 'none' }}>
                <span className="small muted">Loan EMI</span>
                <div className="num">{inr(fin.data.total_emi_inr_month)} <span className="small muted">/mo</span></div>
                <div className="bar-track" style={{ marginTop: 8 }}><div className="bar-fill" style={{ background: '#8f9a93', width: `${Math.min(100, (100 * fin.data.total_emi_inr_month) / Math.max(1, fin.data.bill_saving_inr_month, fin.data.total_emi_inr_month))}%` }} /></div>
              </div>
              <div className={`alert ${fin.data.emi_covered_by_saving ? 'green' : ''}`} style={{ alignItems: 'center' }}>
                {fin.data.emi_covered_by_saving ? <CheckCircle2 /> : <Timer />}
                <div>
                  <b style={{ fontFamily: 'var(--serif)', fontSize: 19 }}>{fin.data.near_zero_bill && fin.data.pivot_note ? 'Bill already near zero' : fin.data.emi_covered_by_saving ? 'Pays for itself' : `Costs ${inr(fin.data.total_emi_inr_month - fin.data.bill_saving_inr_month)}/month net`}</b>
                  <div className="tiny">{fin.data.pivot_note ?? (fin.data.emi_covered_by_saving ? 'Your savings are higher than your EMI from month one.' : 'Savings cover part of the EMI; the rest pays back over time.')}</div>
                </div>
              </div>
              {fin.data.refused.length > 0 && (
                <div className="alert" style={{ gridColumn: '1 / -1' }}><X />
                  <div className="small">{fin.data.refused.map((r) => <div key={r.retrofit_id}><b>{names[r.retrofit_id] ?? r.retrofit_id}</b> is not included: {r.reason}</div>)}</div>
                </div>
              )}
            </div>
          )}
        </Card>

        <Card className="span-4" title="Total cost breakdown" serif>
          {fin.data && sel.selected.length > 0 ? (
            <div className="row" style={{ gap: 8, alignItems: 'stretch' }}>
              <CostBox label={`Gross cost (${fin.data.retrofits.length} upgrades)`} value={inrShort(fin.data.gross_cost_inr)} bg="var(--sand-2)" />
              <span className="row muted">−</span>
              <CostBox label="Subsidy" value={inrShort(fin.data.subsidy_inr)} bg="var(--mint)" />
              <span className="row muted">=</span>
              <CostBox label="Net cost" value={inrShort(fin.data.net_cost_inr)} bg="#f2f1ec" />
            </div>
          ) : <p className="small muted">Shown once you pick upgrades.</p>}
        </Card>

        <Card className="span-5" title="Financing options" icon={<Landmark />}>
          {fin.data && sel.selected.length > 0 ? (
            fin.data.loans.length === 0 ? <p className="small muted">No loan needed for this package.</p> : (
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th scope="col">Loan</th><th scope="col">Amount</th><th scope="col">Rate (p.a.)</th><th scope="col">Tenure</th><th scope="col">Monthly EMI</th></tr></thead>
                  <tbody>
                    {fin.data.loans.map((l) => (
                      <tr key={l.product}><td>{l.product}</td><td>{inr(l.principal_inr)}</td><td>{num(l.rate_pct, 2)}%</td><td>{num(l.tenure_years)} years</td><td><b>{inr(l.emi_inr)}</b></td></tr>
                    ))}
                  </tbody>
                </table>
                <p className="tiny muted" style={{ marginTop: 8 }}>{fin.data.assumptions.rates}. Tariffs rise {num(fin.data.assumptions.tariff_escalation_pct, 1)}% a year in the 25-year view.</p>
              </div>
            )
          ) : <p className="small muted">Pick upgrades to see loan options.</p>}
        </Card>

        <Card className="span-3" title="Estimated package payback" icon={<Timer />}>
          {fin.data && sel.selected.length > 0 ? (
            <div className="stack">
              <span className="big">{fin.data.simple_payback_years == null ? 'n/a' : years(fin.data.simple_payback_years)}</span>
              <span className="small muted">{fin.data.simple_payback_years == null ? "Doesn't pay back on bill savings alone." : `Based on ${inr(fin.data.bill_saving_inr_month)}/month savings.`}</span>
              <div className="sep" />
              <span className="small">25-year savings <b>{inrShort(fin.data.savings_25yr_inr)}</b></span>
              <span className="small">CO₂ cut <b>{num(fin.data.co2_saving_kg_year)} kg/yr</b></span>
            </div>
          ) : <p className="small muted">–</p>}
        </Card>

        <Card className="span-4" title="Property value uplift" icon={<Home />}>
          <Q q={val} lines={3}>
            {(v) => !v.available ? <p className="small muted">{v.label}</p> : (
              <div className="stack">
                <span className="big">{v.uplift_pct != null && sel.selected.length ? `+${num(v.uplift_pct, 1)}%` : inrShort(v.current_value_inr)}</span>
                <span className="small muted">{v.uplift_pct != null && sel.selected.length ? 'Estimated increase in property value' : 'Estimated current value'}</span>
                {v.current_value_range_inr && <RangeBar lo={v.current_value_range_inr[0]} hi={v.current_value_range_inr[1]} mid={v.current_value_inr} min={v.current_value_range_inr[0] * 0.95} max={v.current_value_range_inr[1] * 1.05} format={inrShort} />}
                <span className="tiny muted">{v.interval} · {v.caveat}</span>
              </div>
            )}
          </Q>
        </Card>

        <SolarCard id={id} onUse={(kw) => { if (!sel.selected.includes('rooftop_solar')) sel.setSelected([...sel.selected, 'rooftop_solar']); sel.setPvKw(kw) }} />
        <Roadmap id={id} />
      </div>
    </>
  )
}

const CostBox = ({ label, value, bg }: { label: string; value: string; bg: string }) => (
  <div style={{ flex: 1, background: bg, borderRadius: 12, padding: 12, textAlign: 'center' }}>
    <div className="tiny muted">{label}</div><div style={{ fontFamily: 'var(--serif)', fontSize: 22, marginTop: 6 }}>{value}</div>
  </div>
)

function SolarCard({ id, onUse }: { id: string; onUse: (kw: number) => void }) {
  const [kw, setKw] = useState<number | undefined>()
  const dKw = useDebounced(kw, 300)
  const q = useSolar(id, dKw)
  const [app, setApp] = useState<SubsidyApplication | null>(null)
  const [appErr, setAppErr] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const toast = useToast()
  const trackKey = `paisa:tracker:${id}`
  const [done, setDone] = useState<Record<string, boolean>>({})
  useEffect(() => { try { setDone(JSON.parse(localStorage.getItem(trackKey) ?? '{}')) } catch { setDone({}) } }, [trackKey])
  const tick = (s: string) => setDone((d) => { const n = { ...d, [s]: !d[s] }; try { localStorage.setItem(trackKey, JSON.stringify(n)) } catch { /* storage blocked */ } return n })
  const prepare = async () => {
    setLoading(true); setAppErr(null)
    try { setApp(await Api.subsidyApplication(id)) } catch (e) { setAppErr(describeError(e)) } finally { setLoading(false) }
  }
  const copy = async (k: string, v: unknown) => {
    try { await navigator.clipboard.writeText(String(v)); toast({ kind: 'ok', title: `${humanize(k)} copied` }) } catch { toast({ kind: 'warn', title: 'Copy failed', body: 'Select and copy the value manually.' }) }
  }
  return (
    <>
      <Card className="span-5" title="Solar calculator" icon={<Sun />}>
        <Q q={q} lines={4}>
          {(s) => (
            <div className="stack">
              <div className="row wrap" style={{ gap: 18 }}>
                <div className="field">PV size<Stepper label="Solar size in kW" value={kw ?? s.quote.kw} min={0.5} max={10} step={0.5} format={(v) => `${num(v, 1)} kW`} onChange={setKw} /></div>
                <div><span className="tiny muted">Annual generation</span><div className="num">{kwh(s.quote.annual_generation_kwh)}</div></div>
                <div><span className="tiny muted">Roof area needed</span><div className="num">{num(s.quote.roof_needed_m2)} m²</div></div>
              </div>
              <div className="kv">
                <div><span className="tiny muted">Gross cost</span><b className="small">{inrRange(s.quote.gross_cost_inr)}</b></div>
                <div><span className="tiny muted">Subsidy (central + state)</span><b className="small">{inr(s.quote.central_subsidy_inr + s.quote.state_topup_inr)}</b></div>
                <div><span className="tiny muted">Net cost</span><b className="small">{inrRange(s.quote.net_cost_inr)}</b></div>
              </div>
              {s.subsidy.eligible ? <button className="btn ghost" onClick={() => onUse(kw ?? s.quote.kw)}>Use {num(kw ?? s.quote.kw, 1)} kW in my package</button>
                : <span className="tiny muted">Indicative only: rooftop solar can't be added to this home's package (see the navigator).</span>}
            </div>
          )}
        </Q>
      </Card>
      <Card className="span-7" title="Subsidy navigator (PM Surya Ghar)" icon={<FileText />}>
        <Q q={q} lines={4}>
          {(s) => !s.subsidy.eligible ? (
            <div className="alert"><X /><div className="small"><b>Not eligible for rooftop solar subsidy.</b><div>{s.subsidy.why_not}</div></div></div>
          ) : (
            <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1.4fr) minmax(0, 1fr)', gap: 16 }}>
              <div className="stack">
                <span className="small">Up to <b>{inr(s.subsidy.central_subsidy_inr + s.subsidy.state_topup_inr)}</b> for {num(s.subsidy.kw, 1)} kW.</span>
                <ol className="stack" style={{ paddingLeft: 0, listStyle: 'none', margin: 0 }}>
                  {s.subsidy.steps.map((st, i) => (
                    <li key={st} className="row" style={{ alignItems: 'flex-start' }}>
                      <button className="icon-btn" style={{ width: 26, height: 26, borderRadius: 99, background: done[st] ? 'var(--green)' : undefined, color: done[st] ? '#fff' : undefined }} onClick={() => tick(st)} aria-pressed={!!done[st]} aria-label={`Mark step ${i + 1} done`}>
                        {done[st] ? <Check size={14} /> : <span className="tiny">{i + 1}</span>}
                      </button>
                      <span className="small" style={{ flex: 1 }}>{st}</span>
                    </li>
                  ))}
                </ol>
                <span className="tiny muted">Ticks are saved on this device.</span>
              </div>
              <div className="card stack" style={{ boxShadow: 'none' }}>
                <b className="small">Documents you'll need</b>
                {s.subsidy.documents.map((d) => <span key={d} className="small row"><CheckCircle2 size={15} color="var(--leaf)" />{d}</span>)}
                <button className="btn primary" onClick={prepare} disabled={loading}>{loading ? 'Preparing…' : 'Prepare my application'}</button>
                {appErr && <span className="err">{appErr}</span>}
              </div>
            </div>
          )}
        </Q>
      </Card>
      <Drawer open={!!app} onClose={() => setApp(null)} title="Your PM Surya Ghar application">
        {app && (
          <div className="stack">
            <p className="small">These details are filled in from your home. Copy each into the national portal.</p>
            {Object.entries(app.prefilled).map(([k, v]) => (
              <div key={k} className="row between card" style={{ padding: 12, boxShadow: 'none' }}>
                <span><span className="tiny muted">{humanize(k)}</span><b style={{ display: 'block' }}>{String(v)}</b></span>
                <button className="icon-btn" aria-label={`Copy ${humanize(k)}`} onClick={() => copy(k, v)}><ClipboardCopy size={16} /></button>
              </div>
            ))}
            <b className="small">You'll still need</b>
            <ul className="small" style={{ margin: 0 }}>{app.to_complete_by_user.map((x) => <li key={x}>{x}</li>)}</ul>
            <a className="btn primary" href={app.portal} target="_blank" rel="noopener noreferrer"><ExternalLink /> Open the portal</a>
          </div>
        )}
      </Drawer>
    </>
  )
}

function Roadmap({ id }: { id: string }) {
  const [budget, setBudget] = useState(40000)
  const [yrs, setYrs] = useState(3)
  const [obj, setObj] = useState<'inr' | 'co2' | 'kwh'>('inr')
  const dBudget = useDebounced(budget, 400)
  const q = useRoadmap(id, dBudget, yrs, obj)
  return (
    <Card className="span-12" title="Roadmap planner" icon={<CalendarRange />}
      actions={
        <div className="row wrap" style={{ gap: 10 }}>
          <Stepper label="Budget per year" value={budget} min={1000} max={5_000_000} step={5000} format={(v) => inr(v)} onChange={setBudget} />
          <select className="input" style={{ width: 'auto' }} value={yrs} onChange={(e) => setYrs(Number(e.target.value))} aria-label="Years">{[1, 2, 3, 4, 5].map((y) => <option key={y} value={y}>{y} year{y > 1 ? 's' : ''}</option>)}</select>
          <Tabs label="Optimise for" value={obj} onChange={setObj} tabs={[{ key: 'inr', label: 'Savings' }, { key: 'co2', label: 'CO₂' }, { key: 'kwh', label: 'kWh' }]} />
        </div>
      }>
      <Q q={q} lines={4}>
        {(r) => (
          <div className="stack" style={{ opacity: q.isFetching ? 0.6 : 1 }}>
            <div className="grid" style={{ gridTemplateColumns: `repeat(${r.years.length}, minmax(0, 1fr)) minmax(180px, .8fr)`, gap: 12, overflowX: 'auto' }}>
              {r.years.map((y) => (
                <div key={y.year} className="card" style={{ boxShadow: 'none', padding: 14 }}>
                  <div className="row between"><b>Year {y.year}</b><span className="tiny muted">{inr(y.spend_inr)}</span></div>
                  <div className="stack" style={{ marginTop: 10, gap: 6 }}>
                    {y.items.length === 0 ? <span className="small muted">Nothing fits this year.</span> : y.items.map((it) => (
                      <div key={it.retrofit_id} className="small" style={{ background: 'var(--mint)', borderRadius: 8, padding: '6px 8px' }}>
                        <b>{it.name}</b><div className="tiny muted">{inr(it.cost_inr)} · saves {inr(it.saving_inr_year)}/yr</div>
                      </div>
                    ))}
                  </div>
                  <div className="tiny muted" style={{ marginTop: 8 }}>Saves {inr(y.saving_inr_year)}/yr · {num(y.co2_kg_year)} kg CO₂</div>
                </div>
              ))}
              <div className="card" style={{ boxShadow: 'none', padding: 14, background: 'var(--sand-2)' }}>
                <b className="small">Not scheduled</b>
                <div className="stack" style={{ marginTop: 8, gap: 4 }}>
                  {r.not_scheduled.length ? r.not_scheduled.map((x) => <span key={x} className="small">{humanize(x)}</span>) : <span className="small muted">Everything fits.</span>}
                </div>
              </div>
            </div>
            <p className="tiny muted">{r.note} Budget {inr(r.budget_per_year_inr)} per year, optimised for {obj === 'inr' ? 'bill savings' : obj === 'co2' ? 'CO₂' : 'kWh'}.</p>
          </div>
        )}
      </Q>
    </Card>
  )
}
