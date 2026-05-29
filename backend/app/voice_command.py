"""语音指令编排（后端大脑，见 docs/复盘.md D-16）。

把一句话指令的文本，经"意图解析 → 时间解析 → CRUD/冲突/澄清"串成端到端动作，
并为每个分支生成自然中文 TTS 回应文案（语音闭环的关键，D-03）。

统一返回结构：
    {
        "intent": str,
        "ok": bool,                  # 动作是否成功执行
        "speech": str,               # 给 TTS 播报的回应文案
        "needs_clarification": bool, # 是否需要用户进一步澄清
        "clarification": str | None,
        "candidates": [event_dict],  # 歧义候选（供用户选择）
        "events": [event_dict],      # 受影响或查询到的事件
    }
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app import crud
from app.conflict import check_conflict
from app.intent_parser import parse_intent
from app.time_parser import parse_time


def _response(
    intent: str,
    speech: str,
    ok: bool = True,
    needs_clarification: bool = False,
    clarification: Optional[str] = None,
    candidates: Optional[list] = None,
    events: Optional[list] = None,
    pending_new_values: Optional[dict] = None,
) -> dict:
    """统一组装响应。

    pending_new_values：update 澄清时把待应用的新值一并回传，
    前端在下一轮 resolve 时原样带回，实现多轮澄清的指代消解。
    """
    return {
        "intent": intent,
        "ok": ok,
        "speech": speech,
        "needs_clarification": needs_clarification,
        "clarification": clarification,
        "candidates": candidates or [],
        "events": events or [],
        "pending_new_values": pending_new_values,
    }


def _fmt_dt(dt: datetime) -> str:
    """把 datetime 格式化成口语友好的中文（月日 + 时分）。"""
    return f"{dt.month}月{dt.day}日{dt.hour}点{dt.minute:02d}分"


def _day_range(dt: datetime):
    """取某 datetime 所在自然日的 [00:00, 23:59:59] 范围。"""
    start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    end = dt.replace(hour=23, minute=59, second=59, microsecond=0)
    return (start, end)


def _handle_add(parsed: dict, session: Session, now: datetime, force: bool) -> dict:
    """添加事件。无时间→澄清；冲突→默认不建并给建议；循环→建多个。"""
    title = parsed.get("title") or "新日程"
    time_expr = parsed.get("time_expr")
    if not time_expr:
        return _response(
            "add",
            speech=f"好的，{title}安排在什么时间？",
            ok=False,
            needs_clarification=True,
            clarification="缺少时间",
        )

    time_result = parse_time(time_expr, now=now)
    if not time_result["ok"]:
        return _response(
            "add",
            speech=f"没太听清时间，{title}安排在什么时候？",
            ok=False,
            needs_clarification=True,
            clarification="时间无法解析",
        )

    datetimes = [datetime.fromisoformat(s) for s in time_result["datetimes"]]
    location = parsed.get("location")
    attendees = parsed.get("attendees") or []

    # 单个事件且冲突且未强制：不创建，给建议
    if len(datetimes) == 1 and not force:
        start = datetimes[0]
        end = start + timedelta(hours=1)
        conflict = check_conflict(session, start, end)
        if conflict["has_conflict"]:
            clash_title = conflict["conflicts"][0]["title"]
            speech = f"这个时间和你的{clash_title}冲突了"
            if conflict["suggestion"]:
                sug = datetime.fromisoformat(conflict["suggestion"])
                speech += f"，要不要改到{_fmt_dt(sug)}？"
            else:
                speech += "，换个时间好吗？"
            return _response(
                "add",
                speech=speech,
                ok=False,
                needs_clarification=True,
                clarification="时间冲突",
                candidates=conflict["conflicts"],
            )

    # 创建（循环则多个）；若指定提前提醒分钟数，挂提醒
    reminder_min = parsed.get("reminder_before_minutes")
    created = []
    for start in datetimes:
        ev = crud.create_event(
            session,
            title=title,
            start_at=start,
            location=location,
            attendees=attendees,
        )
        if isinstance(reminder_min, int) and reminder_min > 0:
            crud.create_reminder(
                session,
                event_id=ev.id,
                remind_at=start - timedelta(minutes=reminder_min),
            )
        created.append(ev.to_dict())

    if len(created) == 1:
        start = datetimes[0]
        speech = f"已添加，{_fmt_dt(start)}的{title}"
        if location:
            speech += f"，地点{location}"
        if isinstance(reminder_min, int) and reminder_min > 0:
            speech += f"，会提前{reminder_min}分钟提醒你"
    else:
        speech = f"已添加{len(created)}个{title}日程"
    return _response("add", speech=speech, events=created)


def _handle_view(parsed: dict, session: Session, now: datetime) -> dict:
    """查询事件。按 time_expr 推导日范围，无则默认今天。"""
    time_expr = parsed.get("time_expr")
    if time_expr:
        tr = parse_time(time_expr, now=now)
        if tr["ok"]:
            anchor = datetime.fromisoformat(tr["datetimes"][0])
        else:
            anchor = now
    else:
        anchor = now

    start, end = _day_range(anchor)
    events = crud.list_events(session, start=start, end=end)
    event_dicts = [e.to_dict() for e in events]

    when = "今天" if anchor.date() == now.date() else f"{anchor.month}月{anchor.day}日"
    if not events:
        speech = f"{when}没有安排"
    else:
        parts = [f"{e.start_at.hour}点的{e.title}" for e in events]
        speech = f"{when}有{len(events)}个安排：" + "、".join(parts)
    return _response("view", speech=speech, events=event_dicts)


def _handle_delete(parsed: dict, session: Session, now: datetime) -> dict:
    """删除事件。按目标定位：0→没找到，1→删，≥2→列候选澄清。"""
    keyword = parsed.get("target_query") or parsed.get("title")
    # 若带时间，叠加当天范围缩小匹配
    start = end = None
    time_expr = parsed.get("time_expr")
    if time_expr:
        tr = parse_time(time_expr, now=now)
        if tr["ok"]:
            start, end = _day_range(datetime.fromisoformat(tr["datetimes"][0]))

    matches = crud.find_events(session, keyword=keyword, start=start, end=end)
    if not matches:
        return _response(
            "delete",
            speech=f"没有找到{keyword or '相关'}的日程",
            ok=False,
        )
    if len(matches) > 1:
        candidates = [e.to_dict() for e in matches]
        parts = [f"{e.start_at.month}月{e.start_at.day}日{e.start_at.hour}点的{e.title}" for e in matches]
        speech = f"找到{len(matches)}个：" + "、".join(parts) + "，要删哪一个？"
        return _response(
            "delete",
            speech=speech,
            ok=False,
            needs_clarification=True,
            clarification="目标不唯一",
            candidates=candidates,
        )

    target = matches[0]
    info = target.to_dict()
    crud.delete_event(session, target.id)
    return _response("delete", speech=f"已删除{target.title}", events=[info])


def _handle_update(parsed: dict, session: Session, now: datetime) -> dict:
    """修改事件。定位目标后应用新值（支持改到具体时间或整体平移）。"""
    keyword = parsed.get("target_query") or parsed.get("title")
    new_values = parsed.get("new_values") or {}
    matches = crud.find_events(session, keyword=keyword)
    if not matches:
        return _response("update", speech=f"没有找到{keyword or '相关'}的日程", ok=False)
    if len(matches) > 1:
        candidates = [e.to_dict() for e in matches]
        parts = [f"{e.start_at.month}月{e.start_at.day}日{e.start_at.hour}点的{e.title}" for e in matches]
        speech = f"找到{len(matches)}个：" + "、".join(parts) + "，要改哪一个？"
        return _response(
            "update",
            speech=speech,
            ok=False,
            needs_clarification=True,
            clarification="目标不唯一",
            candidates=candidates,
            pending_new_values=new_values,
        )

    return _apply_update(matches[0], new_values, session, now)


def _apply_update(target, new_values: dict, session: Session, now: datetime) -> dict:
    """对已确定的目标事件应用新值（改到具体时间或整体平移）。"""
    new_start = None

    # 优先用明确新时间表达
    new_time_expr = new_values.get("time_expr")
    if new_time_expr:
        tr = parse_time(new_time_expr, now=now)
        if tr["ok"]:
            new_start = datetime.fromisoformat(tr["datetimes"][0])

    # 否则尝试平移（往后/往前 N 小时）——简化解析
    if new_start is None:
        shift = new_values.get("shift")
        if shift:
            delta = _parse_shift(shift)
            if delta is not None:
                new_start = target.start_at + delta

    if new_start is None:
        return _response(
            "update",
            speech="要把它改到什么时间？",
            ok=False,
            needs_clarification=True,
            clarification="缺少新时间",
        )

    duration = timedelta(hours=1)
    if target.end_at is not None:
        duration = target.end_at - target.start_at
    crud.update_event(
        session, target.id, start_at=new_start, end_at=new_start + duration
    )
    updated = crud.get_event(session, target.id)
    return _response(
        "update",
        speech=f"已把{target.title}改到{_fmt_dt(new_start)}",
        events=[updated.to_dict()],
    )


# 序数词 → 索引（支持"第一个/头一个/最后一个/第2个"等）
_ORDINAL = {
    "第一": 0, "第1": 0, "头一": 0, "第一个": 0, "头个": 0, "首个": 0,
    "第二": 1, "第2": 1, "第三": 2, "第3": 2,
    "第四": 3, "第4": 3, "第五": 4, "第5": 4,
}

# 时段 → 小时区间（用于"下午那个"匹配候选）
_PERIOD_RANGE = {
    "凌晨": (0, 5), "早上": (5, 9), "早晨": (5, 9), "上午": (5, 12),
    "中午": (11, 13), "下午": (12, 18), "傍晚": (17, 19),
    "晚上": (18, 24), "夜里": (18, 24),
}


def resolve_selection(text: str, candidates: list) -> Optional[int]:
    """从用户的指代话术里，确定性地选出候选事件的下标。

    candidates 为 event dict 列表（含 title / start_at）。
    依次尝试：序数（第一个）→ 末位（最后）→ 时段（下午那个）→ 标题关键词。
    选不出唯一返回 None（让上层再问一次）。
    """
    if not candidates:
        return None

    # 1) 末位
    if "最后" in text:
        return len(candidates) - 1

    # 2) 序数（长 key 优先，避免"第一" 命中"第十一"之类）
    for key in sorted(_ORDINAL, key=len, reverse=True):
        if key in text:
            idx = _ORDINAL[key]
            if 0 <= idx < len(candidates):
                return idx

    # 3) 时段：命中某时段且恰好一个候选落在区间内
    for period, (lo, hi) in _PERIOD_RANGE.items():
        if period in text:
            hits = []
            for i, c in enumerate(candidates):
                hour = datetime.fromisoformat(c["start_at"]).hour
                if lo <= hour < hi:
                    hits.append(i)
            if len(hits) == 1:
                return hits[0]

    # 4) 标题关键词：双向子串匹配（"客户对接那个"含标题；"聚餐"是"部门聚餐"的子串）
    title_hits = []
    for i, c in enumerate(candidates):
        title = c.get("title") or ""
        if not title:
            continue
        if title in text or (len(text) >= 2 and text in title):
            title_hits.append(i)
    if len(title_hits) == 1:
        return title_hits[0]

    return None


def handle_resolve(
    text: str,
    intent: str,
    candidates: list,
    session: Session,
    now: Optional[datetime] = None,
    new_values: Optional[dict] = None,
) -> dict:
    """多轮澄清的第二步：根据用户指代从候选里选定目标并执行。

    candidates 是上一轮 clarify 返回的候选 event dict 列表。
    选不出则再次追问。
    """
    if now is None:
        now = datetime.now()

    idx = resolve_selection(text, candidates)
    if idx is None:
        return _response(
            intent,
            speech="还是没听清是哪一个，可以说“第一个”或说出它的时间段",
            ok=False,
            needs_clarification=True,
            clarification="指代仍不明确",
            candidates=candidates,
            pending_new_values=new_values,
        )

    chosen = candidates[idx]
    event = crud.get_event(session, chosen["id"])
    if event is None:
        return _response(intent, speech="这个日程已经不存在了", ok=False)

    if intent == "delete":
        info = event.to_dict()
        crud.delete_event(session, event.id)
        return _response("delete", speech=f"已删除{event.title}", events=[info])

    if intent == "update":
        return _apply_update(event, new_values or {}, session, now)

    return _response(intent, speech="好的", ok=False)


def _parse_shift(shift: str) -> Optional[timedelta]:
    """把"往后一小时""提前半小时"这类平移描述转成 timedelta。简化版。"""
    from app.time_parser import zh_to_int
    import re

    backward = ("后" in shift) or ("推迟" in shift) or ("晚" in shift)
    forward = ("前" in shift) or ("提前" in shift) or ("早" in shift)

    hours = 0.0
    m = re.search(r"([0-9一二两三四五六七八九十]+|半)?\s*(?:个)?\s*小时", shift)
    if m:
        token = m.group(1)
        if token == "半" or token is None:
            hours = 0.5 if token == "半" else 1.0
        else:
            val = zh_to_int(token)
            if val is not None:
                hours = float(val)
    mm = re.search(r"([0-9一二两三四五六七八九十]+|半)\s*分", shift)
    minutes = 0.0
    if mm:
        token = mm.group(1)
        if token == "半":
            minutes = 30.0
        else:
            val = zh_to_int(token)
            if val is not None:
                minutes = float(val)

    total = timedelta(hours=hours, minutes=minutes)
    if total == timedelta(0):
        return None
    if forward and not backward:
        return -total
    return total


def handle_command(
    text: str,
    session: Session,
    now: Optional[datetime] = None,
    llm=None,
    force: bool = False,
) -> dict:
    """编排入口：一句话指令 → 结构化动作 + TTS 回应。

    参数：
        text: 用户原话（ASR 文本）。
        session: 数据库会话。
        now: 参考时间，默认当前；测试传固定值。
        llm: 注入的 LLM provider（测试用假对象）。
        force: 冲突时是否强制创建。
    """
    if now is None:
        now = datetime.now()

    parsed = parse_intent(text, now_iso=now.isoformat(), llm=llm)
    intent = parsed["intent"]

    if intent == "add":
        return _handle_add(parsed, session, now, force)
    if intent == "view":
        return _handle_view(parsed, session, now)
    if intent == "delete":
        return _handle_delete(parsed, session, now)
    if intent == "update":
        return _handle_update(parsed, session, now)
    if intent == "clarify":
        question = parsed.get("clarification") or "能再说详细一点吗？"
        return _response(
            "clarify",
            speech=question,
            ok=False,
            needs_clarification=True,
            clarification=question,
        )
    # unknown
    return _response(
        "unknown",
        speech="抱歉，我没听懂，你可以说添加、删除或查看日程",
        ok=False,
    )
