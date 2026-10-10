// Screen 1: My Ghar Score. Score, why (7 weighted components), confidence, usage, next action, package potential.
import { AlertTriangle, ArrowRight, BadgeIndianRupee, CheckCircle2, ChevronRight, CloudSun, Gauge, Info, Leaf, Lightbulb, Maximize2, ShieldCheck, Timer, TrendingUp, Zap } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useHome, usePlan, useScenario, useScore, useWeatherSignature } from '../api/hooks'
import type { ScoreResult, SubScore } from '../api/types'
import { MonthlyBars } from '../components/charts'
import { HouseHero } from '../components/HouseHero'
import { BandChip, Card, Drawer, Empty, Estimated, ErrorState, Loading, Q } from '../components/ui'
import { BAND_COLOR, bandOf, COMPONENT_LABEL, inr, inrShort, kg, kwh, num, pct, years } from '../lib/format'
import { retrofitIcon } from '../lib/icons'
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
  const sc = score.data
  const top = plan.data?.recommendations[0]
  const lowParts = sc ? [...sc.components].sort((x, y) => x.score - y.score) : []

  return (
    <>
      <div className="stage">
        <section className="card cond" aria-label="Your home today">
          <div className="cond-h">
            <div><h2>{name ? `Hello, ${name}` : 'Your home today'}</h2><small>{home.data ? `${home.data.city} · ${home.dataUpdatedAt ? 'updated just now' : ''}` : 'Loading…'}</small></div>
            <Link to="/bill" className="icon-btn" aria-label="Add a bill"><Maximize2 size={15} /></Link>
          </div>
          <div className="tiles">
            <div className="tile"><span>Ghar score</span><b>{sc ? Math.round(sc.score) : '–'}<small>/100</small></b></div>
            {sc?.peer_percentile != null
              ? <div className="tile"><span>Beats similar homes</span><b>{Math.round(sc.peer_percentile)}<small>%</small></b></div>
              : <div className="tile"><span>Rating</span><b style={{ fontSize: 20, lineHeight: 1.15 }}>{sc?.band ?? '–'}</b></div>}
            <div className="tile"><span>Energy intensity</span><b>{sc ? num(sc.intensity_kwh_m2) : '–'}<small>kWh/m²</small></b></div>
            <div className="tile"><span>Confidence</span><b style={{ fontSize: 24 }}>{sc ? sc.confidence[0].toUpperCase() + sc.confidence.slice(1) : '–'}</b></div>
          </div>
          <Metric icon={<Zap />} title="Grid electricity" sub={sc?.annual_grid_kwh_estimated ? 'Estimated per year' : 'Per year'} value={sc ? kwh(sc.annual_grid_kwh) : '–'} />
          <Metric icon={<BadgeIndianRupee />} title="Savings with full plan" sub="Per year" value={pkg.data ? inrShort(pkg.data.saving_inr_year) : '–'} hl />
          <Metric icon={<Leaf />} title="Carbon cut with plan" sub="Per year" value={pkg.data ? kg(Math.abs(pkg.data.co2_saving_kg_year)) : '–'} />
          <Metric icon={<TrendingUp />} title="Score after plan" sub={pkg.data?.band_after ?? 'All measures'} value={pkg.data ? String(Math.round(pkg.data.score_after)) : '–'} />
          <Metric icon={<Timer />} title="Best first step payback" sub={top?.name ?? 'Next action'} value={top ? years(top.payback_years) : '–'} />
          <div className="mini-title"><span>Monthly electricity use</span><Link to="/garmi" aria-label="Heat and your bill"><Gauge size={16} /></Link></div>
          <Q q={home} lines={3}>{(h) => <UseSteps months={h.monthly_kwh ?? []} />}</Q>
        </section>

        <div className="hero">
          <div className="hero-art"><HouseHero /></div>
          {sc && (
            <div className="hero-badge" aria-hidden>
              <div className="n">{Math.round(sc.score)}<small> /100</small></div>
              <div className="small" style={{ marginTop: 4 }}>{sc.band}</div>
            </div>
          )}
          <div className="hero-cards">
            <section className="olive" aria-labelledby="comp-h">
              <Link to="/studio" className="corner" aria-label="Open retrofit studio"><ArrowRight size={16} style={{ transform: 'rotate(-45deg)' }} /></Link>
              <h2 id="comp-h">Score parts</h2>
              <Q q={score} lines={6}>
                {(s) => (
                  <div className="cbars" role="list">
                    {s.components.map((c) => {
                      const low = c.score < 40
                      const col = BAND_COLOR[bandOf(c.score)]
                      return (
                        <button key={c.component} role="listitem" className="cbar" onClick={() => setComp(c)} aria-label={`${COMPONENT_LABEL[c.component] ?? c.component}: ${Math.round(c.score)} of 100, weight ${Math.round(c.weight * 100)}%`}>
                          <span className="v"><Estimated show={c.estimated}>{Math.round(c.score)}</Estimated></span>
                          <span className="col"><i style={{ height: `${Math.max(6, c.score)}%`, background: `linear-gradient(180deg, ${col}, color-mix(in srgb, ${col} 55%, #0a3a44))` }} />{low && <u><AlertTriangle /></u>}</span>
                          <span className="l">{SHORT[c.component] ?? (COMPONENT_LABEL[c.component] ?? c.component).split(' ')[0]}</span>
                        </button>
                      )
                    })}
                  </div>
                )}
              </Q>
            </section>

            <section className="olive" aria-labelledby="sav-h">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div><h2 id="sav-h">Savings</h2><div className="sub">{pkg.data ? `${pkg.data.steps.length} measures, applied in order` : 'Full plan'}</div></div>
                <Link to="/paisa" className="icon-btn" aria-label="Open finance" style={{ background: 'rgba(255,255,255,.14)' }}><ArrowRight size={16} /></Link>
              </div>
              <div className="trio">
                <div><b>{pkg.data ? inrShort(pkg.data.saving_inr_year) : '–'}</b><span>Per year</span></div>
                <div><b>{pkg.data ? pct(pkg.data.baseline.co2_kg ? (100 * pkg.data.co2_saving_kg_year) / pkg.data.baseline.co2_kg : null) : '–'}</b><span>Carbon cut</span></div>
                <div><b>{pkg.data ? Math.round(pkg.data.score_after) : '–'}</b><span>New score</span></div>
              </div>
              <div className="scale">
                <div className="lab"><span>Poor</span><span>Efficient</span></div>
                <div className="track"><div className="ticks" /><div className="pin" style={{ left: `${sc?.score ?? 0}%` }} /></div>
              </div>
              <p className="foot-line">{sc ? `You are at ${Math.round(sc.score)} today${pkg.data ? `; the full plan reaches ${Math.round(pkg.data.score_after)}.` : '.'}` : 'Loading your score…'}</p>
            </section>

            <section className="olive" aria-labelledby="al-h">
              <h2 id="al-h" style={{ marginBottom: 6 }}>Needs attention</h2>
              <div className="alerts">
                {sc && sc.warnings.slice(0, 1).map((w) => (
                  <Link key="w" to="/bill" className="alert-row"><span className="ic"><Info /></span><span><b>{w.length > 34 ? `${w.slice(0, 33)}…` : w}</b><small>Warning</small></span></Link>
                ))}
                {lowParts.slice(0, 3).map((c) => (
                  <button key={c.component} className="alert-row" onClick={() => setComp(c)}>
                    <span className={`ic${c.score < 40 ? ' crit' : ''}`}><AlertTriangle /></span>
                    <span><b>{COMPONENT_LABEL[c.component] ?? c.component} low</b><small>{c.score < 40 ? 'Critical' : 'Warning'} · {Math.round(c.score)}/100</small></span>
                  </button>
                ))}
                {!sc && <Loading lines={3} />}
              </div>
            </section>
          </div>
        </div>
      </div>

      <div className="grid g-12 below">
        <Card className="span-4" title={t('yourScore')} id="score" actions={<Info size={16} className="muted" aria-hidden />}>
          <Q q={score} lines={5}>{(s) => <ScoreHero s={s} />}</Q>
        </Card>

        <div className="span-4 stack" style={{ gap: 18 }}>
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

        <Card className="span-4" title="Popular for homes like yours" icon={<Lightbulb />}>
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

        <Card className="span-8" title={t('usage')} icon={<Zap />} actions={<span className="tiny muted">Last 12 months</span>}>
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
                  {read === 0 ? <Empty title="No meter data yet"><Link to="/bill">Add a bill photo</Link></Empty> : <MonthlyBars a={months} height={190} width={760} />}
                </div>
              )
            }}
          </Q>
        </Card>

        <WeatherCard id={id} />

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

const SHORT: Record<string, string> = {
  energy_efficiency: 'Efficiency', consumption_intensity: 'Intensity', envelope: 'Envelope', cooling_system: 'Cooling', windows_shading: 'Windows', renewables: 'Solar', smart_use: 'Smart',
}

function Metric({ icon, title, sub, value, hl }: { icon: ReactNode; title: string; sub: string; value: string; hl?: boolean }) {
  return (
    <div className={`metric${hl ? ' hl' : ''}`}>
      {icon}
      <span><b>{title}</b><small>{sub}</small></span>
      <em>{value}</em>
    </div>
  )
}

// Stepped, hatched area of the 12 monthly readings, like a light-exposure chart.
function UseSteps({ months }: { months: (number | null)[] }) {
  const vals = months.length ? months : Array(12).fill(null)
  const known = vals.filter((v): v is number => v != null)
  if (!known.length) return <p className="small muted">No meter data yet. <Link to="/bill">Add a bill</Link></p>
  const max = Math.max(...known) || 1
  const W = 280, H = 96, bw = W / 12
  return (
    <svg viewBox={`0 0 ${W} ${H + 22}`} width="100%" role="img" aria-label={`Monthly electricity use, peak ${num(max)} kWh`} style={{ color: 'var(--ink-3)' }}>
      <defs><pattern id="use-hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="5" height="5" fill="rgba(63,208,220,.16)" /><line x1="0" y1="0" x2="0" y2="5" stroke="rgba(63,208,220,.85)" strokeWidth="1.4" /></pattern></defs>
      {[0, 0.5, 1].map((f) => <line key={f} x1="0" x2={W} y1={H - H * f} y2={H - H * f} stroke="rgba(255,255,255,.14)" strokeDasharray="2 3" />)}
      {vals.map((v, i) => v == null ? null : <rect key={i} x={i * bw + 1} y={H - (H * v) / max} width={bw - 2} height={(H * v) / max} fill="url(#use-hatch)" stroke="rgba(63,208,220,.9)" strokeWidth="1" />)}
      {['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'].map((m, i) => <text key={i} x={i * bw + bw / 2} y={H + 15} fontSize="10" textAnchor="middle" fill="currentColor">{m}</text>)}
    </svg>
  )
}
