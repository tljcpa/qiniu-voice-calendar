"""意图解析 prompt 真实调试脚本（一次性运行，非常驻服务）。

对一组覆盖各意图的话术跑真实 LLM，人工核对解析是否符合预期，用于调 prompt。
本机可跑（只是若干次 API 调用，无常驻进程），需先 source 凭证。

用法：
    source /root/七牛云比赛/.secrets/shared.env
    cd backend && python scripts/tune_intent.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.intent_parser import parse_intent  # noqa: E402

# 覆盖 add/delete/view/update/clarify/批量/unknown 的测试话术
CASES = [
    "明天下午三点开产品评审会，叫上小王和小李，提前十分钟提醒我",
    "下周一三五上午九点都有晨会",
    "把我下午的客户对接往后挪一个小时",
    "今天还有什么安排",
    "周六的羽毛球取消了",
    "把那个会删掉",          # 期望 clarify（目标模糊）
    "帮我加个会",            # 期望 clarify（缺时间）
    "今天天气怎么样",        # 期望 unknown
]

NOW = "2026-05-30T09:00:00"


def main() -> int:
    for text in CASES:
        result = parse_intent(text, now_iso=NOW)
        print(f"\n输入: {text}")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
