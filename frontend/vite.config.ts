import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// 构建产物直接落到 Python 包内，桌面端以本地文件方式加载，无需任何服务器。
export default defineConfig({
  plugins: [vue()],
  base: './',
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  build: {
    outDir: fileURLToPath(new URL('../docmorph/ui/webapp', import.meta.url)),
    emptyOutDir: true,
    assetsDir: 'assets',
    chunkSizeWarningLimit: 1200,
  },
  server: {
    port: 5173,
    strictPort: true,
  },
})
