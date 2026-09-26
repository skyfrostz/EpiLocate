import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.API_PROXY_TARGET
  return {
    plugins: [vue()],
    server: {
      host: '127.0.0.1',
      port: 5183,
      strictPort: true,
      proxy: target ? { '/api/v2': { target, changeOrigin: true } } : undefined,
    },
  }
})
