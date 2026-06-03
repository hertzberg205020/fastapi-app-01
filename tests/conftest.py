import os

# Gotcha: config.py builds Settings() at import time (anthropic_api_key is
# required) and llm.py builds AsyncAnthropic at import time. So a fake key must
# exist *before* the app is imported. conftest.py loads before the test modules,
# so setting it here at module top is early enough.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    """In-process client with Claude mocked at the llm.answer seam."""
    from fastapi_app_01.core import llm

    async def fake_answer(question: str) -> str:
        return f"stub answer for: {question}"

    monkeypatch.setattr(llm, "answer", fake_answer)

    from fastapi_app_01.main import app

    with TestClient(app) as c:
        yield c
