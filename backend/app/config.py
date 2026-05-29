"""运行期配置。

设计原则：
- 所有外部依赖（Azure Speech / DeepSeek / Azure OpenAI）的凭证只从环境变量读取，
  绝不硬编码、绝不入 git。
- 配置集中在一个对象里，避免散落的 os.getenv 调用。
- PR1 阶段保持轻量，仅用标准库 os.getenv；待配置项增多再考虑 pydantic-settings。
"""

import os


class Settings:
    """集中式配置对象。

    读取顺序：进程环境变量。本地开发用 backend/.env.example 复制为 .env 后
    由启动脚本 source（.env 已被 .gitignore 忽略）。
    """

    def __init__(self) -> None:
        # 应用元信息
        self.app_name: str = "voice-calendar-backend"
        self.app_version: str = "0.1.0"

        # 服务监听地址。部署时三项目共用一台机，本项目固定用 8081 端口避免冲突。
        self.host: str = os.getenv("APP_HOST", "0.0.0.0")
        self.port: int = int(os.getenv("APP_PORT", "8081"))

        # CORS 允许来源。开发期放开本地前端端口，部署时收敛到正式域名。
        cors_raw: str = os.getenv(
            "CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        )
        self.cors_origins: list[str] = [
            origin.strip() for origin in cors_raw.split(",") if origin.strip()
        ]

        # Azure Speech（核心语音能力，PR4 起使用）
        self.azure_speech_key: str = os.getenv("AZURE_SPEECH_KEY", "")
        self.azure_speech_region: str = os.getenv("AZURE_SPEECH_REGION", "eastus2")

        # LLM 后端（PR3 起使用）
        self.deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
        self.deepseek_base_url: str = os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com"
        )
        self.deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    def speech_configured(self) -> bool:
        """Azure Speech 凭证是否就绪。健康检查用，不打印 key 本身。"""
        if self.azure_speech_key:
            return True
        return False

    def llm_configured(self) -> bool:
        """LLM 凭证是否就绪。"""
        if self.deepseek_api_key:
            return True
        return False


# 进程级单例。其他模块统一 from app.config import settings 引用。
settings = Settings()
