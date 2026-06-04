from collections.abc import AsyncIterator
from dataclasses import dataclass

from anthropic import AsyncAnthropic

from fastapi_app_01.config import settings

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)


async def stream_answer(question: str) -> AsyncIterator[str]:
    """把問題丟給 Claude,逐段 yield 文字 delta。本迭代:單輪、無 system prompt、無歷史。"""
    async with _client.messages.stream(
        model=settings.anthropic_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": question}],
    ) as stream:
        async for text in stream.text_stream:
            yield text


# ---- 多輪 + system(迭代 3,給 OpenAI 相容 /v1 用)----
# core/llm 只收「已轉好的 anthropic messages + system」,與 OpenAI / 傳輸無關;
# OpenAI↔Anthropic 的轉接放在 api/openai_compat.py。


@dataclass
class ChatResult:
    text: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int


def _kwargs(messages: list[dict], system: str | None) -> dict:
    kw = {"model": settings.anthropic_model, "max_tokens": 1024, "messages": messages}
    if system:
        kw["system"] = system  # 無 system 就不傳該參數
    return kw


async def stream_chat(messages: list[dict], system: str | None = None) -> AsyncIterator[str]:
    """多輪串流:逐段 yield 文字 delta。"""
    async with _client.messages.stream(**_kwargs(messages, system)) as stream:
        async for text in stream.text_stream:
            yield text


async def complete_chat(messages: list[dict], system: str | None = None) -> ChatResult:
    """多輪非串流:回完整文字 + stop_reason + token 用量。"""
    msg = await _client.messages.create(**_kwargs(messages, system))
    return ChatResult(
        text=msg.content[0].text,
        stop_reason=msg.stop_reason,
        input_tokens=msg.usage.input_tokens,
        output_tokens=msg.usage.output_tokens,
    )
