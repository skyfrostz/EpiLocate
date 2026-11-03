import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
export default defineConfig({base:'/annotations/',plugins:[vue()],resolve:{alias:{events:'events/'}},test:{environment:'jsdom',include:['src/**/*.spec.ts']}})
