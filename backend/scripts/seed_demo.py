"""重置并灌入"相对当天"的演示数据，供 demo 录制随时就绪。

为什么相对当天：固定日期的种子随比赛日推移会变成"过去"，导致"今天/明天/本周"
查询演示不出内容。本脚本按 now 计算偏移，任何一天跑都得到合理的当日/次日/本周日程。

用法（在能访问后端的机器上，如 Azure VM）：
    python scripts/seed_demo.py                 # 默认 http://127.0.0.1:8081
    BASE=https://voice.qiniu.zdwktlj.top python scripts/seed_demo.py

仅用标准库（urllib），无额外依赖。先清空现有事件，再灌入新数据。
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta

BASE = os.getenv("BASE", "http://127.0.0.1:8081")


def _req(method: str, path: str, body=None):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read().decode("utf-8")
        if raw:
            return json.loads(raw)
        return None


def _at(base_day: datetime, day_offset: int, hour: int, minute: int) -> str:
    d = base_day + timedelta(days=day_offset)
    return d.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()


def main() -> int:
    now = datetime.now()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # 清空现有事件
    existing = _req("GET", "/api/events") or []
    for ev in existing:
        _req("DELETE", f"/api/events/{ev['id']}")
    print(f"已清空 {len(existing)} 个旧事件")

    # 相对当天的演示日程：今天 2 个、明天 1 个、后天 1 个、本周内再 1 个
    events = [
        {"title": "产品评审会", "start_at": _at(today, 0, 15, 0),
         "location": "会议室A", "attendees": ["小王"]},
        {"title": "客户对接", "start_at": _at(today, 0, 17, 30)},
        {"title": "团队周会", "start_at": _at(today, 1, 10, 0)},
        {"title": "牙医复诊", "start_at": _at(today, 2, 9, 30)},
        {"title": "项目复盘", "start_at": _at(today, 3, 14, 0)},
    ]
    for e in events:
        _req("POST", "/api/events", e)
    print(f"已灌入 {len(events)} 个演示事件（相对今天 {today.date()}）")
    print(f"验证：当前共 {len(_req('GET', '/api/events') or [])} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
