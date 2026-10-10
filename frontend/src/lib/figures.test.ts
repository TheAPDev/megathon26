import { figures, segments } from './figures'
import { inr, inrShort, num } from './format'

describe('figure extraction mirrors the backend verifier', () => {
  it('counts money, kWh and percentages but exempts small counts and years', () => {
    const f = figures('Your score is 52 and 3 measures save ₹28,800 a year (34%) by 2027.').filter((x) => x.counted).map((x) => x.token)
    expect(f).toEqual(['52', '28,800', '34%'])
  })
  it('reads lakh/crore and Devanagari digits', () => {
    const f = figures('लागत १,४५,००० है, या 1.45 lakh').filter((x) => x.counted).map((x) => x.token)
    expect(f).toEqual(['1,45,000', '1.45 lakh'])
  })
  it('marks exactly the unsupported tokens as unverified', () => {
    const s = segments('Saves ₹28,800 a year and ₹7,20,000 over 25 years.', ['7,20,000'])
    expect(s.filter((x) => x.status === 'unverified').map((x) => x.text)).toEqual(['7,20,000'])
    expect(s.filter((x) => x.status === 'verified').map((x) => x.text)).toEqual(['28,800', '25'])
    expect(s.map((x) => x.text).join('')).toBe('Saves ₹28,800 a year and ₹7,20,000 over 25 years.')
  })
})

describe('Indian number formatting', () => {
  it('groups in lakhs', () => {
    expect(inr(123456)).toBe('₹1,23,456')
    expect(num(1240)).toBe('1,240')
    expect(inrShort(196000)).toBe('₹1.96L')
    expect(inrShort(18_420_000_000)).toBe('₹1,842 Cr')
  })
})
