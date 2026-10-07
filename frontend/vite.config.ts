import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const apiTarget = env.VITE_API_TARGET || 'http://localhost:8000'

  return {
    plugins: [react()],
    server: {
      proxy: {
        '/qa': {
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
      },
    },
  }
})