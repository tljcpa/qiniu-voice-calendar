"""日历数据访问层。

把数据库操作收拢在此，上层（API、语音指令编排）只调这些函数，不直接写 SQL。
所有函数接收 session，便于测试用内存库注入。

owner_id（创新1）：默认 None 表示不按用户过滤（直接调用/测试的历史行为）；
API 层始终传入登录用户 id，从而按用户作用域——安全在边界保证。
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
    owner_id: Optional[int] = None,
) -> Event:
    """创建事件。end_at 缺省为 start_at + 1 小时（见 D-10）。归属 owner_id。"""
    if end_at is None:
        end_at = start_at + DEFAULT_DURATION
    if attendees is None:
        attendees = []
    event = Event(
        owner_id=owner_id,
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


def get_event(
    session: Session, event_id: int, owner_id: Optional[int] = None
) -> Optional[Event]:
    """按 id 取事件；指定 owner_id 时校验归属，不符返回 None。"""
    event = session.get(Event, event_id)
    if event is None:
        return None
    if owner_id is not None and event.owner_id != owner_id:
        return None
    return event


def list_events(
    session: Session,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    owner_id: Optional[int] = None,
) -> list[Event]:
    """按时间范围列事件，按开始时间升序。owner_id 不空则按用户作用域。"""
    stmt = select(Event)
    if owner_id is not None:
        stmt = stmt.where(Event.owner_id == owner_id)
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
    owner_id: Optional[int] = None,
) -> list[Event]:
    """定位事件（删除/修改的目标匹配）。owner_id 不空则按用户作用域。"""
    stmt = select(Event)
    if owner_id is not None:
        stmt = stmt.where(Event.owner_id == owner_id)
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
    owner_id: Optional[int] = None,
    **fields,
) -> Optional[Event]:
    """更新事件指定字段。事件不存在或不属于 owner_id 返回 None。"""
    event = get_event(session, event_id, owner_id=owner_id)
    if event is None:
        return None
    allowed = {"title", "start_at", "end_at", "location", "attendees", "note"}
    for key, value in fields.items():
        if key in allowed:
            setattr(event, key, value)
    session.commit()
    session.refresh(event)
    return event


def delete_event(
    session: Session, event_id: int, owner_id: Optional[int] = None
) -> bool:
    """删除事件。成功 True；不存在或不属于 owner_id 返回 False。"""
    event = get_event(session, event_id, owner_id=owner_id)
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


def get_due_reminders(
    session: Session, now: datetime, owner_id: Optional[int] = None
) -> list[Reminder]:
    """取到期未发送的提醒，按时间升序。owner_id 不空则只取该用户事件的提醒。"""
    stmt = (
        select(Reminder)
        .where(Reminder.remind_at <= now)
        .where(Reminder.sent == False)  # noqa: E712 - SQLAlchemy 需用 ==
        .order_by(Reminder.remind_at.asc())
    )
    if owner_id is not None:
        stmt = stmt.join(Event, Reminder.event_id == Event.id).where(
            Event.owner_id == owner_id
        )
    return list(session.scalars(stmt).all())


def mark_reminder_sent(session: Session, reminder_id: int) -> None:
    """标记提醒已发送，避免重复弹出。"""
    reminder = session.get(Reminder, reminder_id)
    if reminder is not None:
        reminder.sent = True
        session.commit()
