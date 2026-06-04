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
    """In-process client with Claude mocked at the llm.stream_answer seam."""
    from fastapi_app_01.core import llm

    async def fake_stream(question: str):
        for chunk in ["stub ", "answer ", f"for: {question}"]:
            yield chunk

    monkeypatch.setattr(llm, "stream_answer", fake_stream)

    from fastapi_app_01.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def newline_client(monkeypatch):
    """Like `client`, but the stubbed deltas contain a newline (tests SSE framing)."""
    from fastapi_app_01.core import llm

    async def newline_stream(question: str):
        for chunk in ["line1\n", "line2"]:
            yield chunk

    monkeypatch.setattr(llm, "stream_answer", newline_stream)

    from fastapi_app_01.main import app

    with TestClient(app) as c:
        yield c
