import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const backendTarget = process.env.VITE_BACKEND_PROXY_TARGET ?? 'http://127.0.0.1:18080'
const backendProxy = {
  target: backendTarget,
  changeOrigin: false,
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 15173,
    strictPort: true,
    proxy: {
      '/api': backendProxy,
      '/static': backendProxy,
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 15173,
    strictPort: true,
    proxy: {
      '/api': backendProxy,
      '/static': backendProxy,
    },
  },
})
