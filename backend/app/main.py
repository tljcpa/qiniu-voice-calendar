"""FastAPI 应用入口。

PR1 仅装配最小骨架：
- 应用元信息与 CORS
- /health 健康检查端点（用于部署探活、CI 冒烟、main 分支可运行性验证）
- / 根路由返回服务标识

后续 PR 在此基础上挂载语音、意图解析、日历 CRUD、WebSocket 等路由。
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth as auth_api
from app.api import calendar_export as calendar_export_api
from app.api import events as events_api
from app.api import reminders as reminders_api
from app.api import speech as speech_api
from app.api import voice as voice_api
from app.config import settings
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表。

    用 lifespan 而非 import 期建表，避免 mock 单测（不进入服务生命周期）误建库文件。
    """
    init_db()
    yield


def create_app() -> FastAPI:
    """应用工厂。

    用工厂函数而非模块级全局 app，便于测试时以不同配置构造多个实例，
    也便于未来按需注册路由模块。
    """
    app = FastAPI(
        title="语音日历 API",
        version=settings.app_version,
        description="以语音交互为核心的日历管理工具后端",
        lifespan=lifespan,
    )

    # 跨域：前端（Vite 开发服务器 / 正式域名）与后端不同源，必须放行。
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root() -> dict:
        """根路由：返回服务标识，便于人工确认服务在线。"""
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
        }

    @app.get("/health")
    def health() -> dict:
        """健康检查。

        返回各依赖凭证是否就绪（只返回布尔，不泄露 key 内容），
        供部署探活与冒烟测试使用。status 恒为 ok 表示进程存活；
        依赖未配置不代表进程不健康，故单列字段。
        """
        return {
            "status": "ok",
            "version": settings.app_version,
            "dependencies": {
                "azure_speech": settings.speech_configured(),
                "llm": settings.llm_configured(),
            },
        }

    # 业务路由装配
    app.include_router(auth_api.router)
    app.include_router(speech_api.router)
    app.include_router(events_api.router)
    app.include_router(voice_api.router)
    app.include_router(reminders_api.router)
    app.include_router(calendar_export_api.router)

    return app


# uvicorn 入口：uvicorn app.main:app
app = create_app()
