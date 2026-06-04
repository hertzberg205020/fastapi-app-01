from collections.abc import AsyncIterator

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
