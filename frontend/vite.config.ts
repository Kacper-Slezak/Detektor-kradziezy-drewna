import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    // w Dockerze na Windowsie zmiany plików wykrywamy odpytywaniem
    watch: { usePolling: process.env.CHOKIDAR_USEPOLLING === 'true' },
    proxy: {
      // /api/... idzie do FastAPI; w Dockerze adres podaje docker-compose.yml
      '/api': process.env.API_TARGET ?? 'http://localhost:8000',
    },
  },
})
