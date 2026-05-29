#!/usr/bin/env bash
# 语音日历一键部署脚本。在 VM 的 /opt/voice-calendar 下执行。
# 幂等：可重复运行以更新到最新代码。
set -euo pipefail

ROOT="/opt/voice-calendar"
cd "$ROOT"

echo "==> 拉取最新代码"
git pull

echo "==> 构建前端静态产物"
cd "$ROOT/frontend"
npm install
npm run build

echo "==> 构建并启动后端容器（project=voice-calendar, 端口 8081）"
cd "$ROOT"
mkdir -p "$ROOT/data"
docker compose -p voice-calendar up -d --build

echo "==> 安装 Caddy 站点并热重载"
sudo cp "$ROOT/deploy/voice.caddy" /etc/caddy/conf.d/voice.caddy
sudo systemctl reload caddy

echo "==> 等待后端就绪"
for i in $(seq 1 20); do
	if curl -sf http://127.0.0.1:8081/health >/dev/null; then
		echo "后端 up"
		break
	fi
	sleep 1
done

echo "==> 验证"
curl -s http://127.0.0.1:8081/health
echo ""
echo "部署完成：https://voice.qiniu.zdwktlj.top"
