"""数据库引擎、会话与基类。

设计：
- make_engine/make_session_factory 工厂化，便于测试用内存库构造独立引擎。
- 内存 SQLite 用 StaticPool + check_same_thread=False，否则每次连接是新库、跨线程报错。
- 应用级 engine/SessionLocal 从 settings.database_url 构造。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def make_engine(url: str):
    """按 URL 构造引擎。内存 SQLite 做特殊池化处理。"""
    if url == "sqlite://" or ":memory:" in url:
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    if url.startswith("sqlite"):
        # 文件型 SQLite：FastAPI 多线程下也需放开同线程检查
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url)


def make_session_factory(engine) -> sessionmaker:
    """构造会话工厂。"""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# 应用级单例
engine = make_engine(settings.database_url)
SessionLocal = make_session_factory(engine)


def init_db() -> None:
    """建表。应用启动时调用一次。"""
    # 导入模型以注册到 Base.metadata（避免循环导入，函数内导入）
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_session():
    """FastAPI 依赖：每请求一个会话，结束自动关闭。"""
    session: Session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
