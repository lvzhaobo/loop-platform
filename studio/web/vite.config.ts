import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ command }) => ({
  plugins: [vue()],
  // 开发服务器仍从根路径服务；构建产物固定部署在 Flask 的 /studio-vue/ 下。
  base: command === 'build' ? '/studio-vue/' : '/',
  server: {
    port: 5175,
    proxy: {
      '/studio-api': {
        target: 'http://127.0.0.1:5100',
        changeOrigin: true,
        rewrite: path => path.replace(/^\/studio-api/, ''),
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
}))
