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


# Stub deltas join to this exact string; complete_chat returns the same text, so
# both /v1 paths assert against one known answer.
OAI_ANSWER = "stub answer here"


@pytest.fixture
def oai_client(monkeypatch):
    """Client for the OpenAI-compatible /v1 endpoints, with Claude mocked at the
    llm.stream_chat / llm.complete_chat seam. The (messages, system) handed to the
    adapter is recorded on `client.calls` so tests can assert the transcoding."""
    from fastapi_app_01.core import llm

    calls: dict = {}

    async def fake_stream_chat(messages, system=None):
        calls["stream_chat"] = {"messages": messages, "system": system}
        for chunk in ["stub ", "answer ", "here"]:
            yield chunk

    async def fake_complete_chat(messages, system=None):
        calls["complete_chat"] = {"messages": messages, "system": system}
        return llm.ChatResult(text=OAI_ANSWER, stop_reason="end_turn",
                              input_tokens=11, output_tokens=7)

    monkeypatch.setattr(llm, "stream_chat", fake_stream_chat)
    monkeypatch.setattr(llm, "complete_chat", fake_complete_chat)

    from fastapi_app_01.main import app

    with TestClient(app) as c:
        c.calls = calls
        yield c
