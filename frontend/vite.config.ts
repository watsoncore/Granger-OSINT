import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  base: './',
  plugins: [react()],
  build: { target: 'es2022', sourcemap: false, assetsInlineLimit: 0 },
  test: { environment: 'jsdom', setupFiles: './src/test-setup.ts', css: false },
})
