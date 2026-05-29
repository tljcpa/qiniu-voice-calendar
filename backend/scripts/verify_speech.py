"""Azure Speech 真实联调脚本（一次性运行，建议在 Azure VM）。

验证两件事：
1. 短时 token 能签发（httpx，轻量，本机也能跑）。
2. 服务端 TTS 能合成音频（需 azure-cognitiveservices-speech，体积大，建议 VM）。

用法：
    source /root/七牛云比赛/.secrets/shared.env
    cd /opt/voice-calendar/backend && python scripts/verify_speech.py

成功：打印 token 前缀 + region，并把合成音频写到 /tmp/tts_demo.wav。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.speech import get_token_service, synthesize_speech  # noqa: E402


def main() -> int:
    token_info = get_token_service().get_token()
    token = token_info["token"]
    print(f"token 前缀: {token[:16]}...  region: {token_info['region']}")

    audio = synthesize_speech("已为你添加明天下午三点的产品评审会，需要修改吗？")
    out = Path("/tmp/tts_demo.wav")
    out.write_bytes(audio)
    print(f"TTS 合成 {len(audio)} 字节 -> {out}")
    print("OK: Azure Speech 联调通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
