import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
// 백엔드에 CORS 설정이 없으므로 개발 서버 프록시로 API를 넘긴다(D-029).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_')
  const target = env.VITE_API_TARGET || 'http://127.0.0.1:8000'
  return {
    plugins: [react()],
    server: {
      proxy: {
        '/qa': target,
        '/ocr': target,
        '/subjects': target,
      },
    },
  }
})
