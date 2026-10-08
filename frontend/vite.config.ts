import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(
    mode,
    process.cwd(),
    '',
  )

  const apiTarget =
    env.VITE_API_TARGET ||
    'http://127.0.0.1:8000'

  return {
    plugins: [
      react(),
    ],

    server: {
      proxy: {
        '/subjects': {
          target: apiTarget,
          changeOrigin: true,
        },

        '/qa': {
          target: apiTarget,
          changeOrigin: true,
        },

        '/ocr': {
          target: apiTarget,
          changeOrigin: true,
        },

        '/answer-reports': {
          target: apiTarget,
          changeOrigin: true,
        },

        '/supplements': {
          target: apiTarget,
          changeOrigin: true,
        },

        '/blocks': {
          target: apiTarget,
          changeOrigin: true,
        },

        '/block-corrections': {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
  }
})