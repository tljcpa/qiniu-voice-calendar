# 后端镜像。显式钉 3.11（见 docs/复盘.md L-01：开发机为 3.10，部署锁定推荐版本）。
FROM python:3.11-slim

# 不写 .pyc、stdout 不缓冲，便于容器日志实时可见。
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 先单独拷贝依赖清单再安装，利用 Docker 层缓存：源码变动不触发重装依赖。
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝应用源码
COPY app ./app

EXPOSE 8081

# 生产用 uvicorn 直起；进阶可换 gunicorn+uvicorn worker。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]
