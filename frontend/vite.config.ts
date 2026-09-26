import vue from '@vitejs/plugin-vue'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.API_PROXY_TARGET
  const userToken = env.API_PROXY_USER_TOKEN
  const proxySecure = env.API_PROXY_INSECURE !== 'true'
  return {
    plugins: [vue()],
    resolve: { alias: { events: 'events/' } },
    optimizeDeps: { include: [
      '@cornerstonejs/codec-libjpeg-turbo-8bit/decodewasmjs',
      '@cornerstonejs/codec-charls/decodewasmjs',
      '@cornerstonejs/codec-openjpeg/decodewasmjs',
      '@cornerstonejs/codec-openjph/wasmjs',
      '@cornerstonejs/codec-libjxl/decodewasmjs',
    ] },
    server: {
      host: '127.0.0.1',
      port: 5183,
      strictPort: true,
      proxy: target ? {
        '/api/v2': {
          target,
          changeOrigin: true,
          secure: proxySecure,
          configure(proxy) {
            if (userToken) proxy.on('proxyReq', request => request.setHeader('Authorization', `Bearer ${userToken}`))
          },
        },
      } : undefined,
    },
  }
})
