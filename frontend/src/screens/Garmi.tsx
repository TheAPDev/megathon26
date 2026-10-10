// Differentiator 3: real-weather heatwave readiness. Judges the home against the weather it actually lived
// through (Open-Meteo/ERA5 daily data loaded in the database), not a climate average.
import { AlertTriangle, ArrowRight, Flame, Info, Snowflake, Sun, Thermometer, Zap } from 'lucide-react'
import { Link } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useHeatwave, useHome, useRealCity, useRetrofits, useWeatherSignature } from '../api/hooks'
import { HeatLine, MonthlyBars, heatColor } from '../components/charts'
import { Card, Empty, Q } from '../components/ui'
import { MONTHS, humanize, inrRange, kwh, num, pct } from '../lib/format'
import { retrofitIcon } from '../lib/icons'
import { useSession } from '../state/session'

export default function Garmi() {
  const id = useSession((s) => s.activeHomeId)!
  const home = useHome(id)
  const hw = useHeatwave(id)
  const sig = useWeatherSignature(id)
  const city = useRealCity(home.data?.city)
  const cat = useRetrofits()
  const names = Object.fromEntries((cat.data ?? []).map((r) => [r.retrofit_id, r.name]))
  const realMissing = city.error instanceof ApiError && city.error.status === 404
  const monthly = city.data?.monthly ?? []
  const latest = monthly.at(-1)
  const hot = !!latest && (latest.heatwave_days >= 3 || latest.humid_heat_days >= 10 || (latest.t_max_c ?? 0) >= 40)
  const label = (m: string) => `${MONTHS[Number(m.slice(5, 7)) - 1]} ${m.slice(2, 4)}`
  const longLabel = (m: string) => `${MONTHS[Number(m.slice(5, 7)) - 1]} ${m.slice(0, 4)}`

  // Home readings are calendar Jan..Dec for the last 12 billing months (Oct 2025 - Sep 2026).
  const homeFor = (m: string) => (m >= '2025-10' ? home.data?.monthly_kwh?.[Number(m.slice(5, 7)) - 1] ?? null : null)

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title"><Sun size={30} color="var(--amber)" style={{ verticalAlign: -3 }} /> Garmi mode</h1>
          <p className="page-sub">Stay cooler, use less, and be ready for heatwaves.</p>
        </div>
      </div>
      {latest && (
        <div className={`alert ${hot ? '' : 'green'}`} role="status">
          {hot ? <AlertTriangle /> : <Info />}
          <div><b>{hot ? `Heat stress in ${home.data?.city} in ${longLabel(latest.month.slice(0, 7))}` : `A mild month in ${home.data?.city}: ${longLabel(latest.month.slice(0, 7))}`}</b>
            <div className="small">{latest.heatwave_days} day(s) at 40 °C or more, hottest {num(latest.t_max_c, 1)} °C, {latest.humid_heat_days} humid-heat day(s). Source: Open-Meteo / ERA5 daily weather.</div></div>
        </div>
      )}

      <div className="grid g-12">
        <Card className="span-4" title="Your summer at a glance" icon={<Thermometer />}>
          <Q q={hw} lines={4}>
            {(h) => (
              <div className="stack">
                <div className="row" style={{ gap: 14 }}><span className="big">{num(h.summer_mean_temp_c, 1)}°C</span><span className="small muted">average April–June temperature in {h.city} ({humanize(h.zone)} zone)</span></div>
                <div className="kv" style={{ gridTemplateColumns: '1fr 1fr' }}>
                  <div><span className="tiny muted">AC hours, Apr–Jun</span><b>{h.has_ac ? num(h.ac_hours_apr_jun) : 'No AC'}</b></div>
                  <div><span className="tiny muted">Real heatwave days / yr</span><b>{city.data?.check?.real_heatwave_days_per_year != null ? num(city.data.check.real_heatwave_days_per_year, 1) : '–'}</b></div>
                </div>
              </div>
            )}
          </Q>
        </Card>

        <Card className="span-5" title="Weather-adjusted energy use" icon={<Zap />}>
          {sig.error instanceof ApiError && sig.error.status === 404 ? (
            <p className="small muted">Needs 6 or more metered months and the server's real-weather layer to compare your use against the actual weather.</p>
          ) : (
            <Q q={sig} lines={3}>
              {(s) => {
                const d = s.weather_normalised_kwh_year ? (100 * (s.actual_kwh_last12 - s.weather_normalised_kwh_year)) / s.weather_normalised_kwh_year : 0
                return (
                  <div className="row wrap" style={{ gap: 18 }}>
                    <div><span className="tiny muted">Actual, last 12 months</span><div className="num">{kwh(s.actual_kwh_last12)}</div></div>
                    <div><span className="tiny muted">In a normal-weather year</span><div className="num">{kwh(s.weather_normalised_kwh_year)}</div></div>
                    <div className={`alert ${d > 0 ? '' : 'green'}`} style={{ padding: 10 }}><b>{d >= 0 ? '+' : '−'}{pct(Math.abs(d))}</b><span className="small">{d >= 0 ? 'above' : 'below'} weather-normal</span></div>
                  </div>
                )
              }}
            </Q>
          )}
        </Card>

        <Card className="span-3" title="How heat affects your home" icon={<Flame />}>
          {sig.data ? (
            <div className="stack">
              <span className="small">Each hot degree-day adds about</span>
              <span className="big">{num(sig.data.kwh_per_cdd24, 1)} kWh</span>
              <span className="small muted">{sig.data.r2 >= 0.6 ? 'Strong' : sig.data.r2 >= 0.3 ? 'Moderate' : 'Weak'} link between heat and your bill (R² {num(sig.data.r2, 2)} over {sig.data.months_used} months).</span>
            </div>
          ) : <p className="small muted">Shown when your home has a weather signature.</p>}
        </Card>

        <Card className="span-12" title={realMissing ? 'Your monthly electricity use' : 'Cooling demand vs your electricity use (Oct 2024 – Sep 2026)'} icon={<Sun />}>
          {realMissing ? (
            <>
              <p className="small muted" style={{ marginBottom: 10 }}>Real weather for your city is served from the database layer (GG_REPO=supabase). Showing your metered months only.</p>
              <MonthlyBars a={home.data?.monthly_kwh ?? Array(12).fill(null)} width={1100} height={240} />
            </>
          ) : (
            <Q q={city} lines={5} empty={(c) => (c.monthly.length ? null : <Empty title="No weather data for this city yet" />)}>
              {(c) => (
                <>
                  <HeatLine months={c.monthly.map((m) => label(m.month.slice(0, 7)))} heat={c.monthly.map((m) => m.cdd24)} heatTitle={(i) => `${num(c.monthly[i].cdd24)} degree-days above 24 °C, ${c.monthly[i].heatwave_days} heatwave and ${c.monthly[i].humid_heat_days} humid-heat days`} values={c.monthly.map((m) => homeFor(m.month.slice(0, 7)))} />
                  <div className="legend" style={{ marginTop: 6 }}>
                    {['Mild', 'Warm', 'Hot', 'Very hot'].map((l, i) => <span key={l}><i style={{ background: heatColor(i / 3) }} />{l}</span>)}
                    <span className="muted">(cooling degree-days above 24 °C)</span>
                    <span><i style={{ background: 'var(--leaf)' }} />Your electricity use (kWh)</span>
                  </div>
                </>
              )}
            </Q>
          )}
        </Card>

        <Card className="span-8" title="Top passive measures for heatwave readiness" icon={<Snowflake />}>
          <Q q={hw} lines={4} empty={(h) => (h.measures.length ? null : <Empty title="No passive measures apply">Your home already has them, or they don't fit (e.g. no exposed roof).</Empty>)}>
            {(h) => (
              <div className="stack">
                {[...h.measures].sort((a, b) => b.ac_hours_avoided_apr_jun - a.ac_hours_avoided_apr_jun).map((m, i) => {
                  const I = retrofitIcon(m.retrofit_id)
                  return (
                    <div key={m.retrofit_id} className="list-item" style={{ flexWrap: 'wrap' }}>
                      <span className="chip grey">{i + 1}</span>
                      <span className="tile-ico"><I /></span>
                      <span style={{ flex: '1 1 200px' }}><b>{names[m.retrofit_id] ?? humanize(m.retrofit_id)}</b><div className="tiny muted">{m.reason}</div></span>
                      <span className="chip"><Thermometer />{num(m.indoor_peak_drop_c[0], 1)}–{num(m.indoor_peak_drop_c[1], 1)} °C cooler at peak</span>
                      <span className="small" style={{ minWidth: 120 }}><span className="tiny muted">AC hours avoided</span><b style={{ display: 'block' }}>{h.has_ac ? `${num(m.ac_hours_avoided_apr_jun)} hrs` : '–'}</b></span>
                      <span className="small" style={{ minWidth: 150 }}><span className="tiny muted">Estimated cost</span><b style={{ display: 'block' }}>{inrRange(m.cost_inr)}</b></span>
                      <Link className="btn ghost" to={`/studio?r=${m.retrofit_id}`}>Try in studio <ArrowRight /></Link>
                    </div>
                  )
                })}
              </div>
            )}
          </Q>
        </Card>
        <Card className="span-4" title="Advice for your home" icon={<Info />}>
          <Q q={hw} lines={3}>{(h) => <p>{h.advice}</p>}</Q>
          {city.data?.check && (
            <p className="tiny muted" style={{ marginTop: 12 }}>
              Real cooling load in {city.data.check.city}: {num(city.data.check.real_cdd24_per_year)} degree-days a year above 24 °C. Sunlight {num(city.data.check.real_ghi_kwh_m2_year)} kWh/m² a year (NASA POWER: {num(city.data.check.nasa_ghi_kwh_m2_year)}).
            </p>
          )}
        </Card>
      </div>
    </>
  )
}
