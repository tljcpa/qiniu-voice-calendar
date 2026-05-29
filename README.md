# 语音日历

> 七牛云 × XEngineer 暑期实训营 - 题目一作品

以语音交互为核心的日历管理工具，支持通过语音添加 / 删除 / 查看事件提醒，提升日程管理的效率与便捷性。

- 在线 Demo：待部署（https://voice.qiniu.zdwktlj.top）
- 演示视频：待录制
- 架构文档：见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)（编写中）

## 核心特性（开发中）

- Azure Speech 工业级中文 ASR / TTS（而非识别率不佳的浏览器 Web Speech API）
- 真"语音闭环"：语音指令 + TTS 语音回复
- 自然中文时间解析（覆盖"下周三""每周一三五"等 30+ 表达式）
- 歧义对话澄清
- 冲突检测与智能调度建议

## 项目结构

```
voice-calendar/
├── backend/            FastAPI 后端
│   ├── app/            应用代码（config / main / 后续模块）
│   ├── tests/          测试
│   ├── requirements.txt
│   └── Dockerfile      部署镜像（python:3.11-slim）
├── frontend/           前端（React + Vite，PR10 起填充）
├── deploy/             部署配置（Caddyfile 等）
├── docs/               架构、决策复盘、设计文档
├── docker-compose.yml  编排骨架
└── LICENSE             MIT
```

## 快速开始（后端）

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8081
# 验证：curl http://localhost:8081/health
```

## 开发状态

本仓库在 72 小时实战周期内（2026-05-29 至 2026-05-31）按 PR 工作流持续开发。
开发决策与踩坑记录见 [docs/复盘.md](docs/复盘.md)。

## AI 协作声明

本项目通过 Claude Code 辅助开发，Prompt / 决策 / 关键 review 见 docs/复盘.md。
代码经过人工审阅、测试与定型。详细声明在交付前补充于本节。

## 开源协议

[MIT](LICENSE)

## 作者

tljcpa
