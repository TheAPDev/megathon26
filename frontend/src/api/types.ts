// Response and request shapes, taken from the FastAPI backend (greenghar/api/routers/*, greenghar/schemas.py)
// and verified against live responses by scripts/contract-check.mjs. Keep in sync with docs/openapi.json.

export type Band = 'Highly efficient' | 'Good' | 'Moderate' | 'Poor' | 'Very poor'
export type Confidence = 'high' | 'medium' | 'low'

export interface Home {
  home_id: string
  city: string
  dwelling_type: 'apartment' | 'independent_house' | 'row_house'
  floor_position: 'ground' | 'middle' | 'top'
  tenure: 'owner' | 'tenant'
  carpet_area_m2: number | null
  occupants: number
  building_age_years: number | null
  roof_area_m2: number | null
  roof_access: boolean
  wall_type: 'solid_brick' | 'hollow_block' | 'aac'
  window_to_wall: number
  west_glass: boolean
  shading: 'none' | 'partial' | 'full'
  cool_roof: boolean
  roof_insulation: boolean
  solar_film: boolean
  n_ac: number
  ac_tech: 'fixed' | 'inverter'
  ac_star: number
  ac_age_years: number
  ac_tonnage: number
  ac_setpoint_c: number
  n_coolers: number
  n_fans: number
  bldc_fan_share: number
  fridge_star: number
  fridge_age_years: number
  light_points: number
  led_share: number
  water_heating: 'electric_geyser' | 'solar' | 'heat_pump' | 'gas' | 'none'
  cooking: 'lpg' | 'png' | 'induction'
  lpg_cylinders_per_year: number | null
  pv_kw: number
  net_metered: boolean
  backup: 'none' | 'lead_acid' | 'lithium' | 'dg_set'
  outage_hours_month: number
  smart_meter: boolean
  tod_tariff: boolean
  smart_plugs: boolean
  bee_star_label: number | null
  sanctioned_load_kw: number
  income_band: 'low' | 'middle' | 'upper_middle' | 'high'
  wfh: boolean
  data_source: 'smart_meter' | 'bill_ocr' | 'bbps' | 'survey'
  monthly_kwh: (number | null)[] | null
  has_retrofit_history: boolean
}
export type HomeCreate = Partial<Omit<Home, 'home_id'>> & { city: string; home_id?: string }

export interface SubScore { component: string; weight: number; score: number; contribution: number; why: string; estimated: boolean }
export interface ScoreResult {
  home_id: string; score: number; band: Band; raw_score: number; components: SubScore[]
  confidence: Confidence; confidence_reasons: string[]; warnings: string[]
  annual_grid_kwh: number | null; annual_grid_kwh_estimated: boolean; intensity_kwh_m2: number | null; peer_percentile: number | null
}

export interface Recommendation {
  retrofit_id: string; name: string; category: string; order_rank: number
  suitability: 'High' | 'Medium' | 'Low' | 'Infeasible' | 'Excluded'; reason: string; over_budget?: boolean
  cost_inr_min: number; cost_inr_max: number; saving_kwh_electricity: number; saving_kwh_lpg: number
  saving_inr_year: number; co2_kg_year: number; payback_years: number | null; rank_score: number
}
export interface Plan { home_id: string; constraints: Record<string, unknown> & { exclude?: string[]; budget_inr?: number }; recommendations: Recommendation[]; estimated: boolean }

export interface ValueRange {
  available: boolean; label: string; current_value_inr?: number; current_value_range_inr?: [number, number]
  interval?: string; uplift_pct?: number; uplift_range_pct?: [number, number]; method?: string; caveat?: string
}
export interface EnergyState { grid_kwh: number; lpg_kwh: number; dg_kwh: number; annual_bill_inr: number; co2_kg: number; monthly_grid_kwh: number[]; pv_generation_kwh?: number; pv_exported_kwh?: number }
export interface ScenarioStep {
  retrofit_id: string; name: string; saving_kwh_electricity: number; saving_kwh_lpg: number; saving_kwh_dg: number
  saving_inr_year: number; co2_kg_year: number; cost_inr: [number, number]; subsidy_inr: number; net_cost_inr: [number, number]
}
export interface Scenario {
  home_id: string; estimated: boolean; baseline: EnergyState; after: EnergyState
  per_fuel_saving_kwh: { electricity: number; lpg: number; diesel: number }
  saving_inr_year: number; co2_saving_kg_year: number; improvement_potential_pct: number | null
  score_before: number; score_after: number; band_after: Band; steps: ScenarioStep[]
  refused: { retrofit_id: string; reason: string }[]; near_zero_bill: boolean; data_method: string; value: ValueRange
}
export interface ScenarioRequest { retrofits: string[]; params: Record<string, number> }

export interface Finance {
  home_id: string; estimated: boolean; retrofits: string[]; refused: { retrofit_id: string; reason: string }[]
  gross_cost_inr: number; subsidy_inr: number; net_cost_inr: number
  loans: { product: string; principal_inr: number; rate_pct: number; tenure_years: number; emi_inr: number }[]
  total_emi_inr_month: number; bill_saving_inr_month: number; emi_covered_by_saving: boolean
  simple_payback_years: number | null; savings_25yr_inr: number; co2_saving_kg_year: number
  near_zero_bill: boolean; pivot_note: string | null
  assumptions: { tariff_escalation_pct: number; pv_degradation_pct: number; rates: string }
}
export interface Solar {
  quote: { kw: number; annual_generation_kwh: number; roof_needed_m2: number; gross_cost_inr: [number, number]; central_subsidy_inr: number; state_topup_inr: number; net_cost_inr: [number, number] }
  subsidy: { eligible: boolean; why_not: string; kw: number; central_subsidy_inr: number; state_topup_inr: number; steps: string[]; documents: string[] }
}
export interface SubsidyApplication {
  portal: string; prefilled: Record<string, string | number | boolean>; to_complete_by_user: string[]; steps: string[]
  status_tracker: { step: string; done: boolean }[]
}
export interface Roadmap {
  home_id: string; budget_per_year_inr: number; objective: 'inr' | 'co2' | 'kwh'
  years: { year: number; items: { retrofit_id: string; name: string; order_rank: number; cost_inr: number; saving_inr_year: number; co2_kg_year: number; saving_kwh_electricity: number }[]; spend_inr: number; saving_inr_year: number; co2_kg_year: number }[]
  not_scheduled: string[]; note: string
}
export interface Heatwave {
  home_id: string; city: string; zone: string; summer_mean_temp_c: number; ac_hours_apr_jun: number; has_ac: boolean
  measures: { retrofit_id: string; suitability: string; indoor_peak_drop_c: [number, number]; ac_hours_avoided_apr_jun: number; cost_inr: [number, number]; reason: string }[]
  advice: string; estimated: boolean
}
export interface WeatherSignature {
  home_id: string; city: string; months_used: number; kwh_per_cdd24: number; base_kwh_per_month: number; r2: number
  actual_kwh_last12: number; weather_normalised_kwh_year: number
}
export interface CityClimate {
  check: { city: string; state: string; nbc_zone: string; engine_pv_yield: number; real_cdd24_per_year: number | null; real_heatwave_days_per_year: number | null; real_ghi_kwh_m2_year: number | null; nasa_ghi_kwh_m2_year: number | null; nasa_t2m_annual_c: number | null } | null
  monthly: { month: string; days: number; t_mean_c: number; t_max_c: number; t_min_c: number; cdd24: number; cdd18: number; heatwave_days: number; humid_heat_days: number; rh_mean_pct: number; ghi_kwh_m2: number; rain_mm: number }[]
  nasa_climatology: Record<string, Record<string, number>> | null
}

export interface MemoryItem { memory_id: string; customer_id: string; home_id: string; kind: 'constraint' | 'preference' | 'feedback'; key: string; value: string; created_month: string }
export interface Journey {
  home_id: string; customer_id: string | null
  completed_retrofits: { retrofit_id: string; month_index?: number; completed_month?: string; [k: string]: unknown }[]
  memory: MemoryItem[]; plan: Plan
}
export interface MemoryIn { kind: 'constraint' | 'preference' | 'feedback'; key: string; value: string | number | boolean }
export interface MemoryResult {
  memory_item: MemoryItem
  what_changed: { changes: { retrofit_id: string; change: string; from: unknown; to: unknown }[]; constraints_before: Record<string, unknown>; constraints_after: Record<string, unknown> }
}

export interface Grounding { total: number; verified: number; unsupported: string[]; grounded: boolean; badge: string }
export interface ChatReply {
  answer: string; language: string; provider: string; model: string | null
  tool_calls: { tool: string; args: Record<string, unknown> }[]; caveats: string[]; cited_fields: string[]
  grounding: Grounding; fallback_reason?: string; latency_s: number; usage: Record<string, number>; cached: boolean; estimated: boolean
}
export interface ChatIn { home_id: string; message: string; language?: string | null; use_llm: boolean }

export interface BillParse {
  monthly_kwh: (number | null)[]; months_found: number; warnings: string[]; provider?: string
  city?: string | null; state?: string | null; discom?: string | null; sanctioned_load_kw?: number | null
  amount_inr?: number | null; consumer_number_masked?: string | null; stored?: { storage_path: string }
}
export interface Transcript { text: string; language: string | null; provider: string }
export interface TelegramLink { token: string; expires_at: number; bot_username: string | null; deep_link: string | null }

export interface PortfolioSummary {
  homes_with_loans: number; mean_score: number | null; median_score: number | null; band_counts: Record<Band, number>
  poor_or_very_poor_share: number; score_histogram: { bin_edges: number[]; counts: number[] }
  financed_emissions_t_co2: number; financed_emissions_reduction_potential_t_co2: number
  loan_book_outstanding_cr: number; low_confidence_share: number; method: string
}
export interface PoorHome { home_id: string; customer_id: string; city: string; score: number; band: Band; key_issue: string; confidence: Confidence; warnings: string[] | string }
export interface RankedHome { home_id: string; customer_id: string; city: string; score: number; improvement_potential_pct: number; score_after_package: number; package_saving_inr_year: number; co2_saving_t_year: number; financed_co2_reduction_t_year: number; package: string[] | string }
export interface Target { customer_id: string; home_id: string; city: string; score: number; offer: string; package_saving_inr_year: number; improvement_potential_pct: number; credit_band: string; language: string }
export interface RwaLead { society_id: string; city: string; customers: number; without_private_roof: number; mean_score: number; suggested_common_solar_kw: number; rwa_subsidy_inr: number }
export interface CityPoint { city: string; state: string; lat: number; lon: number; zone: string; homes: number; mean_score: number; poor_share: number; financed_emissions_t: number; reduction_potential_t: number }

export interface City { city: string; state: string; zone: string; lat: number; lon: number; tier: number | string }
export interface Retrofit { retrofit_id: string; name: string; category: string; order_rank: number; cost_min_inr: number; cost_max_inr: number; cost_basis: string; effect_type: string; effect_value: number; lifetime_years: number; description: string }
export interface MyHome { home_id: string; city: string; dwelling_type: string }
export interface PublicConfig {
  env: string; repo: string; version: string
  auth: { supabase_url: string | null; supabase_anon_key: string | null; username_domain: string | null; required: boolean }
  telegram_bot_username: string | null; demo_home_id: string | null
}
