"""日历数据访问层。

把数据库操作收拢在此，上层（API、语音指令编排）只调这些函数，不直接写 SQL。
所有函数接收 session，便于测试用内存库注入。
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, Reminder

# 用户未说结束时间时的默认时长。
DEFAULT_DURATION = timedelta(hours=1)


def create_event(
    session: Session,
    title: str,
    start_at: datetime,
    end_at: Optional[datetime] = None,
    location: Optional[str] = None,
    attendees: Optional[list] = None,
    note: Optional[str] = None,
) -> Event:
    """创建事件。end_at 缺省为 start_at + 1 小时（见 D-10）。"""
    if end_at is None:
        end_at = start_at + DEFAULT_DURATION
    if attendees is None:
        attendees = []
    event = Event(
        title=title,
        start_at=start_at,
        end_at=end_at,
        location=location,
        attendees=attendees,
        note=note,
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


def get_event(session: Session, event_id: int) -> Optional[Event]:
    """按 id 取事件，不存在返回 None。"""
    return session.get(Event, event_id)


def list_events(
    session: Session,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[Event]:
    """按时间范围列事件，按开始时间升序。

    start/end 针对事件的 start_at 过滤（闭区间）。都不传则返回全部。
    """
    stmt = select(Event)
    if start is not None:
        stmt = stmt.where(Event.start_at >= start)
    if end is not None:
        stmt = stmt.where(Event.start_at <= end)
    stmt = stmt.order_by(Event.start_at.asc())
    return list(session.scalars(stmt).all())


def find_events(
    session: Session,
    keyword: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> list[Event]:
    """定位事件，用于删除/修改的目标匹配。

    keyword 对标题做包含匹配（大小写不敏感对中文无意义，直接子串）；
    叠加可选时间范围。结果按开始时间升序，供"找到 N 个候选"的歧义澄清用。
    """
    stmt = select(Event)
    if keyword:
        stmt = stmt.where(Event.title.contains(keyword))
    if start is not None:
        stmt = stmt.where(Event.start_at >= start)
    if end is not None:
        stmt = stmt.where(Event.start_at <= end)
    stmt = stmt.order_by(Event.start_at.asc())
    return list(session.scalars(stmt).all())


def update_event(
    session: Session,
    event_id: int,
    **fields,
) -> Optional[Event]:
    """更新事件指定字段。事件不存在返回 None。

    只更新传入且模型上存在的字段，忽略 None 之外的非法键。
    """
    event = session.get(Event, event_id)
    if event is None:
        return None
    allowed = {"title", "start_at", "end_at", "location", "attendees", "note"}
    for key, value in fields.items():
        if key in allowed:
            setattr(event, key, value)
    session.commit()
    session.refresh(event)
    return event


def delete_event(session: Session, event_id: int) -> bool:
    """删除事件。删除成功返回 True，不存在返回 False。"""
    event = session.get(Event, event_id)
    if event is None:
        return False
    session.delete(event)
    session.commit()
    return True


def create_reminder(
    session: Session,
    event_id: int,
    remind_at: datetime,
    channel: str = "browser",
) -> Reminder:
    """为事件创建提醒。"""
    reminder = Reminder(event_id=event_id, remind_at=remind_at, channel=channel)
    session.add(reminder)
    session.commit()
    session.refresh(reminder)
    return reminder
