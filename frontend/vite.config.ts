/// <reference types="vitest" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API lives at the site root (same origin in production: FastAPI serves this app at /app).
const API = process.env.GG_API_URL ?? 'http://127.0.0.1:8000'
const apiPaths = ['/homes', '/advisor', '/bills', '/speech', '/telegram', '/portfolio', '/lab', '/reference', '/health', '/config']

export default defineConfig({
  base: '/app/',
  plugins: [react()],
  server: { port: 5173, proxy: Object.fromEntries(apiPaths.map((p) => [p, { target: API, changeOrigin: true }])) },
  build: {
    target: 'es2022',
    sourcemap: false,
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: { manualChunks: { react: ['react', 'react-dom', 'react-router-dom'], query: ['@tanstack/react-query'] } },
    },
  },
  test: { environment: 'jsdom', globals: true, setupFiles: ['src/test-setup.ts'], include: ['src/**/*.test.{ts,tsx}'] },
})
