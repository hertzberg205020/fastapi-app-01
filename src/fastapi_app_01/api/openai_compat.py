import json
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from fastapi_app_01.config import settings
from fastapi_app_01.core import llm
from fastapi_app_01.schemas.openai import ChatCompletionRequest, ChatMessage

router = APIRouter(prefix="/v1")

# Anthropic stop_reason → OpenAI finish_reason
_FINISH = {"end_turn": "stop", "stop_sequence": "stop", "max_tokens": "length"}


def _split(messages: list[ChatMessage]) -> tuple[str | None, list[dict]]:
    """system role 併成 Anthropic 頂層 system;其餘原順序映成 messages。"""
    system = "\n\n".join(m.content for m in messages if m.role == "system") or None
    convo = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
    return system, convo


@router.get("/models")
def list_models() -> dict:
    return {
        "object": "list",
        "data": [
            {"id": settings.anthropic_model, "object": "model", "created": 0, "owned_by": "anthropic"},
        ],
    }


@router.post("/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    system, convo = _split(req.messages)
    cid, created, model = f"chatcmpl-{uuid.uuid4().hex}", int(time.time()), settings.anthropic_model

    if req.stream:
        async def gen() -> AsyncIterator[str]:
            head = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                    "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
            yield f"data: {json.dumps(head)}\n\n"
            async for text in llm.stream_chat(convo, system):
                chunk = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                         "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            tail = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            yield f"data: {json.dumps(tail)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    r = await llm.complete_chat(convo, system)
    return {
        "id": cid, "object": "chat.completion", "created": created, "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": r.text},
                     "finish_reason": _FINISH.get(r.stop_reason, "stop")}],
        "usage": {"prompt_tokens": r.input_tokens, "completion_tokens": r.output_tokens,
                  "total_tokens": r.input_tokens + r.output_tokens},
    }
