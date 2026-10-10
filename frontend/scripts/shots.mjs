// Screenshot every screen against a running backend (dev aid; not part of CI).
import { chromium } from '@playwright/test'
const base = process.env.BASE ?? 'http://127.0.0.1:8000/app'
const out = process.argv[2] ?? 'shots'
const width = Number(process.env.W ?? 1440)
const exe = process.env.CHROME ?? '/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell'
const b = await chromium.launch({ executablePath: exe })
const p = await b.newPage({ viewport: { width, height: 900 } })
const logs = []
p.on('console', (m) => (m.type() === 'error' || m.type() === 'warning') && logs.push(`${m.type()}: ${m.text()}`))
p.on('pageerror', (e) => logs.push(`pageerror: ${e.message}`))
p.on('response', (r) => r.status() >= 400 && logs.push(`HTTP ${r.status()} ${r.url()}`))
for (const [name, path] of [['dashboard', '/'], ['studio', '/studio?r=cool_roof,ac_5star_inverter,led_lighting'], ['paisa', '/paisa?r=cool_roof,ac_5star_inverter,led_lighting'],
  ['saathi', '/saathi'], ['portfolio', '/portfolio'], ['bill', '/bill'], ['garmi', '/garmi']]) {
  await p.goto(base + path, { waitUntil: 'networkidle' })
  await p.waitForTimeout(800)
  await p.screenshot({ path: `${out}/${name}-${width}.png`, fullPage: true })
}
console.log(logs.join('\n') || 'no console errors')
await b.close()
