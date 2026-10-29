/// <reference types="vitest/config" />
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // Installable app (manifest + service worker); works only in the build (npm run build && npm run preview)
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'Detektor kradzieży drewna',
        short_name: 'Detektor',
        description: 'Czujniki i alarmy kradzieży drewna',
        lang: 'pl',
        start_url: '/',
        scope: '/',
        display: 'standalone',
        theme_color: '#1f5130',
        background_color: '#ffffff',
        icons: [
          { src: 'pwa-192x192.png', sizes: '192x192', type: 'image/png' },
          { src: 'pwa-512x512.png', sizes: '512x512', type: 'image/png' },
          { src: 'maskable-icon-512x512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
        // API responses are never served from the cache
        navigateFallbackDenylist: [/^\/api\//],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
    // in Docker on Windows, file changes are detected by polling
    watch: { usePolling: process.env.CHOKIDAR_USEPOLLING === 'true' },
    proxy: {
      // /api/... goes to FastAPI; in Docker the address comes from docker-compose.yml
      '/api': process.env.API_TARGET ?? 'http://localhost:8000',
    },
  },
  preview: {
    allowedHosts: ['.loca.lt'],
    proxy: {
      '/api': process.env.API_TARGET ?? 'http://localhost:8000',
    },
  },
  test: {
    environment: 'jsdom',
    // tests never call FastAPI
    env: { VITE_USE_MOCK: 'true' },
    setupFiles: ['./src/test/setup.ts'],
  },
})
