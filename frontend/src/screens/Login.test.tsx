// Username + password screen: sign-in, sign-up tab, client-side validation (auth calls mocked).
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import { useSession } from '../state/session'
import Login from './Login'

const signIn = vi.fn()
const signUp = vi.fn()
vi.mock('../auth/auth', async (orig) => ({
  ...(await orig<typeof import('../auth/auth')>()),
  signInWithPassword: (...a: unknown[]) => signIn(...a),
  signUpWithPassword: (...a: unknown[]) => signUp(...a),
}))
vi.mock('../components/Layout', () => ({ BrandMark: () => null }))

const setup = () => render(<MemoryRouter><Login /></MemoryRouter>)
const fill = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })

beforeEach(() => {
  signIn.mockReset().mockResolvedValue(undefined)
  signUp.mockReset().mockResolvedValue(undefined)
  useSession.getState().setAuthMode('supabase')
  useSession.getState().setUser(null)
})

it('signs in with username and password', async () => {
  setup()
  fill('Username', 'Asha')
  fill('Password', 'monsoon2026')
  fireEvent.submit(screen.getByLabelText('Username').closest('form')!)
  await waitFor(() => expect(signIn).toHaveBeenCalledWith('Asha', 'monsoon2026'))
})

it('sign-up blocks mismatched passwords before any request', async () => {
  setup()
  fireEvent.click(screen.getByRole('tab', { name: 'Sign up' }))
  fill('Username', 'asha')
  fill('Password', 'monsoon2026')
  fill('Confirm password', 'monsoon2027')
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('do not match')
  expect(signUp).not.toHaveBeenCalled()
})

it('sign-up rejects weak passwords and creates the account otherwise', async () => {
  setup()
  fireEvent.click(screen.getByRole('tab', { name: 'Sign up' }))
  fill('Username', 'asha')
  fill('Password', 'onlyletters')
  fill('Confirm password', 'onlyletters')
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('mix of letters and numbers')
  fill('Password', 'monsoon2026')
  fill('Confirm password', 'monsoon2026')
  fireEvent.click(screen.getByRole('button', { name: 'Create account' }))
  await waitFor(() => expect(signUp).toHaveBeenCalledWith('asha', 'monsoon2026'))
})

it('shows a sign-in failure message', async () => {
  signIn.mockRejectedValue(new Error('Wrong username or password.'))
  setup()
  fill('Username', 'asha')
  fill('Password', 'nope12345')
  fireEvent.submit(screen.getByLabelText('Username').closest('form')!)
  expect(await screen.findByRole('alert')).toHaveTextContent('Wrong username or password.')
})
