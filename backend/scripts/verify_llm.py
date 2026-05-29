"""LLM 抽象层真实联调脚本（一次性运行，非常驻服务）。

用途：在配好凭证的环境（推荐 Azure VM）确认 LLMProvider 真的能连通后端。
本机内存受限，常规验证用单元测试（tests/test_llm_provider.py）；
本脚本需要真实网络与凭证，建议在 VM 上跑：

    source /root/七牛云比赛/.secrets/shared.env
    cd /opt/voice-calendar/backend && python scripts/verify_llm.py

成功输出：主后端名 + 一次普通补全 + 一次 JSON 补全的结果。
"""

import sys
from pathlib import Path

# 允许直接 python scripts/verify_llm.py 运行（把 backend 加入 import 路径）。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm_provider import get_llm  # noqa: E402


def main() -> int:
    llm = get_llm()
    print(f"主后端: {llm.primary_name()}")

    text = llm.complete(
        [{"role": "user", "content": "用一句话介绍你自己"}],
        max_tokens=100,
    )
    print(f"普通补全: {text}")

    data = llm.complete_json(
        [
            {
                "role": "system",
                "content": "你是意图分类器，只返回 JSON。",
            },
            {
                "role": "user",
                "content": '把这句话分类：明天下午三点开会。返回 {"intent": "...", "title": "..."}',
            },
        ],
        max_tokens=200,
    )
    print(f"JSON 补全: {data}")
    print("OK: LLM 抽象层联调通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
