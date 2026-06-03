from fastapi import APIRouter

from fastapi_app_01.core import llm
from fastapi_app_01.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    return ChatResponse(answer=await llm.answer(req.question))
