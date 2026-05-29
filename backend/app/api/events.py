"""日历事件 REST API。

供前端 FullCalendar 拉取/手动增删改事件（语音之外的图形操作兜底）。
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import crud
from app.db import get_session

router = APIRouter(prefix="/api/events", tags=["events"])


class EventCreate(BaseModel):
    title: str
    start_at: datetime
    end_at: Optional[datetime] = None
    location: Optional[str] = None
    attendees: list[str] = []
    note: Optional[str] = None


class EventUpdate(BaseModel):
    title: Optional[str] = None
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    location: Optional[str] = None
    attendees: Optional[list[str]] = None
    note: Optional[str] = None


@router.get("")
def list_events(
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    session: Session = Depends(get_session),
) -> list[dict]:
    """按时间范围列事件（FullCalendar 视图拉取用）。"""
    events = crud.list_events(session, start=start, end=end)
    return [e.to_dict() for e in events]


@router.post("", status_code=201)
def create_event(body: EventCreate, session: Session = Depends(get_session)) -> dict:
    """手动创建事件。"""
    ev = crud.create_event(
        session,
        title=body.title,
        start_at=body.start_at,
        end_at=body.end_at,
        location=body.location,
        attendees=body.attendees,
        note=body.note,
    )
    return ev.to_dict()


@router.patch("/{event_id}")
def update_event(
    event_id: int, body: EventUpdate, session: Session = Depends(get_session)
) -> dict:
    """修改事件。只更新提供的字段。"""
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    ev = crud.update_event(session, event_id, **fields)
    if ev is None:
        raise HTTPException(status_code=404, detail="事件不存在")
    return ev.to_dict()


@router.delete("/{event_id}")
def delete_event(event_id: int, session: Session = Depends(get_session)) -> dict:
    """删除事件。"""
    ok = crud.delete_event(session, event_id)
    if not ok:
        raise HTTPException(status_code=404, detail="事件不存在")
    return {"ok": True, "deleted": event_id}
