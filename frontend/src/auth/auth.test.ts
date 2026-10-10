import { describe, expect, it } from 'vitest'
import { checkPassword, normalizeUsername } from './auth'

describe('username + password rules (mirror the server)', () => {
  it('normalises usernames', () => {
    expect(normalizeUsername('  Asha.K_22 ')).toBe('asha.k_22')
  })
  it.each(['ab', 'has space', 'a@b.com', '-start', 'x'.repeat(31), 'dot..dot', 'end.'])('rejects %s', (u) => {
    expect(() => normalizeUsername(u)).toThrow()
  })
  it('accepts a mixed password and rejects weak ones', () => {
    expect(() => checkPassword('monsoon2026', 'asha')).not.toThrow()
    for (const bad of ['short1', '12345678', 'onlyletters', 'ashaasha']) expect(() => checkPassword(bad, 'ashaasha')).toThrow()
  })
})
