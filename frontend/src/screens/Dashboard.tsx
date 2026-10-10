// Screen 1: My Ghar Score. Score, why (7 weighted components), confidence, usage, next action, package potential.
import { AlertTriangle, ArrowRight, CheckCircle2, ChevronRight, CloudSun, Info, Leaf, Lightbulb, ShieldCheck, Zap } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useHome, usePlan, useScenario, useScore, useWeatherSignature } from '../api/hooks'
import type { ScoreResult, SubScore } from '../api/types'
import { HBar, MonthlyBars } from '../components/charts'
import { BandChip, Card, Drawer, Empty, Estimated, ErrorState, Loading, Q } from '../components/ui'
import { BAND_COLOR, COMPONENT_LABEL, inr, inrShort, kg, kwh, num, pct, years } from '../lib/format'
import { COMPONENT_ICON, retrofitIcon } from '../lib/icons'
import { useT } from '../lib/i18n'
import { useSession } from '../state/session'

export function Dashboard() {
  const id = useSession((s) => s.activeHomeId)!
  const user = useSession((s) => s.user)
  const forget = useSession((s) => s.forgetHome)
  const t = useT()
  const score = useScore(id)
  const home = useHome(id)
  const plan = usePlan(id)
  const pkgIds = useMemo(() => (plan.data?.recommendations ?? []).filter((r) => r.suitability !== 'Infeasible' && r.suitability !== 'Excluded').map((r) => r.retrofit_id), [plan.data])
  const pkg = useScenario(id, pkgIds, {})
  const [comp, setComp] = useState<SubScore | null>(null)
  const [dismissed, setDismissed] = useState(false)

  if (score.error instanceof ApiError && score.error.status === 404)
    return (
      <Empty title="That home isn't available any more.">
        <button className="btn primary" onClick={() => forget(id)}>Choose another home</button>
      </Empty>
    )
  const name = user?.email?.split('@')[0]
  const today = new Date().toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">{name ? `Welcome back, ${name}` : 'Welcome to your Green Ghar'}</h1>
          <p className="page-sub">Here's how your home is performing and what you can do next.</p>
        </div>
        <div className="meta-card">
          <div><div>{today}</div><div className="tiny">{home.data ? `${home.data.city}` : '…'}</div></div>
          <CloudSun size={26} color="var(--amber)" aria-hidden />
          <Link to="/garmi" className="small">Heat & your bill</Link>
        </div>
      </div>

      <div className="grid g-12">
        <Card className="span-4" title={t('yourScore')} id="score" actions={<Info size={16} className="muted" aria-hidden />}>
          <Q q={score} lines={5}>{(s) => <ScoreHero s={s} />}</Q>
        </Card>

        <Card className="span-5" title={t('breakdown')} id="breakdown">
          <Q q={score} lines={7}>
            {(s) => (
              <div role="list">
                {s.components.map((c) => {
                  const I = COMPONENT_ICON[c.component] ?? Zap
                  return (
                    <button key={c.component} role="listitem" className="comp-row" onClick={() => setComp(c)} aria-label={`${COMPONENT_LABEL[c.component] ?? c.component}: ${Math.round(c.score)} of 100, weight ${Math.round(c.weight * 100)}%`}>
                      <span className="comp-ico"><I /></span>
                      <span className="small">{COMPONENT_LABEL[c.component] ?? c.component} <span className="muted">· {Math.round(c.weight * 100)}%</span></span>
                      <HBar value={c.score} color={BAND_COLOR[c.score >= 80 ? 'Highly efficient' : c.score >= 65 ? 'Good' : c.score >= 50 ? 'Moderate' : c.score >= 30 ? 'Poor' : 'Very poor']} />
                      <b className="small" style={{ textAlign: 'right' }}><Estimated show={c.estimated}>{Math.round(c.score)}</Estimated></b>
                    </button>
                  )
                })}
                <p className="tiny muted" style={{ marginTop: 8 }}>Each bar is that part's score out of 100; the % is its fixed weight in your total. Tap a row to see why.</p>
              </div>
            )}
          </Q>
        </Card>

        <div className="span-3 stack" style={{ gap: 18 }}>
          {score.data && !dismissed && (score.data.warnings.length > 0 || score.data.confidence !== 'high') && (
            <div className="alert" role="status">
              <AlertTriangle />
              <div style={{ flex: 1 }}>
                <b className="small">{score.data.warnings[0] ?? 'Part of this score is estimated'}</b>
                <div className="tiny" style={{ marginTop: 4 }}>{score.data.warnings.slice(1).join(' ') || score.data.confidence_reasons.join(' ')}</div>
                {score.data.confidence !== 'high' && <Link to="/bill" className="tiny">Add your bills to sharpen it</Link>}
              </div>
              <button className="btn link" aria-label="Dismiss" onClick={() => setDismissed(true)}>×</button>
            </div>
          )}
          <Card title={t('nextAction')} icon={<Leaf />}>
            <Q q={plan} lines={4} empty={(p) => (p.recommendations.length ? null : <Empty title="Nothing left to recommend">Your plan constraints exclude every measure.</Empty>)}>
              {(p) => {
                const r = p.recommendations[0]
                const I = retrofitIcon(r.retrofit_id)
                return (
                  <div className="stack">
                    <div className="row"><span className="tile-ico"><I /></span><div><b>{r.name}</b><div className="tiny muted">{r.reason}</div></div></div>
                    <div className="kv">
                      <div><span className="tiny muted">Saves</span><b>{inr(r.saving_inr_year)}</b><span className="tiny muted">per year</span></div>
                      <div><span className="tiny muted">CO₂</span><b>{num(r.co2_kg_year)} kg</b><span className="tiny muted">per year</span></div>
                      <div><span className="tiny muted">Payback</span><b>{years(r.payback_years)}</b></div>
                    </div>
                    <Link className="btn primary block" to={`/studio?r=${r.retrofit_id}`}>See options & costs <ArrowRight /></Link>
                  </div>
                )
              }}
            </Q>
          </Card>
        </div>

        <Card className="span-5" title={t('usage')} icon={<Zap />} actions={<span className="tiny muted">Last 12 months</span>}>
          <Q q={home} lines={5}>
            {(h) => {
              const months = h.monthly_kwh ?? Array(12).fill(null)
              const read = months.filter((v) => v != null).length
              return (
                <div className="stack">
                  <div className="row wrap" style={{ gap: 18 }}>
                    <div><span className="num"><Estimated show={score.data?.annual_grid_kwh_estimated}>{kwh(score.data?.annual_grid_kwh)}</Estimated></span><div className="tiny muted">per year{score.data?.annual_grid_kwh_estimated ? ' (estimated)' : ''}</div></div>
                    <div><span className="num">{num(score.data?.intensity_kwh_m2)}</span><div className="tiny muted">kWh per m² per year</div></div>
                    <span className="chip grey">{read} of 12 months metered</span>
                  </div>
                  {read === 0 ? <Empty title="No meter data yet"><Link to="/bill">Add a bill photo</Link></Empty> : <MonthlyBars a={months} height={190} width={470} />}
                </div>
              )
            }}
          </Q>
        </Card>

        <WeatherCard id={id} />

        <Card className="span-3" title="Popular for homes like yours" icon={<Lightbulb />}>
          <Q q={plan} lines={4}>
            {(p) => (
              <div className="stack">
                {p.recommendations.slice(1, 4).map((r) => {
                  const I = retrofitIcon(r.retrofit_id)
                  return (
                    <Link key={r.retrofit_id} to={`/studio?r=${r.retrofit_id}`} className="list-item">
                      <span className="tile-ico" style={{ width: 38, height: 38 }}><I size={18} /></span>
                      <span style={{ flex: 1 }}><b className="small">{r.name}</b><div className="tiny muted">Save up to {inr(r.saving_inr_year)}/year</div></span>
                      <ChevronRight size={16} />
                    </Link>
                  )
                })}
                {p.recommendations.length <= 1 && <span className="small muted">No other measures fit this home right now.</span>}
              </div>
            )}
          </Q>
        </Card>

        <Card className="span-6" title="Savings potential with the full plan" icon={<CheckCircle2 />}>
          {plan.isLoading || (pkg.isLoading && pkgIds.length > 0) ? <Loading lines={4} /> : pkg.error ? <ErrorState error={pkg.error} onRetry={() => pkg.refetch()} /> : !pkg.data ? (
            <Empty title="No measures to add up yet" />
          ) : (
            <div className="stack">
              <div className="row wrap" style={{ gap: 18 }}>
                <span className="big">{inrShort(pkg.data.saving_inr_year)}</span>
                <span className="muted">per year if you do all {pkg.data.steps.length} recommended measures, in order</span>
              </div>
              <div className="stacked" role="img" aria-label="Saving by measure">
                {pkg.data.steps.filter((s) => s.saving_inr_year > 0).map((s, i) => (
                  <div key={s.retrofit_id} title={`${s.name}: ${inr(s.saving_inr_year)}`} style={{ width: `${(s.saving_inr_year / Math.max(1, pkg.data!.steps.reduce((a, x) => a + Math.max(0, x.saving_inr_year), 0))) * 100}%`, background: ['var(--green)', 'var(--leaf-2)', 'var(--sand)', '#9cc7a8', '#c9a46a', '#3f7d5a', '#e1cfae'][i % 7] }} />
                ))}
              </div>
              <div className="row wrap small" style={{ gap: 14 }}>
                {pkg.data.steps.filter((s) => s.saving_inr_year > 0).slice(0, 5).map((s) => <span key={s.retrofit_id}>{s.name}: <b>{inr(s.saving_inr_year)}</b></span>)}
              </div>
              <p className="tiny muted">Measures are applied one after another, so each saving is counted after the ones before it. Score after the plan: <b>{pkg.data.score_after}</b> ({pkg.data.band_after}).</p>
            </div>
          )}
        </Card>

        <Card className="span-6" title="Carbon impact" icon={<Leaf />}>
          {pkg.data ? (
            <div className="stack">
              <div className="row wrap" style={{ gap: 18 }}>
                <span className="big" style={{ color: pkg.data.co2_saving_kg_year < 0 ? 'var(--red)' : undefined }}>{kg(Math.abs(pkg.data.co2_saving_kg_year))} CO₂</span>
                <span className="muted">{pkg.data.co2_saving_kg_year >= 0 ? 'less per year with the full plan' : 'more per year: switching cooking to the grid adds emissions unless you add solar'}</span>
              </div>
              <div className="kv">
                <div><span className="tiny muted">Today</span><b>{kg(pkg.data.baseline.co2_kg)}</b></div>
                <div><span className="tiny muted">After the plan</span><b>{kg(pkg.data.after.co2_kg)}</b></div>
                <div><span className="tiny muted">Cut</span><b>{pct(pkg.data.baseline.co2_kg ? (100 * pkg.data.co2_saving_kg_year) / pkg.data.baseline.co2_kg : null)}</b></div>
              </div>
              <p className="tiny muted">Grid electricity at 0.727 kg CO₂/kWh (CEA), LPG and diesel backup included.</p>
            </div>
          ) : pkg.isLoading || plan.isLoading ? <Loading lines={3} /> : <Empty title="Add measures to see the carbon cut" />}
        </Card>
      </div>

      <Drawer open={!!comp} onClose={() => setComp(null)} title={comp ? COMPONENT_LABEL[comp.component] ?? comp.component : ''}>
        {comp && (
          <div className="stack">
            <div className="row"><span className="big">{Math.round(comp.score)}</span><span className="muted">/ 100 · weight {Math.round(comp.weight * 100)}% · adds {num(comp.contribution, 1)} points</span></div>
            <p>{comp.why}</p>
            {comp.estimated && <div className="alert"><Info /><span className="small">This part is estimated because some details about your home are missing.</span></div>}
            <Link className="btn primary" to="/studio" onClick={() => setComp(null)}>Find measures that improve it <ArrowRight /></Link>
          </div>
        )}
      </Drawer>
    </>
  )
}

function ScoreHero({ s }: { s: ScoreResult }) {
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className="row wrap" style={{ gap: 16 }}>
        <span className="huge" aria-label={`Score ${s.score} out of 100`}>{s.score}</span>
        <span className="muted" style={{ fontSize: 22, fontFamily: 'var(--serif)' }}>/100</span>
        <span className={`chip ${s.confidence === 'high' ? '' : s.confidence === 'medium' ? 'sand' : 'amber'}`} title={s.confidence_reasons.join(' ')}>
          <ShieldCheck /> {s.confidence[0].toUpperCase() + s.confidence.slice(1)} confidence
        </span>
      </div>
      <div className="row wrap"><BandChip band={s.band} /><span className="small muted">Raw score {num(s.raw_score, 1)}</span></div>
      {s.peer_percentile != null ? (
        <p style={{ fontSize: 16 }}>A more efficient home than {pct(s.peer_percentile)} of similar homes.</p>
      ) : (
        <p className="small muted">Bands: 80+ highly efficient, 65 good, 50 moderate, 30 poor.</p>
      )}
      <div aria-hidden style={{ position: 'relative', height: 10, borderRadius: 99, background: 'linear-gradient(90deg, var(--band-5) 0 30%, var(--band-4) 30% 50%, var(--band-3) 50% 65%, var(--band-2) 65% 80%, var(--band-1) 80%)' }}>
        <div style={{ position: 'absolute', left: `${s.score}%`, top: -4, width: 4, height: 18, marginLeft: -2, borderRadius: 2, background: 'var(--ink)' }} />
      </div>
      <div className="row between tiny muted"><span>0</span><span>30</span><span>50</span><span>65</span><span>80</span><span>100</span></div>
      <div className="stack" style={{ gap: 8, marginTop: 6, paddingTop: 14, borderTop: '1px solid var(--line)' }}>
        <b className="small">Where your points are being lost</b>
        {[...s.components].sort((a, b) => b.weight * (100 - b.score) - a.weight * (100 - a.score)).slice(0, 3).map((c) => (
          <div key={c.component} className="row between small">
            <span>{COMPONENT_LABEL[c.component] ?? c.component}</span>
            <span className="muted">{num(c.weight * (100 - c.score), 1)} of 100 pts</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function WeatherCard({ id }: { id: string }) {
  const w = useWeatherSignature(id)
  if (w.error instanceof ApiError && w.error.status === 404)
    return (
      <Card className="span-4" title="Weather signature" icon={<CloudSun />}>
        <p className="small muted">Your home needs 6 or more metered months, and the server's real-weather layer, to compare your use with actual heat.</p>
        <Link to="/garmi" className="btn ghost" style={{ marginTop: 12 }}>See heat readiness <ArrowRight /></Link>
      </Card>
    )
  return (
    <Card className="span-4" title="Weather signature" icon={<CloudSun />}>
      <Q q={w} lines={4}>
        {(d) => {
          const diff = d.weather_normalised_kwh_year ? (100 * (d.actual_kwh_last12 - d.weather_normalised_kwh_year)) / d.weather_normalised_kwh_year : 0
          return (
            <div className="stack">
              <p>Your use was <b>{pct(Math.abs(diff))} {diff >= 0 ? 'higher' : 'lower'}</b> than in a normal-weather year.</p>
              <div className="kv" style={{ gridTemplateColumns: '1fr 1fr' }}>
                <div><span className="tiny muted">Last 12 months</span><b>{kwh(d.actual_kwh_last12)}</b></div>
                <div><span className="tiny muted">Normal year</span><b>{kwh(d.weather_normalised_kwh_year)}</b></div>
              </div>
              <div className="alert green"><Leaf /><span className="small">Each hot degree-day adds about {num(d.kwh_per_cdd24, 1)} kWh (fit R² {num(d.r2, 2)}, {d.months_used} months).</span></div>
            </div>
          )
        }}
      </Q>
    </Card>
  )
}
