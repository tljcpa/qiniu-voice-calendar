"""日历 ORM 模型（见 docs/复盘.md D-10）。

event：日历事件本体。
reminder：挂在事件上的提醒（PR14 调度用）。
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db import Base


class User(Base):
    """用户（创新1：账户）。密码只存 bcrypt 哈希，绝不存明文。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)


class Event(Base):
    """日历事件。

    时间用 naive datetime（本地时区语义，demo 单时区，见 D-10）。
    attendees 存 JSON 列表，不另开关联表。
    owner_id 归属用户（创新1）；可空以兼容历史数据，API 层始终按登录用户作用域。
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(200))
    start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    # end_at 可空；crud 层在缺省时补 start_at + 1 小时
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    # 参与人列表，JSON 存储，缺省空列表
    attendees: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.now
    )

    reminders: Mapped[list["Reminder"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
    )

    def to_dict(self) -> dict:
        """序列化为 API 友好的 dict（datetime 转 ISO 字符串）。"""
        end_iso = None
        if self.end_at is not None:
            end_iso = self.end_at.isoformat()
        return {
            "id": self.id,
            "title": self.title,
            "start_at": self.start_at.isoformat(),
            "end_at": end_iso,
            "location": self.location,
            "attendees": self.attendees or [],
            "note": self.note,
        }


class Reminder(Base):
    """事件提醒。channel：browser / email 等。sent：是否已触发。"""

    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    remind_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    channel: Mapped[str] = mapped_column(String(20), default="browser")
    sent: Mapped[bool] = mapped_column(default=False)

    event: Mapped["Event"] = relationship(back_populates="reminders")
