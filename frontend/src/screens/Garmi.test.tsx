// Garmi mode with the real-weather layer (GG_REPO=supabase). The local backend has no real weather, so this test
// feeds the screen the exact payloads the Supabase RPCs return (fixture captured from the live project).
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import fx from '../test-fixtures/real-weather-chennai.json'
import { ToastProvider } from '../components/ui'
import { useSession } from '../state/session'
import Garmi from './Garmi'

const home = { home_id: 'HD000015', city: 'Chennai', dwelling_type: 'apartment', monthly_kwh: [120, 110, 130, 150, 170, 160, 150, 140, 135, 125, null, 120] }
const heatwave = {
  home_id: 'HD000015', city: 'Chennai', zone: 'warm_humid', summer_mean_temp_c: 31.9, ac_hours_apr_jun: 2045, has_ac: true, estimated: true,
  advice: 'Do roof and shading work before May; set ACs to 24 C or higher.',
  measures: [{ retrofit_id: 'cool_roof', suitability: 'High', indoor_peak_drop_c: [1.5, 3.5], ac_hours_avoided_apr_jun: 307, cost_inr: [38200, 76400], reason: 'Well suited to the warm-humid climate zone.' }],
}
const routes: Record<string, unknown> = {
  '/homes/HD000015': home,
  '/homes/HD000015/heatwave': heatwave,
  '/homes/HD000015/weather-signature': fx.signature,
  '/reference/real/city/Chennai': fx.city,
  '/reference/retrofits': [{ retrofit_id: 'cool_roof', name: 'Cool roof coating', order_rank: 1 }],
}

beforeEach(() => {
  useSession.setState({ activeHomeId: 'HD000015' })
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = new URL(url, 'http://x').pathname
    const body = routes[path]
    return new Response(JSON.stringify(body ?? { error: { code: 'not_found', message: path } }), { status: body ? 200 : 404, headers: { 'Content-Type': 'application/json' } })
  }))
})
afterEach(() => vi.unstubAllGlobals())

test('renders real cooling demand for 24 billing months, the weather-normalised comparison and passive measures', async () => {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ToastProvider><MemoryRouter><Garmi /></MemoryRouter></ToastProvider>
    </QueryClientProvider>,
  )
  expect(await screen.findByText('Cooling demand vs your electricity use (Oct 2024 – Sep 2026)')).toBeInTheDocument()
  expect(await screen.findAllByTestId('heat-cell')).toHaveLength(24)
  // latest month (Sep 2026) had 13 humid-heat days -> heat-stress banner
  expect(screen.getByText('Heat stress in Chennai in Sep 2026')).toBeInTheDocument()
  // weather-normalised: 1,528 actual vs 1,800 normal = 15% below
  const card = screen.getByText('Weather-adjusted energy use').closest('section')!
  expect(within(card).getByText('1,528 kWh')).toBeInTheDocument()
  expect(within(card).getByText('1,800 kWh')).toBeInTheDocument()
  expect(within(card).getByText('−15%')).toBeInTheDocument()
  // weak fit is labelled honestly
  expect(screen.getByText(/Weak link between heat and your bill/)).toBeInTheDocument()
  expect(screen.getByText('Cool roof coating')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Try in studio/ })).toHaveAttribute('href', '/studio?r=cool_roof')
  expect(screen.getByText(/1,686 degree-days a year/)).toBeInTheDocument()
})
