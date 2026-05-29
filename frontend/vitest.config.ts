import { defineConfig } from "vitest/config";

// 前端单元测试用 node 环境（被测的是纯逻辑/网络层，无需 DOM）。
export default defineConfig({
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
