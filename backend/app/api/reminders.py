"""提醒 API。

前端定时轮询 /api/reminders/due 取到期提醒并弹浏览器通知（见复盘 D-09）。
DB 即状态，重启安全；浏览器一打开就能补弹错过的提醒。
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import crud
from app.db import get_session

router = APIRouter(prefix="/api/reminders", tags=["reminders"])


@router.get("/due")
def due_reminders(session: Session = Depends(get_session)) -> list[dict]:
    """返回到期未发的提醒并标记已发，供前端弹通知。

    每条含关联事件标题与开始时间，便于通知文案。
    """
    now = datetime.now()
    due = crud.get_due_reminders(session, now)
    result = []
    for r in due:
        event = crud.get_event(session, r.event_id)
        if event is None:
            # 事件已删除：直接标记已发，跳过
            crud.mark_reminder_sent(session, r.id)
            continue
        result.append(
            {
                "id": r.id,
                "event_id": r.event_id,
                "title": event.title,
                "start_at": event.start_at.isoformat(),
                "remind_at": r.remind_at.isoformat(),
            }
        )
        crud.mark_reminder_sent(session, r.id)
    return result
