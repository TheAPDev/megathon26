// Contract check: call every endpoint the web app uses on a running backend and verify the fields the UI reads.
// Usage: node scripts/contract-check.mjs [http://127.0.0.1:8000]
const base = process.argv[2] ?? process.env.API ?? 'http://127.0.0.1:8000'
const H = process.env.HOME_ID ?? 'H000011'
const R = ['cool_roof', 'led_lighting']
const checks = [
  ['GET', '/config', null, ['env', 'auth.supabase_url', 'telegram_bot_username', 'demo_home_id']],
  ['GET', '/reference/cities', null, ['0.city', '0.state', '0.lat', '0.lon']],
  ['GET', '/reference/retrofits', null, ['0.retrofit_id', '0.name', '0.order_rank']],
  ['GET', '/homes', null, []],
  ['GET', `/homes/${H}`, null, ['home_id', 'city', 'dwelling_type', 'monthly_kwh']],
  ['GET', `/homes/${H}/score`, null, ['score', 'band', 'raw_score', 'components.0.component', 'components.0.weight', 'components.0.why', 'confidence', 'confidence_reasons', 'warnings', 'annual_grid_kwh', 'intensity_kwh_m2']],
  ['GET', `/homes/${H}/plan`, null, ['constraints.exclude', 'recommendations.0.retrofit_id', 'recommendations.0.suitability', 'recommendations.0.cost_inr_min', 'recommendations.0.payback_years']],
  ['POST', `/homes/${H}/scenario`, { retrofits: R, params: {} }, ['score_before', 'score_after', 'band_after', 'saving_inr_year', 'co2_saving_kg_year', 'baseline.grid_kwh', 'baseline.monthly_grid_kwh', 'after.grid_kwh', 'steps.0.saving_kwh_electricity', 'steps.0.net_cost_inr', 'refused', 'value.available']],
  ['GET', `/homes/${H}/value?retrofits=cool_roof`, null, ['available', 'label']],
  ['POST', `/homes/${H}/finance`, { retrofits: R, params: {}, down_payment_inr: 0 }, ['gross_cost_inr', 'subsidy_inr', 'net_cost_inr', 'loans.0.product', 'loans.0.principal_inr', 'loans.0.emi_inr', 'total_emi_inr_month', 'bill_saving_inr_month', 'emi_covered_by_saving', 'savings_25yr_inr', 'assumptions.rates']],
  ['GET', `/homes/${H}/solar`, null, ['quote.kw', 'quote.annual_generation_kwh', 'quote.gross_cost_inr', 'subsidy.eligible', 'subsidy.steps', 'subsidy.documents']],
  ['GET', `/homes/${H}/roadmap?budget_inr=40000&years=3&objective=inr`, null, ['years.0.items', 'years.0.spend_inr', 'not_scheduled', 'note']],
  ['GET', `/homes/${H}/heatwave`, null, ['summer_mean_temp_c', 'ac_hours_apr_jun', 'measures.0.indoor_peak_drop_c', 'measures.0.ac_hours_avoided_apr_jun', 'advice']],
  ['GET', `/homes/${H}/journey`, null, ['memory', 'completed_retrofits', 'plan.recommendations']],
  ['POST', '/advisor/chat', { home_id: H, message: 'why is my score low?', use_llm: false }, ['answer', 'language', 'provider', 'tool_calls.0.tool', 'grounding.badge', 'grounding.unsupported', 'grounding.verified', 'grounding.total']],
  ['POST', `/homes/${H}/telegram-link`, null, ['token', 'expires_at']],
  ['GET', '/portfolio/summary', null, ['homes_with_loans', 'band_counts.Poor', 'score_histogram.bin_edges', 'financed_emissions_t_co2', 'loan_book_outstanding_cr', 'low_confidence_share', 'method']],
  ['GET', '/portfolio/map', null, ['0.city', '0.lat', '0.lon', '0.mean_score', '0.financed_emissions_t']],
  ['GET', '/portfolio/poor-homes?limit=2', null, ['0.home_id', '0.customer_id', '0.score', '0.band', '0.key_issue', '0.confidence']],
  ['GET', '/portfolio/ranking?limit=2', null, ['0.home_id', '0.score_after_package', '0.improvement_potential_pct', '0.package']],
  ['GET', '/portfolio/targets?limit=2', null, ['0.customer_id', '0.offer', '0.credit_band']],
  ['GET', '/portfolio/rwa-leads?limit=2', null, ['0.society_id', '0.suggested_common_solar_kw', '0.rwa_subsidy_inr']],
  ['GET', '/reference/real/sources', null, ['0.source_id']],
]
const get = (o, p) => p.split('.').reduce((a, k) => (a == null ? undefined : a[k]), o)
let bad = 0
for (const [m, p, body, keys] of checks) {
  const r = await fetch(base + p, { method: m, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body ? JSON.stringify(body) : undefined })
  const j = await r.json().catch(() => null)
  const missing = r.ok ? keys.filter((k) => get(j, k) === undefined) : keys
  if (!r.ok || missing.length) bad++
  console.log(`${r.ok && !missing.length ? 'ok  ' : 'FAIL'} ${m} ${p} ${r.status}${missing.length ? ` missing: ${missing.join(', ')}` : ''}`)
}
console.log(bad ? `${bad} endpoint(s) broke the contract` : `all ${checks.length} endpoints match the UI contract`)
process.exit(bad ? 1 : 0)
