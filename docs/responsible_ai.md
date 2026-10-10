# Responsible AI note

**Privacy (DPDP Act 2023)**
- All development data is synthetic.
- In production, energy data is processed only with explicit, purpose-limited consent (`customers.consent_energy_data`). Marketing lists use only `consent_marketing = true` customers.
- Bill images are stored under service-role-only tables, and consumer numbers are masked on parse.
- No usage data is sold or shared.

**Explainability**
- Every score comes with a waterfall of 7 weighted contributions and a plain-language "why" for each.
- Every rupee or kWh figure traces to an engine field, and LightGBM SHAP drivers appear in the Model Lab.

**Hallucination controls**
- The LLM only narrates. A numeric verifier checks every figure against tool JSON and falls back to deterministic templates.
- A "Grounded ✓ n/n" badge is shown on every reply.
- Infeasible retrofits are refused with a reason and never given a number.

**Honest uncertainty**
- A data-confidence badge (high / medium / low) is shown with its reasons.
- Estimates are always labelled.
- Value is a range, marked "indicative, not proven causal", or "unavailable" when information is missing.
- There is no guarantee language anywhere.

**Bias checks**
- Scores use intensity (kWh/m²) normalised by NBC climate zone and dwelling type, so large homes and hot cities aren't penalised for size or climate.
- `scripts/bias_report.py` reports score distributions and model errors by zone, dwelling type, tenure and income band. Rerun it after each retrain.

**Fairness of advice**
- Tenants get tenant-feasible advice: AC, fans, fridge, set-points and society solar. They are never told to insulate a roof they don't control.
- Free-units states pivot the advice to comfort, backup and export income instead of overstating bill savings.

**Human oversight**
- Financial actions (loans, top-ups) are suggestions; credit decisions stay with the lender's existing underwriting.
- An adviser handoff is offered for loans and installs, and installers must be MNRE-registered.

**Honest physics**
- LPG to induction is shown as *raising* CO₂ on today's grid unless it is paired with solar, even though that makes the recommendation less flattering.
