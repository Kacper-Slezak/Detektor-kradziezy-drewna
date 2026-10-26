import { defineConfig, minimal2023Preset } from '@vite-pwa/assets-generator/config'

// Generates the app icons from public/logo.svg: npm run generate-pwa-assets
// Android only: no iOS (apple-touch-icon) and no small desktop icon
export default defineConfig({
  preset: {
    ...minimal2023Preset,
    transparent: { ...minimal2023Preset.transparent, sizes: [192, 512] },
    // maskable icons get the logo's green as padding instead of white
    maskable: { ...minimal2023Preset.maskable, resizeOptions: { background: '#1f5130' } },
    apple: { sizes: [] },
  },
  images: ['public/logo.svg'],
})
