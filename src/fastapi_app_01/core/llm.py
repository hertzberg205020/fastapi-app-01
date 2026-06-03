from anthropic import AsyncAnthropic

from fastapi_app_01.config import settings

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)


async def answer(question: str) -> str:
    """把問題丟給 Claude,回一段純文字。本迭代:單輪、無 system prompt、無歷史。"""
    msg = await _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": question}],
    )
    # 非串流回應:內容在 content blocks,第一塊取 text。
    return msg.content[0].text
