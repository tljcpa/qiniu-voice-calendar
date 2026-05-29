"""语音指令 API。

POST /api/voice/command：接收 ASR 识别出的文本，编排意图解析→时间→动作，
返回执行结果与 TTS 回应文案。这是语音闭环的后端核心入口。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.llm_provider import LLMError, get_llm
from app.voice_command import handle_command

router = APIRouter(prefix="/api/voice", tags=["voice"])


class CommandRequest(BaseModel):
    text: str
    # 冲突时是否强制创建（用户坚持原时间）
    force: bool = False


@router.post("/command")
def command(body: CommandRequest, session: Session = Depends(get_session)) -> dict:
    """处理一条语音指令文本。"""
    try:
        llm = get_llm()
    except LLMError as exc:
        return {
            "intent": "unknown",
            "ok": False,
            "speech": "语音助手暂时不可用，请稍后再试",
            "needs_clarification": False,
            "clarification": None,
            "candidates": [],
            "events": [],
            "error": str(exc),
        }
    return handle_command(body.text, session=session, llm=llm, force=body.force)
