import { expect, test, type Page } from '@playwright/test'
import path from 'node:path'

const HOME = 'H000011'
const api = (page: Page, p: string) => page.request.get(new URL(p, page.context().pages()[0]?.url() || 'http://127.0.0.1:8765').toString())

test.beforeEach(async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (e) => errors.push(e.message))
  ;(page as unknown as { _errors: string[] })._errors = errors
})
test.afterEach(async ({ page }) => {
  expect((page as unknown as { _errors: string[] })._errors, 'no uncaught page errors').toEqual([])
})

test('dashboard shows the engine score, breakdown and next action for the demo home', async ({ page, baseURL }) => {
  const score = await (await page.request.get(new URL(`/homes/${HOME}/score`, baseURL).toString())).json()
  const plan = await (await page.request.get(new URL(`/homes/${HOME}/plan`, baseURL).toString())).json()
  await page.goto('./')
  await expect(page.getByLabel(`Score ${score.score} out of 100`)).toBeVisible()
  await expect(page.getByText(score.band, { exact: true }).first()).toBeVisible()
  for (const c of score.components) await expect(page.getByRole('listitem').filter({ hasText: String(Math.round(c.score)) }).first()).toBeVisible()
  await expect(page.getByText(plan.recommendations[0].name).first()).toBeVisible()
  // component drawer explains the sub-score
  await page.getByRole('listitem').first().click()
  await expect(page.getByRole('dialog')).toContainText(score.components[0].why)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).toBeHidden()
})

test('studio: ticking measures re-runs the engine and shows the sequential package', async ({ page, baseURL }) => {
  await page.goto('studio')
  const reqs: string[] = []
  page.on('request', (r) => r.url().includes('/scenario') && reqs.push(r.postData() ?? ''))
  await page.getByLabel('Include Cool roof coating').check()
  await page.getByLabel('Include LED lighting').check()
  await expect(page).toHaveURL(/r=cool_roof%2Cled_lighting|r=cool_roof,led_lighting/)
  const expected = await (await page.request.post(new URL(`/homes/${HOME}/scenario`, baseURL).toString(), { data: { retrofits: ['cool_roof', 'led_lighting'], params: {} } })).json()
  await expect(page.getByLabel(`Score ${expected.score_after} out of 100`)).toBeVisible()
  await expect(page.getByText(`₹${expected.saving_inr_year.toLocaleString('en-IN', { maximumFractionDigits: 0 })}`).first()).toBeVisible()
  expect(reqs.length).toBeGreaterThan(0)
  expect(JSON.parse(reqs.at(-1)!).retrofits).toEqual(['cool_roof', 'led_lighting'])
  // infeasible measures cannot be ticked
  await expect(page.getByLabel('Include Rooftop solar PV')).toBeDisabled()
})

test('studio constraints are saved to memory and can be removed', async ({ page }) => {
  await page.goto('studio')
  await page.getByRole('button', { name: 'Add constraint' }).click()
  await page.getByLabel('Constraint type').selectOption('exclude')
  await page.getByLabel('Measure to exclude').selectOption('led_lighting')
  await page.getByRole('button', { name: 'Save', exact: true }).click()
  await expect(page.getByText('No LED lighting')).toBeVisible()
  await expect(page.getByLabel('Include LED lighting')).toBeDisabled()
  await page.getByLabel('Allow LED lighting again').click()
  await expect(page.getByText('No LED lighting')).toBeHidden()
  await expect(page.getByLabel('Include LED lighting')).toBeEnabled()
})

test('paisa: finance, value, solar and roadmap come from the backend', async ({ page, baseURL }) => {
  const r = ['cool_roof', 'ac_5star_inverter', 'led_lighting']
  const fin = await (await page.request.post(new URL(`/homes/${HOME}/finance`, baseURL).toString(), { data: { retrofits: r, params: {}, down_payment_inr: 0 } })).json()
  await page.goto(`paisa?r=${r.join(',')}`)
  await expect(page.getByText(`₹${fin.total_emi_inr_month.toLocaleString('en-IN')}`).first()).toBeVisible()
  await expect(page.getByText(fin.emi_covered_by_saving ? 'Pays for itself' : /Costs ₹/).first()).toBeVisible()
  await expect(page.getByRole('cell', { name: fin.loans[0].product })).toBeVisible()
  await expect(page.getByText('Not eligible for rooftop solar subsidy')).toBeVisible() // H000011 has no private roof
  await expect(page.getByText('Year 1')).toBeVisible()
  // removing a measure refetches finance
  const wait = page.waitForResponse((x) => x.url().includes('/finance'))
  await page.getByLabel('Remove LED lighting').click()
  const body = JSON.parse((await wait).request().postData()!)
  expect(body.retrofits).toEqual(['cool_roof', 'ac_5star_inverter'])
})

test('AI Saathi answers with a verified badge, highlighted figures and the tools used', async ({ page }) => {
  await page.goto('saathi')
  await page.getByRole('button', { name: /Why is my score what it is/ }).first().click()
  const badge = page.getByRole('button', { name: /figures verified/ })
  await expect(badge).toBeVisible()
  await expect(page.locator('mark').first()).toBeVisible()
  await expect(page.getByText('Figure verification')).toBeVisible()
  await expect(page.getByText('get_score').first()).toBeVisible()
  // memory tab writes to the backend
  await page.getByRole('tab', { name: 'Memory' }).click()
  await page.getByLabel('What to remember').selectOption('budget_inr')
  await page.getByLabel('Budget in rupees').fill('150000')
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await expect(page.getByText('Saathi will remember that')).toBeVisible()
  await expect(page.getByText('₹1,50,000').first()).toBeVisible()
})

test('lender portfolio: KPIs, filters, tabs and home drawer', async ({ page, baseURL }) => {
  const s = await (await page.request.get(new URL('/portfolio/summary', baseURL).toString())).json()
  await page.goto('portfolio')
  await expect(page.getByText(s.homes_with_loans.toLocaleString('en-IN')).first()).toBeVisible()
  await page.getByLabel('City filter').selectOption('Pune')
  await expect(page).toHaveURL(/city=Pune/)
  const pune = await (await page.request.get(new URL('/portfolio/summary?city=Pune', baseURL).toString())).json()
  await expect(page.getByText(pune.homes_with_loans.toLocaleString('en-IN')).first()).toBeVisible()
  await page.getByRole('tab', { name: 'Upgrade ranking' }).click()
  await expect(page.getByRole('table')).toContainText('Pune')
  await page.getByRole('table').locator('tbody tr').first().click()
  await expect(page.getByRole('dialog')).toContainText('Projected improvement')
  await expect(page.getByRole('dialog').getByText(/Score \d+ → \d+/)).toBeVisible()
  await page.keyboard.press('Escape')
  await page.getByRole('tab', { name: 'RWA leads' }).click()
  await expect(page.getByRole('columnheader', { name: /Common solar kW/ })).toBeVisible()
  const dl = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export CSV' }).click()
  expect((await dl).suggestedFilename()).toMatch(/^greenghar_rwa_leads_\d{8}\.csv$/)
})

test('bill photo to score: OCR reads the months, the user reviews, a scored home is created', async ({ page }) => {
  await page.goto('bill')
  await page.getByLabel('Bill file').setInputFiles(path.resolve('e2e/fixtures/bill.png'))
  await expect(page.getByText('We read 8 of 12 months')).toBeVisible({ timeout: 45_000 })
  await expect(page.getByLabel('Jan units in kWh')).toHaveValue('320')
  await expect(page.getByLabel('Apr units in kWh')).toHaveValue('')
  await page.getByLabel('Apr units in kWh').fill('335')
  await page.getByRole('button', { name: 'Generate my efficiency score' }).click()
  await expect(page.getByText('Pick the city the home is in.')).toBeVisible() // validation before any request
  await page.locator('select').filter({ hasText: 'Choose your city' }).selectOption('Kolkata')
  const created = page.waitForResponse((r) => r.url().endsWith('/homes') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Generate my efficiency score' }).click()
  const home = await (await created).json()
  expect(home.home.monthly_kwh[0]).toBe(320)
  expect(home.home.monthly_kwh[3]).toBe(335)
  expect(home.home.data_source).toBe('bill_ocr')
  await expect(page).toHaveURL(/\/app\/?$/)
  await expect(page.getByLabel(`Score ${home.score.score} out of 100`)).toBeVisible()
  await expect(page.getByRole('button', { name: 'Switch home' })).toContainText('Kolkata')
})

test('manual entry works without a bill and blank months are never sent as zero', async ({ page }) => {
  await page.goto('bill')
  await page.getByRole('button', { name: /Type your units instead/ }).click()
  await page.getByLabel('Jun units in kWh').fill('410')
  await page.locator('select').filter({ hasText: 'Choose your city' }).selectOption('Jaipur')
  const created = page.waitForResponse((r) => r.url().endsWith('/homes') && r.request().method() === 'POST')
  await page.getByRole('button', { name: 'Generate my efficiency score' }).click()
  const req = JSON.parse((await created).request().postData()!)
  expect(req.monthly_kwh.filter((v: number | null) => v === null)).toHaveLength(11)
  expect(req.data_source).toBe('survey')
})

test('garmi mode shows heat measures from the engine and links into the studio', async ({ page, baseURL }) => {
  const hw = await (await page.request.get(new URL(`/homes/${HOME}/heatwave`, baseURL).toString())).json()
  await page.goto('garmi')
  await expect(page.getByText(`${hw.summer_mean_temp_c.toFixed(1)}°C`)).toBeVisible()
  await expect(page.getByText(hw.advice)).toBeVisible()
  await page.getByRole('link', { name: /Try in studio/ }).first().click()
  await expect(page).toHaveURL(/studio\?r=/)
})

test('an unknown home shows a recoverable empty state, not a crash', async ({ page }) => {
  await page.goto('./')
  await page.getByRole('button', { name: 'Switch home' }).click()
  await page.getByLabel('Home ID').fill('H999999')
  await page.getByRole('button', { name: 'Open' }).click()
  await expect(page.getByText("That home isn't available any more.")).toBeVisible()
  await page.getByRole('button', { name: 'Choose another home' }).click()
  await expect(page.getByLabel(/Score \d+ out of 100/)).toBeVisible()
})

test('mobile: navigation drawer opens and screens stay within the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('./')
  await expect(page.getByLabel(/Score \d+ out of 100/)).toBeVisible()
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  expect(overflow).toBeLessThanOrEqual(1)
  await page.getByRole('button', { name: 'Open menu' }).click()
  await page.getByRole('link', { name: 'AI Saathi' }).click()
  await expect(page).toHaveURL(/saathi/)
})

void api
