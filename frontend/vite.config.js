// 变更记录: 20261126-0922 新增：Vite 配置。/api 代理到本机后端（同源，session cookie 才能生效）；页面标题读取仓库根目录 .env 的 APP_DISPLAY_NAME
// 变更记录: 20261126-1436 /api 代理端口可由根目录 .env 的 BACKEND_PORT 指定（默认 8000），避免与同机其它项目冲突
import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  // 环境变量只在仓库根目录维护一份（与后端一致），这里不读取 frontend/ 下的 .env
  const repoEnv = loadEnv(mode, '..', '')
  const appTitle = repoEnv.APP_DISPLAY_NAME || repoEnv.APP_NAME || 'App'

  return {
    plugins: [
      vue(),
      {
        name: 'app-title',
        transformIndexHtml: (html) => html.replaceAll('%APP_DISPLAY_NAME%', appTitle),
      },
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 5173,
      proxy: {
        '/api': {
          target: `http://localhost:${repoEnv.BACKEND_PORT || 8000}`,
          changeOrigin: true,
        },
      },
    },
  }
})
