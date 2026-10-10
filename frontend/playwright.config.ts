import { defineConfig } from '@playwright/test'

// E2E against the real FastAPI backend serving the built app at /app (npm run build first).
const port = Number(process.env.GG_E2E_PORT ?? 8765)
export default defineConfig({
  testDir: 'e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${port}/app/`,
    launchOptions: { executablePath: process.env.CHROME ?? '/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell' },
    viewport: { width: 1440, height: 900 },
    trace: 'retain-on-failure',
  },
  webServer: {
    command: `cd .. && GG_ENV_FILE=/dev/null GG_RUNTIME_DIR=$(mktemp -d) GG_RATE_LIMIT_PER_MIN=1000 uvicorn greenghar.api.main:app --host 127.0.0.1 --port ${port}`,
    url: `http://127.0.0.1:${port}/health`,
    reuseExistingServer: false,
    timeout: 120_000,
  },
})
