# 部署文档

本项目部署在 Azure VM（与另两个参赛项目共用一台机），通过端口/目录/服务隔离，
站点 https://voice.qiniu.zdwktlj.top 由宿主机共享 Caddy 提供自动 HTTPS。

## 架构

```
浏览器 ──HTTPS──> Caddy(系统级, :443)
                    ├─ /api/*  ──reverse_proxy──> 后端容器 127.0.0.1:8081
                    └─ 其余     ──file_server──> /opt/voice-calendar/frontend/dist (SPA)
```

- 后端：Docker 容器，仅监听 `127.0.0.1:8081`（不公网暴露，由 Caddy 反代）。
- 前端：Vite 构建的静态产物，Caddy 直接托管。
- 数据：SQLite 落在挂载卷 `/opt/voice-calendar/data/`，容器重建不丢。

## 隔离约定（同机三项目，见 BRIEF §3.5）

- compose project 名：`voice-calendar`
- 后端端口：`8081`（另两项目用 8082 等）
- 目录：`/opt/voice-calendar`
- Caddy 站点：`/etc/caddy/conf.d/voice.caddy`（只新增，不动主配置与他人配置）

## 前置条件

- VM 已装 Docker、Node 20、系统级 Caddy（主 Caddyfile 含 `import /etc/caddy/conf.d/*.caddy`）
- DNS：`voice.qiniu.zdwktlj.top` A 记录指向 VM 公网 IP
- 凭证文件 `/opt/voice-calendar/backend/.env`（含 AZURE_SPEECH_KEY / DEEPSEEK_API_KEY 等，权限 600，不入 git）

## 部署步骤

```bash
cd /opt/voice-calendar
git pull

# 1) 构建前端静态产物（Caddy 托管）
cd frontend && npm install && npm run build && cd ..

# 2) 构建并起后端容器（独立 project 名 + 8081）
docker compose -p voice-calendar up -d --build

# 3) 安装/更新 Caddy 站点并热重载（不影响其它站点）
sudo cp deploy/voice.caddy /etc/caddy/conf.d/voice.caddy
sudo systemctl reload caddy

# 4) 验证
curl -s https://voice.qiniu.zdwktlj.top/api/events
curl -s http://127.0.0.1:8081/health
```

一键脚本：`bash deploy/deploy.sh`（在 VM 的 /opt/voice-calendar 下执行）。

## 回滚

```bash
# 撤下本项目站点（不影响其它项目）
sudo rm /etc/caddy/conf.d/voice.caddy && sudo systemctl reload caddy
docker compose -p voice-calendar down
```

## 备注

- 浏览器麦克风/录音权限要求安全上下文（HTTPS），故上线必须有证书——Caddy 自动签发。
- 首次访问域名时 Caddy 现签 Let's Encrypt 证书，可能有数秒延迟。
