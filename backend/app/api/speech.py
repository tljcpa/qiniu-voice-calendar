"""语音相关 API 路由。

/api/speech/token：浏览器 Azure JS SDK 用来初始化识别器/合成器的短时 token。
前端拿到 {token, region} 后直连 Azure，全程不接触订阅 key。
"""

from fastapi import APIRouter, HTTPException

from app.speech import SpeechError, get_token_service

router = APIRouter(prefix="/api/speech", tags=["speech"])


@router.post("/token")
def issue_token() -> dict:
    """签发短时 Azure Speech token。

    成功返回 {token, region}；未配置 key 或上游失败返回 503，
    便于前端据此降级到浏览器原生 Web Speech API。
    """
    try:
        return get_token_service().get_token()
    except SpeechError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
