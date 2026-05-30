import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发期把 /api 代理到后端 8081，避免本地跨域；生产由 Caddy 统一反代。
export default defineConfig({
  plugins: [react()],
  build: {
    // 不清空 dist：自托管的演示视频放在 dist/demo/，构建时不应删除它。
    // 部署脚本只清理 dist/assets（哈希产物）避免堆积，保留 dist/demo。
    emptyOutDir: false,
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8081",
        changeOrigin: true,
      },
    },
  },
  // preview（生产构建预览）也走同样代理，便于在 VM 上整体验证。
  preview: {
    host: true,
    port: 4173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8081",
        changeOrigin: true,
      },
    },
  },
});
