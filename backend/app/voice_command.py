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
from app.time_parser import _monday_of, parse_time


def _response(
    intent: str,
    speech: str,
    ok: bool = True,
    needs_clarification: bool = False,
    clarification: Optional[str] = None,
    candidates: Optional[list] = None,
    events: Optional[list] = None,
    pending_new_values: Optional[dict] = None,
    pending_conflict: Optional[dict] = None,
    resolve_intent: Optional[str] = None,
) -> dict:
    """统一组装响应。

    pending_new_values：update 澄清时把待应用的新值一并回传，
    前端在下一轮 resolve 时原样带回，实现多轮澄清的指代消解。
    pending_conflict：add 冲突时回传待建事件与建议时间，
    前端在用户答"好/就这个"时走 confirm，实现冲突的对话接受。
    resolve_intent：intent=clarify 但已列出候选时，告诉前端这一轮指代消解
    最终要执行的动作（delete/update），让前端对 clarify 也能建 pending。
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
        "pending_conflict": pending_conflict,
        "resolve_intent": resolve_intent,
    }


def _fmt_dt(dt: datetime) -> str:
    """把 datetime 格式化成口语友好的中文（月日 + 时分）。"""
    return f"{dt.month}月{dt.day}日{dt.hour}点{dt.minute:02d}分"


def _day_range(dt: datetime):
    """取某 datetime 所在自然日的 [00:00, 23:59:59] 范围。"""
    start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    end = dt.replace(hour=23, minute=59, second=59, microsecond=0)
    return (start, end)


def _month_range(year: int, month: int, label: str):
    """取某年某月的 [首日00:00, 月末23:59:59] 范围。返回 (start, end, label, True)。"""
    start = datetime(year, month, 1)
    if month < 12:
        ny, nm = year, month + 1
    else:
        ny, nm = year + 1, 1
    end = datetime(ny, nm, 1) - timedelta(seconds=1)
    return (start, end, label, True)


def _create_one(session, title, start, location, attendees, reminder_min, owner_id=None):
    """创建单个事件，并按需挂提醒。供 add 与冲突确认复用。"""
    ev = crud.create_event(
        session,
        title=title,
        start_at=start,
        location=location,
        attendees=attendees or [],
        owner_id=owner_id,
    )
    if isinstance(reminder_min, int) and reminder_min > 0:
        crud.create_reminder(
            session,
            event_id=ev.id,
            remind_at=start - timedelta(minutes=reminder_min),
        )
    return ev


def handle_confirm(data: dict, accept_suggestion: bool, session: Session, owner_id=None) -> dict:
    """冲突后用户的对话决定：接受建议时间 or 坚持原时间强建。

    data 为上一轮 add 冲突回传的 pending_conflict。
    accept_suggestion=True → 用 suggested_start；False → 用 original_start（强建）。
    """
    title = data.get("title") or "新日程"
    location = data.get("location")
    attendees = data.get("attendees") or []
    reminder_min = data.get("reminder_min")

    if accept_suggestion:
        start_iso = data.get("suggested_start")
        if not start_iso:
            return _response("add", speech="没有可用的建议时间，换个时间好吗？", ok=False)
    else:
        start_iso = data.get("original_start")

    if not start_iso:
        return _response("add", speech="信息不全，请重新说一次", ok=False)

    start = datetime.fromisoformat(start_iso)
    ev = _create_one(session, title, start, location, attendees, reminder_min, owner_id)
    if accept_suggestion:
        speech = f"好的，已改到{_fmt_dt(start)}的{title}"
    else:
        speech = f"已按原时间添加{_fmt_dt(start)}的{title}（注意有时间冲突）"
    return _response("add", speech=speech, events=[ev.to_dict()])


def _handle_add(parsed: dict, session: Session, now: datetime, force: bool, owner_id=None) -> dict:
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
    reminder_min = parsed.get("reminder_before_minutes")

    # 单个事件且冲突且未强制：不创建，给建议（回传 pending_conflict 供前端对话接受）
    if len(datetimes) == 1 and not force:
        start = datetimes[0]
        end = start + timedelta(hours=1)
        conflict = check_conflict(session, start, end, owner_id=owner_id)
        if conflict["has_conflict"]:
            clash_title = conflict["conflicts"][0]["title"]
            speech = f"这个时间和你的{clash_title}冲突了"
            suggested_iso = conflict["suggestion"]
            if suggested_iso:
                sug = datetime.fromisoformat(suggested_iso)
                speech += f"，要不要改到{_fmt_dt(sug)}？"
            else:
                speech += "，换个时间好吗？"
            pending_conflict = {
                "title": title,
                "location": location,
                "attendees": attendees,
                "reminder_min": reminder_min if isinstance(reminder_min, int) else None,
                "original_start": start.isoformat(),
                "suggested_start": suggested_iso,
            }
            return _response(
                "add",
                speech=speech,
                ok=False,
                needs_clarification=True,
                clarification="时间冲突",
                candidates=conflict["conflicts"],
                pending_conflict=pending_conflict,
            )

    # 创建（循环则多个）；若指定提前提醒分钟数，挂提醒
    created = []
    for start in datetimes:
        ev = _create_one(session, title, start, location, attendees, reminder_min, owner_id)
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


def _view_range(time_expr, now):
    """据时间表达推导查询范围，返回 (start, end, label, is_multiday)。

    支持：周（本周/下周/上周/下下周，不带具体星期几）、月（这个月/下个月）、
    单日（今天/明天/具体日期/带星期的"下周三"）。无表达 → 今天。
    """
    import re

    if not time_expr:
        s, e = _day_range(now)
        return (s, e, "今天", False)

    from app.time_parser import zh_to_int

    # 相对月：这个月/本月/下个月/下月/上个月/上月（必须有相对词，避免"六月"误判）
    rel = re.search(r"(这个|本|下个|下|上个|上)\s*月", time_expr)
    if rel:
        word = rel.group(1)
        offset = 0
        if word in ("下个", "下"):
            offset = 1
        elif word in ("上个", "上"):
            offset = -1
        y = now.year
        m = now.month + offset
        if m > 12:
            y, m = y + 1, m - 12
        elif m < 1:
            y, m = y - 1, m + 12
        label = {0: "这个月", 1: "下个月", -1: "上个月"}[offset]
        return _month_range(y, m, label)

    # 具体月份名："六月/6月有什么安排"（无具体日 → 整月范围）
    if not re.search(r"[日号]", time_expr):
        sm = re.search(r"([0-9一二三四五六七八九十]+)\s*月", time_expr)
        if sm:
            mv = zh_to_int(sm.group(1))
            if mv is not None and 1 <= mv <= 12:
                return _month_range(now.year, mv, f"{mv}月")

    # 周范围：(这|本|下下|下|上)?(周|星期|礼拜) 且后面不跟具体星期几
    wm = re.search(r"(这|本|下下|下|上)?\s*(?:周|星期|礼拜)(?![一二三四五六日天末])", time_expr)
    if wm:
        mod = wm.group(1)
        week_offset = 0
        if mod == "下":
            week_offset = 1
        elif mod == "下下":
            week_offset = 2
        elif mod == "上":
            week_offset = -1
        monday = _monday_of(now) + timedelta(weeks=week_offset)
        start = monday
        end = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
        label = {0: "本周", 1: "下周", 2: "下下周", -1: "上周"}.get(week_offset, "本周")
        return (start, end, label, True)

    # 单日：用 parse_time 的锚点
    tr = parse_time(time_expr, now=now)
    if tr["ok"]:
        anchor = datetime.fromisoformat(tr["datetimes"][0])
    else:
        anchor = now
    s, e = _day_range(anchor)
    if anchor.date() == now.date():
        label = "今天"
    else:
        label = f"{anchor.month}月{anchor.day}日"
    return (s, e, label, False)


def _handle_view(parsed: dict, session: Session, now: datetime, owner_id=None) -> dict:
    """查询事件。支持单日 / 本周下周 / 整月范围。"""
    time_expr = parsed.get("time_expr")
    start, end, label, is_multiday = _view_range(time_expr, now)
    events = crud.list_events(session, start=start, end=end, owner_id=owner_id)
    event_dicts = [e.to_dict() for e in events]

    if not events:
        speech = f"{label}没有安排"
    elif is_multiday:
        # 跨多天：带月日，避免歧义
        parts = [
            f"{e.start_at.month}月{e.start_at.day}日{e.start_at.hour}点的{e.title}"
            for e in events
        ]
        speech = f"{label}有{len(events)}个安排：" + "、".join(parts)
    else:
        parts = [f"{e.start_at.hour}点的{e.title}" for e in events]
        speech = f"{label}有{len(events)}个安排：" + "、".join(parts)
    return _response("view", speech=speech, events=event_dicts)


def _handle_delete(parsed: dict, session: Session, now: datetime, owner_id=None) -> dict:
    """删除事件。按目标定位：0→没找到，1→删，≥2→列候选澄清。"""
    keyword = parsed.get("target_query") or parsed.get("title")
    # 若带时间，叠加当天范围缩小匹配
    start = end = None
    time_expr = parsed.get("time_expr")
    if time_expr:
        tr = parse_time(time_expr, now=now)
        if tr["ok"]:
            start, end = _day_range(datetime.fromisoformat(tr["datetimes"][0]))

    matches = crud.find_events(session, keyword=keyword, start=start, end=end, owner_id=owner_id)
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
    crud.delete_event(session, target.id, owner_id=owner_id)
    return _response("delete", speech=f"已删除{target.title}", events=[info])


def _handle_update(parsed: dict, session: Session, now: datetime, owner_id=None) -> dict:
    """修改事件。定位目标后应用新值（支持改到具体时间或整体平移）。"""
    keyword = parsed.get("target_query") or parsed.get("title")
    new_values = parsed.get("new_values") or {}
    matches = crud.find_events(session, keyword=keyword, owner_id=owner_id)
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

    return _apply_update(matches[0], new_values, session, now, owner_id)


def _apply_update(target, new_values: dict, session: Session, now: datetime, owner_id=None) -> dict:
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
        session, target.id, start_at=new_start, end_at=new_start + duration, owner_id=owner_id
    )
    updated = crud.get_event(session, target.id, owner_id=owner_id)
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
    owner_id=None,
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
    event = crud.get_event(session, chosen["id"], owner_id=owner_id)
    if event is None:
        return _response(intent, speech="这个日程已经不存在了", ok=False)

    if intent == "delete":
        info = event.to_dict()
        crud.delete_event(session, event.id, owner_id=owner_id)
        return _response("delete", speech=f"已删除{event.title}", events=[info])

    if intent == "update":
        return _apply_update(event, new_values or {}, session, now, owner_id)

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


# 指代词/所有格（剥离后留下真正的内容关键词，如"那个会"/"我的会"→"会"）
_DEMONSTRATIVES = [
    "刚才那个", "之前那个", "刚才", "之前", "那一个", "这一个",
    "那个", "这个", "那场", "这场", "那次", "这次", "那条", "这条", "那",
    "我的", "你的", "他的", "她的", "咱的", "我",
]


def _strip_demonstratives(kw: Optional[str]) -> str:
    """从目标描述里剥掉纯指代词，留下内容关键词。"""
    if not kw:
        return ""
    out = kw
    for d in _DEMONSTRATIVES:
        out = out.replace(d, "")
    return out.strip()


def _infer_clarify_action(text: str) -> Optional[str]:
    """从原话推断澄清背后的动作：删除 / 修改 / 无法判断。"""
    for w in ("删", "取消", "去掉", "不要了", "清掉", "撤掉"):
        if w in text:
            return "delete"
    for w in ("改", "挪", "推迟", "提前", "换到", "换成", "调整", "移到"):
        if w in text:
            return "update"
    return None


def _handle_clarify(parsed: dict, text: str, session: Session, now: datetime, owner_id=None) -> dict:
    """澄清分支（修复纯指代断链）：

    LLM 对纯指代（如"把那个会删了"）返回 clarify。此处推断动作（删/改），
    剥离指代词得到内容关键词查库：唯一→直接执行；多个→列候选并带 resolve_intent
    让前端建 pending，用户可选"第一个"完成；0 个→没找到。
    无法判断动作（如缺时间的添加）→ 回原澄清问句。
    """
    action = _infer_clarify_action(text)
    if action in ("delete", "update"):
        keyword = _strip_demonstratives(parsed.get("target_query") or parsed.get("title"))
        matches = crud.find_events(session, keyword=keyword or None, owner_id=owner_id)
        new_values = parsed.get("new_values") or {}

        if len(matches) == 1:
            # 唯一候选 → 直接执行，不必再问
            target = matches[0]
            if action == "delete":
                info = target.to_dict()
                crud.delete_event(session, target.id, owner_id=owner_id)
                return _response("delete", speech=f"已删除{target.title}", events=[info])
            return _apply_update(target, new_values, session, now, owner_id)

        if len(matches) > 1:
            candidates = [e.to_dict() for e in matches]
            parts = [
                f"{e.start_at.month}月{e.start_at.day}日{e.start_at.hour}点的{e.title}"
                for e in matches
            ]
            verb = "删" if action == "delete" else "改"
            speech = f"找到{len(matches)}个：" + "、".join(parts) + f"，要{verb}哪一个？"
            return _response(
                "clarify",
                speech=speech,
                ok=False,
                needs_clarification=True,
                clarification="目标不唯一",
                candidates=candidates,
                resolve_intent=action,
                pending_new_values=new_values if action == "update" else None,
            )

        # 0 个匹配
        return _response(
            "clarify",
            speech=f"没有找到{keyword or '相关'}的日程",
            ok=False,
        )

    # 动作无法判断（如缺时间的添加）→ 原澄清问句
    question = parsed.get("clarification") or "能再说详细一点吗？"
    return _response(
        "clarify",
        speech=question,
        ok=False,
        needs_clarification=True,
        clarification=question,
    )


def handle_command(
    text: str,
    session: Session,
    now: Optional[datetime] = None,
    llm=None,
    force: bool = False,
    owner_id=None,
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

    # 空/纯空白输入：直接友好回应，不浪费一次 LLM 调用（识别静音/误触常见）
    if not text or not text.strip():
        return _response(
            "unknown",
            speech="没听清，请再说一次",
            ok=False,
        )

    parsed = parse_intent(text, now_iso=now.isoformat(), llm=llm)
    intent = parsed["intent"]

    if intent == "add":
        return _handle_add(parsed, session, now, force, owner_id)
    if intent == "view":
        return _handle_view(parsed, session, now, owner_id)
    if intent == "delete":
        return _handle_delete(parsed, session, now, owner_id)
    if intent == "update":
        return _handle_update(parsed, session, now, owner_id)
    if intent == "clarify":
        return _handle_clarify(parsed, text, session, now, owner_id)
    # unknown
    return _response(
        "unknown",
        speech="抱歉，我没听懂，你可以说添加、删除或查看日程",
        ok=False,
    )
