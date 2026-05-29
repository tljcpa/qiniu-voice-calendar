"""中文时间解析测试集（30+ 表达式）。

参考时间固定为 2026-05-29（周五）10:00，保证结果可复现。
纯规则层，不触网，本机可跑（遵 D-12）。覆盖率数据用于答辩（复盘 §4）。
"""

from datetime import datetime

import pytest

from app.time_parser import parse_time, zh_to_int

NOW = datetime(2026, 5, 29, 10, 0)  # 周五


def _first(expr):
    """解析并返回第一个 datetime 的 ISO（不含循环展开的多结果）。"""
    r = parse_time(expr, now=NOW)
    assert r["ok"], f"未解析: {expr} -> {r}"
    return r["datetimes"][0]


# ---------- 中文数字 ----------

@pytest.mark.parametrize("text,expected", [
    ("三", 3), ("十", 10), ("十五", 15), ("二十", 20),
    ("二十三", 23), ("3", 3), ("30", 30), ("两", 2),
])
def test_zh_to_int(text, expected):
    assert zh_to_int(text) == expected


# ---------- 相对天 + 时刻 ----------

@pytest.mark.parametrize("expr,expected", [
    ("今天下午三点", "2026-05-29T15:00:00"),
    ("明天下午三点", "2026-05-30T15:00:00"),
    ("明天上午九点", "2026-05-30T09:00:00"),
    ("后天晚上八点", "2026-05-31T20:00:00"),
    ("大后天中午", "2026-06-01T12:00:00"),
    ("明天早上九点半", "2026-05-30T09:30:00"),
    ("明天下午三点一刻", "2026-05-30T15:15:00"),
    ("明天下午三点三刻", "2026-05-30T15:45:00"),
    ("明天晚上七点二十", "2026-05-30T19:20:00"),
])
def test_relative_day_with_time(expr, expected):
    assert _first(expr) == expected


# ---------- 周内某天 + 周修饰 ----------

@pytest.mark.parametrize("expr,expected", [
    ("下周三下午三点", "2026-06-03T15:00:00"),
    ("下下周二上午十点", "2026-06-09T10:00:00"),
    ("这周六晚上七点", "2026-05-30T19:00:00"),
    ("周一上午九点", "2026-06-01T09:00:00"),   # 今天周五，本周一已过 → 下周一
    ("周日中午", "2026-05-31T12:00:00"),       # 本周日未过 → 本周日
    ("周六", "2026-05-30T09:00:00"),           # 未指时刻 → 默认 9 点
])
def test_weekday_with_modifier(expr, expected):
    assert _first(expr) == expected


# ---------- 明确年月日 ----------

@pytest.mark.parametrize("expr,expected", [
    ("六月十八号上午十点", "2026-06-18T10:00:00"),
    ("5月31号下午两点", "2026-05-31T14:00:00"),
    ("明年一月一号", "2027-01-01T09:00:00"),
    ("12月25日晚上八点", "2026-12-25T20:00:00"),
])
def test_explicit_date(expr, expected):
    assert _first(expr) == expected


def test_past_month_day_rolls_to_next_year():
    """5月1号 已过（今天5/29）→ 滚到明年。"""
    assert _first("五月一号下午三点") == "2027-05-01T15:00:00"


# ---------- 相对偏移 ----------

@pytest.mark.parametrize("expr,expected", [
    ("三天后下午三点", "2026-06-01T15:00:00"),
    ("两天后", "2026-05-31T09:00:00"),
    ("一周后上午十点", "2026-06-05T10:00:00"),
])
def test_relative_offset(expr, expected):
    assert _first(expr) == expected


# ---------- 只有时刻（无日期） ----------

def test_clock_only_future_today():
    """下午三点：今天 15 点还没过（现在 10 点）→ 今天。"""
    assert _first("下午三点") == "2026-05-29T15:00:00"


def test_clock_only_past_rolls_tomorrow():
    """早上八点：今天 8 点已过 → 明天。"""
    assert _first("早上八点") == "2026-05-30T08:00:00"


# ---------- 循环展开 ----------

def test_recurring_weekdays():
    """每周一三五早上九点 → 多个时间点，标记 is_recurring。"""
    r = parse_time("每周一三五早上九点", now=NOW)
    assert r["ok"]
    assert r["is_recurring"] is True
    assert len(r["datetimes"]) >= 3
    # 第一批应包含 6/1(周一) 9点
    assert "2026-06-01T09:00:00" in r["datetimes"]
    assert "2026-06-03T09:00:00" in r["datetimes"]
    assert "2026-06-05T09:00:00" in r["datetimes"]


def test_next_week_multi_weekday():
    """下周一三五 上午九点 → 恰好下周这三天（非循环）。"""
    r = parse_time("下周一三五上午九点", now=NOW)
    assert r["ok"]
    assert r["is_recurring"] is False
    assert r["datetimes"] == [
        "2026-06-01T09:00:00",
        "2026-06-03T09:00:00",
        "2026-06-05T09:00:00",
    ]


# ---------- 失败与方法标记 ----------

def test_unparseable_returns_not_ok():
    r = parse_time("某个随便的时候", now=NOW)
    assert r["ok"] is False
    assert r["method"] == "none"


def test_method_is_rule_for_common_expr():
    r = parse_time("明天下午三点", now=NOW)
    assert r["method"] == "rule"


def test_empty_expr():
    r = parse_time("", now=NOW)
    assert r["ok"] is False
