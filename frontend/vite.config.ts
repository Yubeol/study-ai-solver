import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const API_TARGET =
    process.env.VITE_API_TARGET ||
    'http://127.0.0.1:8000'

export default defineConfig({
  plugins: [react()],

  server: {
    proxy: {
      '/qa': {
        target: API_TARGET,
        changeOrigin: true,
      },

      '/ocr': {
        target: API_TARGET,
        changeOrigin: true,
      },

      '/subjects': {
        target: API_TARGET,
        changeOrigin: true,
      },

      '/answer-reports': {
        target: API_TARGET,
        changeOrigin: true,
      },

      '/supplements': {
        target: API_TARGET,
        changeOrigin: true,
      },
    },
  },
})