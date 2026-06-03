from fastapi import FastAPI

from fastapi_app_01.api.chat import router as chat_router
from fastapi_app_01.config import settings

app = FastAPI()
app.include_router(chat_router)


@app.get("/")
def read_root():
    return {"message": "Hello World"}


@app.get("/health")
def health():
    # database_url / redis_url are optional in iteration 1 (no DB yet), so we
    # report whether they're configured rather than parsing connection details.
    return {
        "database_configured": bool(settings.database_url),
        "redis_configured": bool(settings.redis_url),
        "model": settings.anthropic_model,
    }


if __name__ == "__main__":
    from fastapi_app_01 import main

    main()
