"""命令行端到端 demo（里程碑 M-02）。

把"文本指令 → 意图 → 时间 → CRUD/冲突/澄清 → TTS 回应文案"整条链路跑通，
不依赖前端与语音设备，用真实 LLM + 内存库验证后端大脑。

用法：
    source /root/七牛云比赛/.secrets/shared.env
    cd backend && python scripts/demo_cli.py            # 跑内置 demo 话术
    python scripts/demo_cli.py "明天下午三点开会"        # 跑指定指令

注意：调用真实 DeepSeek，是一次性脚本（非常驻服务）。
"""

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import Base, make_engine, make_session_factory  # noqa: E402
from app.llm_provider import get_llm  # noqa: E402
from app.voice_command import handle_command  # noqa: E402

# 固定参考时间，保证 demo 可复现（周五）
NOW = datetime(2026, 5, 29, 10, 0)

DEFAULT_SCRIPT = [
    "明天下午三点开产品评审会，叫上小王",
    "后天上午十点也有个客户对接",
    "今天有什么安排",
    "明天还有什么安排",
    "明天下午三点再加个电话会议",   # 与产品评审会冲突，应给建议
    "把产品评审会往后挪一个小时",
    "把客户对接删了",
    "今天天气怎么样",               # unknown
]


def main() -> int:
    engine = make_engine("sqlite://")
    import app.models  # noqa: F401

    Base.metadata.create_all(engine)
    session = make_session_factory(engine)()
    llm = get_llm()
    print(f"LLM 后端: {llm.primary_name()}    参考时间: {NOW.isoformat()}\n")

    commands = sys.argv[1:] if len(sys.argv) > 1 else DEFAULT_SCRIPT
    for text in commands:
        result = handle_command(text, session=session, now=NOW, llm=llm)
        flag = "OK" if result["ok"] else "需澄清/未执行"
        print(f"用户: {text}")
        print(f"  意图: {result['intent']}  [{flag}]")
        print(f"  回应: {result['speech']}")
        if result["events"]:
            for e in result["events"]:
                print(f"  事件: {e['start_at']}  {e['title']}")
        print()
    session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
