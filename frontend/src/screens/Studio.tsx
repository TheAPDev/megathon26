// Screen 2: Retrofit plan + What-If studio. Engine applies measures in interaction order; the panel shows that.
import { ArrowRight, Info, Leaf, Plus, Save, TrendingDown, Wallet, X, Zap } from 'lucide-react'
import { useMemo, useState, type FormEvent, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useAddMemory, usePlan, useRetrofits, useScenario, useScore } from '../api/hooks'
import type { Plan, Recommendation } from '../api/types'
import { Gauge, MonthlyBars, Waterfall } from '../components/charts'
import { Card, Empty, ErrorState, Loading, Q, Stepper, useDebounced, useToast } from '../components/ui'
import { describeError } from '../api/client'
import { inr, inrShort, kg, num, signed, years } from '../lib/format'
import { retrofitIcon } from '../lib/icons'
import { useSelection } from '../lib/selection'
import { useSession } from '../state/session'

export default function Studio() {
  const id = useSession((s) => s.activeHomeId)!
  const plan = usePlan(id)
  const cat = useRetrofits()
  const order = useMemo(() => Object.fromEntries((cat.data ?? []).map((r) => [r.retrofit_id, r.order_rank])), [cat.data])
  const sel = useSelection(order)
  const dSel = useDebounced(sel.selected, 250)
  const dParams = useDebounced(sel.params, 300)
  const sc = useScenario(id, dSel, dParams)
  const score = useScore(id)
  const mem = useAddMemory(id)
  const toast = useToast()
  const names = useMemo(() => Object.fromEntries((cat.data ?? []).map((r) => [r.retrofit_id, r.name])), [cat.data])

  const savePlan = () =>
    mem.mutate({ kind: 'preference', key: 'saved_plan', value: JSON.stringify(sel.selected) }, {
      onSuccess: () => toast({ kind: 'ok', title: 'Plan saved', body: 'AI Saathi will use it when you ask for advice.' }),
      onError: (e) => toast({ kind: 'error', title: 'Could not save the plan', body: describeError(e) }),
    })

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Retrofit plan & what-if studio</h1>
          <p className="page-sub">Build a package that works for your home and budget.</p>
        </div>
      </div>
      {plan.data && <Constraints plan={plan.data} names={names} />}

      <div className="grid g-12">
        <Card className="span-6" title="Choose upgrades" serif actions={<span className="small muted">{sel.selected.length} selected</span>}>
          <Q q={plan} lines={8} empty={(p) => (p.recommendations.length ? null : <Empty title="Nothing to recommend">Every measure is done or excluded.</Empty>)}>
            {(p) => (
              <div className="stack">
                {p.recommendations.map((r) => <RecRow key={r.retrofit_id} r={r} checked={sel.selected.includes(r.retrofit_id)} onToggle={() => sel.toggle(r.retrofit_id)} />)}
              </div>
            )}
          </Q>
        </Card>

        <Card className="span-6 sticky-panel" title="Your package, in real numbers" serif
          actions={<span className={`chip ${sc.isFetching ? 'sand' : ''}`} aria-live="polite">{sc.isFetching ? 'Calculating…' : 'Live estimate'}</span>}>
          {sel.selected.length === 0 ? (
            <div className="stack">
              <div className="row" style={{ justifyContent: 'center', gap: 28 }}>
                {score.data && <div className="stack" style={{ alignItems: 'center' }}><span className="small muted">Today</span><Gauge score={score.data.score} size={140} /></div>}
              </div>
              <Empty title="Pick a measure to see the change">Tick any upgrade on the left. The engine recalculates your score, bill and CO₂ in a fraction of a second.</Empty>
            </div>
          ) : sc.isLoading ? <Loading lines={8} /> : sc.error && !sc.data ? <ErrorState error={sc.error} onRetry={() => sc.refetch()} /> : sc.data && (
            <div className="stack" style={{ gap: 16, opacity: sc.isFetching ? 0.6 : 1, transition: 'opacity .15s' }}>
              <div className="row" style={{ justifyContent: 'center', gap: 28, flexWrap: 'wrap' }}>
                <div className="stack" style={{ alignItems: 'center', gap: 4 }}><span className="small muted">Before</span><Gauge score={sc.data.score_before} size={132} color="var(--sand)" /></div>
                <div className="stack" style={{ alignItems: 'center', gap: 2 }}><span className="small">Green Ghar Score</span><ArrowRight /></div>
                <div className="stack" style={{ alignItems: 'center', gap: 4 }}><span className="small muted">After ({sc.data.band_after})</span><Gauge score={sc.data.score_after} size={132} /></div>
              </div>
              <Tiles s={sc.data} />
              {sc.data.near_zero_bill && <div className="alert green"><Info /><span className="small">Your bill is already near zero, so further measures pay back through CO₂ and comfort rather than money.</span></div>}
              {sc.data.refused.length > 0 && (
                <div className="alert" role="status">
                  <Info />
                  <div className="small">{sc.data.refused.map((r) => <div key={r.retrofit_id}><b>{names[r.retrofit_id] ?? r.retrofit_id}</b> was left out: {r.reason}</div>)}</div>
                </div>
              )}
              <div>
                <div className="row between"><b>How the upgrades work together</b><span className="tiny muted">Electricity, kWh per year</span></div>
                <Waterfall start={sc.data.baseline.grid_kwh} end={sc.data.after.grid_kwh} unit="kWh" startLabel="Current home" endLabel="With this plan"
                  steps={sc.data.steps.map((s) => ({ label: s.name, delta: -s.saving_kwh_electricity }))} />
                <p className="tiny muted">Applied in this order because each step changes what the next one can save, so the total is less than the parts added up.</p>
              </div>
              <div>
                <b>Monthly electricity use</b>
                <MonthlyBars a={sc.data.baseline.monthly_grid_kwh} b={sc.data.after.monthly_grid_kwh} height={190} width={560} />
              </div>
              <Params sel={sel} />
              {sc.data.value.available && sc.data.value.uplift_pct != null && (
                <div className="alert green"><Leaf /><span className="small">Estimated property value uplift <b>{signed(sc.data.value.uplift_pct, 1)}%</b>
                  {sc.data.value.uplift_range_pct && <> (range {num(sc.data.value.uplift_range_pct[0], 1)}–{num(sc.data.value.uplift_range_pct[1], 1)}%)</>}. {sc.data.value.caveat}</span></div>
              )}
              <div className="row wrap" style={{ justifyContent: 'flex-end' }}>
                <Link className="btn ghost" to={`/paisa?${sel.qs}`}><Wallet /> Finance this package</Link>
                <button className="btn primary" onClick={savePlan} disabled={mem.isPending}><Save /> Save as my plan</button>
              </div>
              {sc.data.estimated && <p className="tiny muted">Figures are estimates from your home's details, bills and city climate.</p>}
            </div>
          )}
        </Card>
      </div>
    </>
  )
}

function RecRow({ r, checked, onToggle }: { r: Recommendation; checked: boolean; onToggle: () => void }) {
  const I = retrofitIcon(r.retrofit_id)
  const blocked = r.suitability === 'Infeasible' || r.suitability === 'Excluded'
  const chip = r.suitability === 'High' ? <span className="chip">Recommended</span> : r.suitability === 'Medium' ? <span className="chip sand">Good fit</span>
    : r.suitability === 'Low' ? <span className="chip grey">Small gain</span> : <span className="chip outline">{r.suitability === 'Excluded' ? 'Excluded by you' : 'Not possible here'}</span>
  return (
    <label className="list-item" style={{ alignItems: 'flex-start', opacity: blocked ? 0.65 : 1, cursor: blocked ? 'default' : 'pointer', borderColor: checked ? 'var(--leaf)' : undefined }}>
      <input type="checkbox" checked={checked} onChange={onToggle} disabled={blocked && !checked} aria-label={`Include ${r.name}`} style={{ marginTop: 4 }} />
      <span className="tile-ico"><I /></span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span className="row wrap" style={{ gap: 8 }}><b>{r.name}</b>{chip}{r.over_budget && <span className="chip amber">Over budget</span>}</span>
        <span className="tiny muted" style={{ display: 'block', margin: '2px 0 8px' }}>{r.reason}</span>
        {!blocked && (
          <span className="kv rec-kv">
            <span><span className="tiny muted">Cost (installed)</span><b className="small" style={{ display: 'block' }}>{inrShort(r.cost_inr_min)}–{inrShort(r.cost_inr_max)}</b></span>
            <span><span className="tiny muted">Saves / year</span><b className="small" style={{ display: 'block' }}>{inr(r.saving_inr_year)}</b></span>
            <span><span className="tiny muted">Payback</span><b className="small" style={{ display: 'block' }}>{years(r.payback_years)}</b></span>
            <span><span className="tiny muted">CO₂</span><b className="small" style={{ display: 'block' }}>{num(r.co2_kg_year)} kg/yr</b></span>
          </span>
        )}
      </span>
    </label>
  )
}

function Tiles({ s }: { s: NonNullable<ReturnType<typeof useScenario>['data']> }) {
  const elec = s.baseline.grid_kwh ? (100 * (s.after.grid_kwh - s.baseline.grid_kwh)) / s.baseline.grid_kwh : 0
  const lo = s.steps.reduce((a, x) => a + x.net_cost_inr[0], 0)
  const hi = s.steps.reduce((a, x) => a + x.net_cost_inr[1], 0)
  const co2Up = s.co2_saving_kg_year < 0
  return (
    <div className="grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(118px, 1fr))', gap: 10 }}>
      <Tile icon={<Wallet />} value={inr(s.saving_inr_year)} label="Annual savings" />
      <Tile icon={<Zap />} value={`${signed(elec)}%`} label="Electricity use" />
      <Tile icon={<Leaf />} value={`${co2Up ? '+' : '−'}${kg(Math.abs(s.co2_saving_kg_year))}`} label={co2Up ? 'CO₂ rises: add solar to offset' : 'CO₂ per year'} warn={co2Up} />
      <Tile icon={<TrendingDown />} value={lo === hi ? inrShort(lo) : `${inrShort(lo)}–${inrShort(hi)}`} label="Upfront cost after subsidy" />
    </div>
  )
}
function Tile({ icon, value, label, warn }: { icon: ReactNode; value: string; label: string; warn?: boolean }) {
  return (
    <div className="card" style={{ padding: 12, boxShadow: 'none', display: 'flex', gap: 10, alignItems: 'center', background: warn ? 'var(--amber-bg)' : undefined }}>
      <span style={{ color: warn ? 'var(--amber)' : 'var(--green)' }}>{icon}</span>
      <span><b style={{ fontSize: 17, display: 'block' }}>{value}</b><span className="tiny muted">{label}</span></span>
    </div>
  )
}

function Params({ sel }: { sel: ReturnType<typeof useSelection> }) {
  const hasSp = sel.selected.includes('ac_setpoint')
  const hasPv = sel.selected.includes('rooftop_solar')
  if (!hasSp && !hasPv) return null
  return (
    <div className="card" style={{ boxShadow: 'none', background: 'var(--mint-2)' }}>
      <b className="small">Try a different scenario</b>
      <div className="row wrap" style={{ gap: 24, marginTop: 10 }}>
        {hasSp && (
          <label className="field" style={{ flex: 1, minWidth: 220 }}>
            AC set-point: <b>{sel.setpoint ?? 24}°C</b>
            <input type="range" min={22} max={28} step={1} value={sel.setpoint ?? 24} onChange={(e) => sel.setSetpoint(Number(e.target.value))} aria-label="AC set-point in °C" />
            <span className="row between tiny muted"><span>22°C</span><span>28°C</span></span>
          </label>
        )}
        {hasPv && (
          <div className="field">PV solar size
            <Stepper label="Solar size in kW" value={sel.pvKw ?? 3} min={1} max={10} step={0.5} format={(v) => `${num(v, 1)} kW`} onChange={(v) => sel.setPvKw(v)} />
          </div>
        )}
      </div>
    </div>
  )
}

function Constraints({ plan, names }: { plan: Plan; names: Record<string, string> }) {
  const id = useSession((s) => s.activeHomeId)!
  const mem = useAddMemory(id)
  const toast = useToast()
  const [adding, setAdding] = useState(false)
  const [kind, setKind] = useState<'budget' | 'exclude' | 'tenure'>('budget')
  const [val, setVal] = useState('')
  const c = plan.constraints
  const add = (key: string, value: string | number, done?: string) =>
    mem.mutate({ kind: 'constraint', key, value }, {
      onSuccess: (r) => {
        const n = r.what_changed.changes.length
        toast({ kind: 'ok', title: done ?? 'Constraint saved', body: n ? `${n} recommendation${n > 1 ? 's' : ''} changed.` : 'Your plan stays the same.' })
        setAdding(false)
        setVal('')
      },
      onError: (e) => toast({ kind: 'error', title: 'Could not save', body: describeError(e) }),
    })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (kind === 'budget') {
      const n = Number(val.replace(/[^\d]/g, ''))
      if (n >= 1000) add('budget_inr', n)
    } else if (kind === 'exclude' && val) add('exclude', val)
    else if (kind === 'tenure') add('tenure', 'renting')
  }
  return (
    <div className="row wrap" style={{ gap: 8 }}>
      <span className="small muted">Your constraints:</span>
      {c.tenure === 'renting' && <span className="chip sand">I rent this home<button aria-label="Remove renting constraint" onClick={() => add('tenure', 'owning', 'Constraint removed')}><X size={14} /></button></span>}
      {typeof c.budget_inr === 'number' && <span className="chip sand">Budget: {inr(c.budget_inr)}<button aria-label="Remove budget" onClick={() => add('budget_inr', 0, 'Budget removed')}><X size={14} /></button></span>}
      {(c.exclude ?? []).map((x) => <span key={x} className="chip sand">No {names[x] ?? x}<button aria-label={`Allow ${names[x] ?? x} again`} onClick={() => add('include', x, 'Constraint removed')}><X size={14} /></button></span>)}
      {!adding ? (
        <button className="chip outline" style={{ cursor: 'pointer' }} onClick={() => setAdding(true)}><Plus /> Add constraint</button>
      ) : (
        <form className="row wrap" onSubmit={submit} style={{ gap: 8 }}>
          <select className="input" style={{ width: 'auto' }} value={kind} onChange={(e) => setKind(e.target.value as typeof kind)} aria-label="Constraint type">
            <option value="budget">Budget limit</option>
            <option value="exclude">Don't suggest…</option>
            <option value="tenure">I rent this home</option>
          </select>
          {kind === 'budget' && <input className="input" style={{ width: 140 }} inputMode="numeric" placeholder="₹ 2,00,000" value={val} onChange={(e) => setVal(e.target.value)} aria-label="Budget in rupees" />}
          {kind === 'exclude' && (
            <select className="input" style={{ width: 'auto' }} value={val} onChange={(e) => setVal(e.target.value)} aria-label="Measure to exclude">
              <option value="">Choose a measure</option>
              {plan.recommendations.map((r) => <option key={r.retrofit_id} value={r.retrofit_id}>{r.name}</option>)}
            </select>
          )}
          <button className="btn primary" disabled={mem.isPending || (kind !== 'tenure' && !val)}>Save</button>
          <button type="button" className="btn ghost" onClick={() => setAdding(false)}>Cancel</button>
        </form>
      )}
      {mem.isPending && <span className="small muted">Saving…</span>}
    </div>
  )
}
