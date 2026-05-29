"""语音指令 API。

POST /api/voice/command：接收 ASR 识别出的文本，编排意图解析→时间→动作，
返回执行结果与 TTS 回应文案。这是语音闭环的后端核心入口。
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_session
from app.llm_provider import LLMError, get_llm
from app.voice_command import handle_command, handle_confirm, handle_resolve

router = APIRouter(prefix="/api/voice", tags=["voice"])


class CommandRequest(BaseModel):
    text: str
    # 冲突时是否强制创建（用户坚持原时间）
    force: bool = False


class ResolveRequest(BaseModel):
    """多轮澄清第二步：带上一轮的待定意图与候选，由用户指代选定。"""

    text: str
    intent: str
    candidates: list
    new_values: dict | None = None


class ConfirmRequest(BaseModel):
    """冲突确认：带上一轮 add 冲突回传的 pending_conflict 与用户决定。"""

    data: dict
    # True=接受建议时间；False=坚持原时间强建
    accept_suggestion: bool


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


@router.post("/resolve")
def resolve(body: ResolveRequest, session: Session = Depends(get_session)) -> dict:
    """多轮澄清第二步：用户指代（“第一个”“下午那个”）选定候选并执行。

    纯确定性选择，不需 LLM，故不依赖凭证。
    """
    return handle_resolve(
        body.text,
        intent=body.intent,
        candidates=body.candidates,
        session=session,
        new_values=body.new_values,
    )


@router.post("/confirm")
def confirm(body: ConfirmRequest, session: Session = Depends(get_session)) -> dict:
    """冲突后的对话决定：接受建议时间或坚持原时间。纯确定性，不需 LLM。"""
    return handle_confirm(
        body.data, accept_suggestion=body.accept_suggestion, session=session
    )
