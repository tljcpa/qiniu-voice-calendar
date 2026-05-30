"""日历 .ics 导出端点（创新3：真实操作）。

GET /api/calendar/export.ics?range=today|week|month
  - 返回 text/calendar 附件，浏览器直接下载。
  - 同时支持 webcal:// 订阅：因移动端日历 App 不带 Authorization 头，
    额外接受 ?token=<jwt> 作为鉴权 fallback（仅此端点允许）。

设计原则：纯确定性操作，不调 LLM，不烧 DeepSeek 余额。
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from icalendar import Calendar
from icalendar import Event as ICalEvent
from sqlalchemy.orm import Session

from app import crud
from app.auth import decode_token, get_current_user
from app.db import get_session
from app.models import Event, User

router = APIRouter(prefix="/api/calendar", tags=["calendar-export"])

# webcal 订阅场景下，token 放 query param 是行业惯例（Google/Apple 均如此）。
# 仅此端点允许；其他端点仍要求 Authorization header。
_EXPORT_RANGES = {"today", "week", "month"}


def _week_bounds(now: datetime):
    """本周一 00:00 ~ 本周日 23:59:59。"""
    monday = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return monday, sunday


def _resolve_range(range_: str, now: datetime):
    """range 字符串 → (start, end, label)。未知值降级为 week。"""
    if range_ == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1) - timedelta(seconds=1)
        return start, end, "今日"
    if range_ == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            next_first = start.replace(year=now.year + 1, month=1)
        else:
            next_first = start.replace(month=now.month + 1)
        end = next_first - timedelta(seconds=1)
        return start, end, "本月"
    # 默认 week
    start, end = _week_bounds(now)
    return start, end, "本周"


def _build_ics(events: list[Event], cal_name: str) -> bytes:
    """把 Event 列表序列化为标准 iCalendar 字节流。"""
    cal = Calendar()
    cal.add("prodid", "-//语音日历//voice-calendar//ZH")
    cal.add("version", "2.0")
    # x-wr-calname：让 Apple/Google Calendar 显示订阅源名称
    cal.add("x-wr-calname", f"语音日历 · {cal_name}")
    cal.add("x-wr-caldesc", "由语音日历导出")
    # REFRESH-INTERVAL：提示客户端每 6 小时刷新一次（webcal 订阅）
    cal.add("refresh-interval;value=duration", "PT6H")

    for ev in events:
        ical_ev = ICalEvent()
        # UID 全局唯一：保证重复订阅时同一事件不会重复
        ical_ev.add("uid", f"voice-cal-{ev.id}@voice-calendar")
        ical_ev.add("summary", ev.title)
        ical_ev.add("dtstart", ev.start_at)
        end_at = ev.end_at if ev.end_at else ev.start_at + timedelta(hours=1)
        ical_ev.add("dtend", end_at)
        ical_ev.add("dtstamp", ev.created_at)
        if ev.location:
            ical_ev.add("location", ev.location)
        parts = []
        if ev.note:
            parts.append(ev.note)
        if ev.attendees:
            parts.append("参与人：" + "、".join(ev.attendees))
        if parts:
            ical_ev.add("description", "\n".join(parts))
        cal.add_component(ical_ev)

    return cal.to_ical()


def _get_user_flexible(
    request: Request,
    token_param: str | None = Query(default=None, alias="token"),
    session: Session = Depends(get_session),
) -> User:
    """鉴权：先读 Authorization header，再读 ?token= query param。

    仅供 export 端点使用，支持 webcal:// 订阅场景（移动日历 App 不带 header）。
    """
    # 优先 Authorization header
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        jwt_str = auth.split(" ", 1)[1].strip()
    elif token_param:
        jwt_str = token_param
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="未登录")

    user_id = decode_token(jwt_str)
    if user_id is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="登录已失效，请重新登录")
    user = session.get(User, user_id)
    if user is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


@router.get("/export.ics")
def export_ics(
    range: str = Query(default="week", description="导出范围：today / week / month"),
    user: User = Depends(_get_user_flexible),
    session: Session = Depends(get_session),
) -> Response:
    """生成当前用户指定时间范围内的 .ics 日历文件。

    返回 text/calendar，Content-Disposition: attachment，浏览器直接下载。
    也可作为 webcal:// 订阅源（需在 URL 中附带 ?token=<jwt>）。
    """
    now = datetime.now()
    if range not in _EXPORT_RANGES:
        range = "week"

    start, end, label = _resolve_range(range, now)
    events = crud.list_events(session, start=start, end=end, owner_id=user.id)
    ics_bytes = _build_ics(events, label)

    filename = f"voice-calendar-{range}.ics"
    return Response(
        content=ics_bytes,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            # 允许前端 JS 读取 Content-Disposition（CORS 暴露头）
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )
