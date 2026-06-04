import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from fastapi_app_01.core import llm
from fastapi_app_01.schemas.chat import ChatRequest

router = APIRouter()


async def _sse(question: str) -> AsyncIterator[str]:
    """把純文字 delta 逐段包成 SSE 事件,結尾送 [DONE]。"""
    async for text in llm.stream_answer(question):
        yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(_sse(req.question), media_type="text/event-stream")
