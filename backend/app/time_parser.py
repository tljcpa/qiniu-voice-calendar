"""中文自然语言时间解析（亮点 3）。

把意图解析抽出的原始时间短语（如"下周三下午三点""每周一三五早上九点"）归一化为
ISO8601 日期时间。循环表达展开为多个具体时间点。

三层兜底（见 docs/复盘.md D-04、L-04）：
1. **规则层（主力）**：确定性解析中文日历表达，覆盖相对天/周内某天+周修饰/年月日/
   时间点/循环。这是工作马——日历时间表达高度模式化，规则确定、可测、零延迟。
2. **dateparser（边角兜底）**：标准数字日期等规则未命中的格式。实测中文能力很弱，仅兜底。
3. **LLM ISO（最后兜底，可选）**：农历、节假日等规则难穷举的表达，标低置信度。

返回结构统一：
    {
        "ok": bool,                 # 是否解析成功
        "datetimes": [ISO字符串...], # 解析出的时间点（循环为多个）
        "has_time": bool,           # 是否含具体时刻（否则仅日期，时刻取默认）
        "is_recurring": bool,       # 是否循环表达
        "method": "rule|dateparser|llm|none",
        "raw": 原始表达,
    }
"""

import re
from datetime import datetime, timedelta
from typing import Optional

# 未指定时刻时的默认小时（口语"明天开会"通常指白天，取 9 点比 0 点合理）。
DEFAULT_HOUR = 9
DEFAULT_MINUTE = 0
# 循环表达展开的周数horizon（demo 够用，避免无限生成）。
RECUR_WEEKS = 4


# ----------------- 中文数字 -----------------

_ZH_DIGIT = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}


def zh_to_int(text: str) -> Optional[int]:
    """把中文或阿拉伯数字串转成整数。支持 十/二十/二十三/十五 这类两位以内组合。

    解析不了返回 None。范围限定在日历用得到的两位数（分钟<60，日<32）。
    """
    if text is None:
        return None
    text = text.strip()
    if text == "":
        return None
    # 纯阿拉伯数字
    if text.isdigit():
        return int(text)

    # 含"十"的组合
    if "十" in text:
        left, _, right = text.partition("十")
        if left == "":
            tens = 1
        else:
            tens = _ZH_DIGIT.get(left)
            if tens is None:
                return None
        if right == "":
            ones = 0
        else:
            ones = _ZH_DIGIT.get(right)
            if ones is None:
                return None
        return tens * 10 + ones

    # 单个或多位纯中文数字（如"二三"少见，按逐位拼）
    total = 0
    for ch in text:
        digit = _ZH_DIGIT.get(ch)
        if digit is None:
            return None
        total = total * 10 + digit
    return total


# ----------------- 星期 -----------------

# 周一=0 ... 周日=6（与 datetime.weekday() 对齐）
_WEEKDAY_CHAR = {
    "一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5,
    "日": 6, "天": 6, "末": 6,
}


def _monday_of(d: datetime) -> datetime:
    """返回 d 所在周的周一（零点）。"""
    monday = d - timedelta(days=d.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


# ----------------- 时刻解析 -----------------

# 时段 → 是否需要给小时 +12（下午/晚上）
_PERIOD_PM = ("下午", "晚上", "傍晚", "夜里", "夜晚")
_PERIOD_AM = ("凌晨", "早上", "早晨", "上午", "清晨")


def _parse_clock(text: str):
    """从文本中解析时刻，返回 (hour, minute) 或 None。

    支持：三点 / 3点 / 三点半 / 三点一刻 / 三点三刻 / 三点十五(分) / 九点半，
    以及时段词（上午/下午/中午/晚上...）对 12 小时制的修正。
    """
    period_pm = None
    for p in _PERIOD_PM:
        if p in text:
            period_pm = True
            break
    if period_pm is None:
        for p in _PERIOD_AM:
            if p in text:
                period_pm = False
                break

    # 中午单独处理（约定 12 点）
    noon = "中午" in text

    # 匹配"X点"，点后的内容单独解析分钟（半/N刻/N分/裸数字）
    m = re.search(r"([0-9〇零一二两三四五六七八九十]+)\s*点(.*)", text)
    hour = None
    minute = 0
    if m:
        hour = zh_to_int(m.group(1))
        rest = m.group(2)
        if "半" in rest:
            minute = 30
        elif "刻" in rest:
            # N刻 = N*15（一刻=15，三刻=45）；只有"刻"按一刻
            mq = re.search(r"([0-9一二两三四]+)?\s*刻", rest)
            quarters = 1
            if mq is not None and mq.group(1):
                parsed = zh_to_int(mq.group(1))
                if parsed is not None:
                    quarters = parsed
            minute = quarters * 15
        else:
            mm = re.search(r"([0-9〇零一二两三四五六七八九十]+)\s*分?", rest)
            if mm is not None and mm.group(1):
                parsed = zh_to_int(mm.group(1))
                if parsed is not None and 0 <= parsed < 60:
                    minute = parsed
    elif noon:
        hour = 12

    if hour is None:
        return None

    # 12 小时制修正
    if period_pm is True and hour < 12:
        hour += 12
    if period_pm is False and hour == 12:
        # 上午十二点 罕见，按 0 点
        hour = 0
    if noon and hour == 12:
        pass

    if hour < 0 or hour > 23:
        return None
    if minute < 0 or minute > 59:
        return None
    return (hour, minute)


# ----------------- 日期解析（规则层核心） -----------------

_REL_DAY = {
    "今天": 0, "今儿": 0, "今日": 0,
    "明天": 1, "明儿": 1, "明日": 1,
    "后天": 2, "大后天": 3,
    "昨天": -1, "昨日": -1, "前天": -2,
}


def _extract_weekdays(text: str):
    """从含"周/星期/礼拜"的文本里提取 (week_offset, [weekday_ints], recurring)。

    week_offset：这/本=0，下=+1，下下=+2，上=-1，未带修饰=None（表示就近）。
    支持"周一三五"这种一次多个工作日。无星期表达返回 None。
    """
    m = re.search(r"(每)?\s*(这|本|下下|下|上)?\s*(?:周|星期|礼拜)([一二三四五六日天末]+)", text)
    if m is None:
        return None
    recurring = m.group(1) is not None
    modifier = m.group(2)
    days_chars = m.group(3)

    weekdays = []
    for ch in days_chars:
        wd = _WEEKDAY_CHAR.get(ch)
        if wd is not None and wd not in weekdays:
            weekdays.append(wd)
    if not weekdays:
        return None

    if modifier in ("这", "本"):
        week_offset = 0
    elif modifier == "下":
        week_offset = 1
    elif modifier == "下下":
        week_offset = 2
    elif modifier == "上":
        week_offset = -1
    else:
        week_offset = None
    return (week_offset, weekdays, recurring)


def _resolve_dates_by_weekday(now, week_offset, weekdays, recurring):
    """根据周修饰与星期列表，算出具体日期列表（date 部分，零点）。"""
    monday = _monday_of(now)
    results = []

    if recurring:
        # 循环：从本周起展开 RECUR_WEEKS 周的这些星期几（只取今天及以后）
        for w in range(0, RECUR_WEEKS):
            for wd in weekdays:
                d = monday + timedelta(days=wd, weeks=w)
                if d.date() >= now.date():
                    results.append(d)
        return results

    if week_offset is None:
        # 就近：每个星期几取今天及以后最近的一次
        for wd in weekdays:
            d = monday + timedelta(days=wd)
            if d.date() < now.date():
                d = d + timedelta(weeks=1)
            results.append(d)
        results.sort()
        return results

    # 指定周：本周/下周/下下周/上周 的这些星期几
    for wd in weekdays:
        d = monday + timedelta(days=wd, weeks=week_offset)
        results.append(d)
    results.sort()
    return results


def _resolve_explicit_date(text, now):
    """解析"X月X日/号"，可带"明年/今年"。返回单个 date（零点）或 None。"""
    m = re.search(r"([0-9〇零一二两三四五六七八九十]+)\s*月\s*([0-9〇零一二两三四五六七八九十]+)\s*(?:日|号)", text)
    if m is None:
        return None
    month = zh_to_int(m.group(1))
    day = zh_to_int(m.group(2))
    if month is None or day is None:
        return None
    if month < 1 or month > 12 or day < 1 or day > 31:
        return None

    year = now.year
    if "明年" in text:
        year += 1
    elif "今年" not in text:
        # 没指明年份：若该月日已过，滚到明年（符合"添加未来日程"直觉）
        try:
            candidate = now.replace(
                year=year, month=month, day=day,
                hour=0, minute=0, second=0, microsecond=0,
            )
        except ValueError:
            return None
        if candidate.date() < now.date():
            year += 1
    try:
        return now.replace(
            year=year, month=month, day=day,
            hour=0, minute=0, second=0, microsecond=0,
        )
    except ValueError:
        return None


def _resolve_relative_offset(text, now):
    """解析"N天后/N天前/N周后/下个月"等相对偏移。返回单个 date（零点）或 None。"""
    base = now.replace(hour=0, minute=0, second=0, microsecond=0)

    m = re.search(r"([0-9〇零一二两三四五六七八九十]+)\s*天\s*(后|以后|之后)", text)
    if m:
        n = zh_to_int(m.group(1))
        if n is not None:
            return base + timedelta(days=n)

    m = re.search(r"([0-9〇零一二两三四五六七八九十]+)\s*天\s*(前|以前)", text)
    if m:
        n = zh_to_int(m.group(1))
        if n is not None:
            return base - timedelta(days=n)

    m = re.search(r"([0-9〇零一二两三四五六七八九十]+)\s*(?:个)?\s*(?:周|星期|礼拜)\s*(后|以后|之后)", text)
    if m:
        n = zh_to_int(m.group(1))
        if n is not None:
            return base + timedelta(weeks=n)

    if "下个月" in text or "下月" in text:
        # 简化：+30 天近似；精确月份运算非 demo 重点
        return base + timedelta(days=30)

    return None


def _rule_parse(expr, now):
    """规则层主解析。成功返回 (date_list, has_time, is_recurring)，失败返回 None。"""
    # 时刻
    clock = _parse_clock(expr)
    if clock is not None:
        has_time = True
        hour, minute = clock
    else:
        has_time = False
        hour, minute = DEFAULT_HOUR, DEFAULT_MINUTE

    date_list = None
    is_recurring = False

    # 1) 相对天（今天/明天/后天...）。按 key 长度降序匹配，
    #    避免"后天"作为"大后天"子串被先命中。
    for key in sorted(_REL_DAY, key=len, reverse=True):
        if key in expr:
            offset = _REL_DAY[key]
            base = now.replace(hour=0, minute=0, second=0, microsecond=0)
            date_list = [base + timedelta(days=offset)]
            break

    # 2) 星期表达（含循环与多工作日）
    if date_list is None:
        wd_info = _extract_weekdays(expr)
        if wd_info is not None:
            week_offset, weekdays, recurring = wd_info
            is_recurring = recurring
            date_list = _resolve_dates_by_weekday(
                now, week_offset, weekdays, recurring
            )

    # 3) 明确年月日
    if date_list is None:
        d = _resolve_explicit_date(expr, now)
        if d is not None:
            date_list = [d]

    # 4) 相对偏移（N天后...）
    if date_list is None:
        d = _resolve_relative_offset(expr, now)
        if d is not None:
            date_list = [d]

    # 5) 只有时刻没有日期 → 默认今天（若该时刻已过则明天）
    if date_list is None and clock is not None:
        base = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if base <= now:
            base = base + timedelta(days=1)
        return ([base], True, False)

    if date_list is None:
        return None

    # 把时刻贴到每个日期上
    stamped = []
    for d in date_list:
        stamped.append(
            d.replace(hour=hour, minute=minute, second=0, microsecond=0)
        )
    return (stamped, has_time, is_recurring)


def _dateparser_parse(expr, now):
    """边角兜底：dateparser。实测中文能力弱，仅作补充。返回 [date] 或 None。"""
    try:
        import dateparser
    except ImportError:
        return None
    settings = {
        "RELATIVE_BASE": now,
        "PREFER_DATES_FROM": "future",
        "RETURN_AS_TIMEZONE_AWARE": False,
    }
    dt = dateparser.parse(expr, languages=["zh"], settings=settings)
    if dt is None:
        return None
    return [dt]


def parse_time(
    expr: str,
    now: Optional[datetime] = None,
    use_llm_fallback: bool = False,
    llm=None,
) -> dict:
    """解析中文时间表达为 ISO8601。

    参数：
        expr: 原始时间短语（来自意图解析的 time_expr）。
        now: 参考时间，默认当前。测试时传固定值保证可复现。
        use_llm_fallback: 规则与 dateparser 都失败时是否调 LLM 兜底。
        llm: 注入的 LLM provider（测试用）。
    """
    if now is None:
        now = datetime.now()
    raw = expr

    result = {
        "ok": False,
        "datetimes": [],
        "has_time": False,
        "is_recurring": False,
        "method": "none",
        "raw": raw,
    }
    if not expr:
        return result

    # 第 1 层：规则
    parsed = _rule_parse(expr, now)
    if parsed is not None:
        dates, has_time, is_recurring = parsed
        result.update(
            ok=True,
            datetimes=[d.isoformat() for d in dates],
            has_time=has_time,
            is_recurring=is_recurring,
            method="rule",
        )
        return result

    # 第 2 层：dateparser
    dp = _dateparser_parse(expr, now)
    if dp is not None:
        result.update(
            ok=True,
            datetimes=[d.isoformat() for d in dp],
            has_time=True,
            method="dateparser",
        )
        return result

    # 第 3 层：LLM ISO 兜底（可选）
    if use_llm_fallback:
        iso = _llm_parse(expr, now, llm)
        if iso is not None:
            result.update(
                ok=True, datetimes=[iso], has_time=True, method="llm"
            )
            return result

    return result


def _llm_parse(expr, now, llm):
    """LLM 兜底：让模型把异常表达转 ISO。返回单个 ISO 字符串或 None。"""
    if llm is None:
        from app.llm_provider import get_llm

        llm = get_llm()
    prompt = (
        f"当前时间是 {now.isoformat()}。把下面的中文时间表达转换成 ISO8601 日期时间，"
        f'只返回 JSON {{"datetime":"YYYY-MM-DDTHH:MM:SS"}}，无法确定返回 {{"datetime":null}}。\n'
        f"表达：{expr}"
    )
    try:
        data = llm.complete_json([{"role": "user", "content": prompt}])
    except Exception:  # noqa: BLE001
        return None
    value = data.get("datetime")
    if not value:
        return None
    return value
