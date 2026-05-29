import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// 开发期把 /api 代理到后端 8081，避免本地跨域；生产由 Caddy 统一反代。
export default defineConfig({
  plugins: [react()],
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
});
