import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Dev-server-only proxy target (never bundled into the production build —
// vite build doesn't run a server, so this block is irrelevant once
// deployed; production origin resolution lives in src/lib/api.js instead).
// Overridable via PROXY_TARGET so `docker-compose up` (where the backend is
// reachable at the `api` service name, not localhost) and plain host-machine
// `pnpm dev` (where it's reachable at localhost:8000) both work unmodified.
const proxyTarget = process.env.PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
})
