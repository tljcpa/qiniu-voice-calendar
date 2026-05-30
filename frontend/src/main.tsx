import React from "react";
import ReactDOM from "react-dom/client";
// 自托管字体（不依赖外部 CDN，按 unicode-range 子集懒加载）：
// UI 正文 Noto Sans SC；标题/事件 霞鹜文楷（手账手写气质，GB 简体覆盖）。
import "@fontsource/noto-sans-sc/400.css";
import "@fontsource/noto-sans-sc/500.css";
import "@fontsource/noto-sans-sc/700.css";
import "lxgw-wenkai-screen-webfont/lxgwwenkaigbscreen.css";
import App from "./App";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
