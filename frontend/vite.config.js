import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: '../app/static',
    emptyOutDir: true,
    chunkSizeWarningLimit: 1400
  },
  server: {
    port: 5173,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/healthz': { target: 'http://127.0.0.1:8000', changeOrigin: true },
      '/readyz': { target: 'http://127.0.0.1:8000', changeOrigin: true }
    }
  }
})
