"""冲突检测与调度建议（亮点 5）。

添加事件时检测时间冲突，并在冲突时给出可行的替代时段建议——
体现"日历助手"产品思维，而非简单报错（见 docs/复盘.md D-07）。
"""

from datetime import datetime, time, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.crud import list_events
from app.models import Event

# 建议扫描的步进与工作时段（日程通常按刻钟对齐）。
SLOT_STEP = timedelta(minutes=15)
WORK_START = time(8, 0)
WORK_END = time(22, 0)
# 建议向后扫描的最大跨度（避免无限扫描）。
MAX_SCAN = timedelta(days=2)


def _overlaps(s1: datetime, e1: datetime, s2: datetime, e2: datetime) -> bool:
    """半开区间 [s,e) 相交判定：相邻不算冲突（见 D-07）。"""
    if s1 < e2 and s2 < e1:
        return True
    return False


def find_overlaps(
    session: Session,
    start_at: datetime,
    end_at: datetime,
    exclude_id: Optional[int] = None,
    owner_id: Optional[int] = None,
) -> list[Event]:
    """返回与 [start_at, end_at) 冲突的现有事件（按 owner_id 作用域）。

    exclude_id：修改场景下排除事件自身。
    扫描范围限定在目标日前后一天，避免全表比较。
    """
    window_start = start_at - timedelta(days=1)
    window_end = end_at + timedelta(days=1)
    candidates = list_events(session, start=window_start, end=window_end, owner_id=owner_id)

    conflicts = []
    for ev in candidates:
        if exclude_id is not None and ev.id == exclude_id:
            continue
        ev_end = ev.end_at
        if ev_end is None:
            ev_end = ev.start_at + timedelta(hours=1)
        if _overlaps(start_at, end_at, ev.start_at, ev_end):
            conflicts.append(ev)
    return conflicts


def _within_work_hours(start_at: datetime, end_at: datetime) -> bool:
    """时段是否落在工作时段内（同日，开始与结束都在 8:00-22:00）。"""
    if start_at.time() < WORK_START:
        return False
    if end_at.time() > WORK_END:
        return False
    if end_at.date() != start_at.date():
        return False
    return True


def suggest_free_slot(
    session: Session,
    start_at: datetime,
    end_at: datetime,
    exclude_id: Optional[int] = None,
    owner_id: Optional[int] = None,
) -> Optional[datetime]:
    """从期望开始时间起向后找第一个无冲突且在工作时段内的空档起点。

    保持原时长不变。找不到返回 None。
    """
    duration = end_at - start_at
    cursor = start_at
    limit = start_at + MAX_SCAN

    while cursor <= limit:
        candidate_end = cursor + duration
        in_hours = _within_work_hours(cursor, candidate_end)
        if in_hours:
            clashes = find_overlaps(session, cursor, candidate_end, exclude_id, owner_id)
            if not clashes:
                return cursor
            cursor = cursor + SLOT_STEP
        else:
            # 跳到次日工作时段开始
            next_day = (cursor + timedelta(days=1)).date()
            cursor = datetime.combine(next_day, WORK_START)
    return None


def check_conflict(
    session: Session,
    start_at: datetime,
    end_at: datetime,
    exclude_id: Optional[int] = None,
    owner_id: Optional[int] = None,
) -> dict:
    """综合检测：返回是否冲突、冲突事件、建议时段。

    返回：
        {
            "has_conflict": bool,
            "conflicts": [event.to_dict(), ...],
            "suggestion": ISO字符串 或 None,
        }
    """
    conflicts = find_overlaps(session, start_at, end_at, exclude_id, owner_id)
    if not conflicts:
        return {"has_conflict": False, "conflicts": [], "suggestion": None}

    suggestion = suggest_free_slot(session, start_at, end_at, exclude_id, owner_id)
    suggestion_iso = None
    if suggestion is not None:
        suggestion_iso = suggestion.isoformat()
    return {
        "has_conflict": True,
        "conflicts": [ev.to_dict() for ev in conflicts],
        "suggestion": suggestion_iso,
    }
