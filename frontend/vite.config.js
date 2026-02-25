import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5174,
    proxy: {
      '/api/scans/ws': { target: 'ws://localhost:8001', ws: true, rewriteWsOrigin: true },
      '/api': { target: 'http://localhost:8001', changeOrigin: true },
    }
  },
  build: {
    outDir: '../static',
    emptyOutDir: true,
  }
})
