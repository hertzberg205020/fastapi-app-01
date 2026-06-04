import json

from fastapi_app_01.config import settings

from conftest import OAI_ANSWER


def _data_events(body: str) -> list[str]:
    """從 SSE 本文取出所有 data: 的 payload(去掉前綴與空白)。"""
    return [ln[len("data:"):].strip() for ln in body.splitlines() if ln.startswith("data:")]


# AC 1 — 模型列得出
def test_models(oai_client):
    r = oai_client.get("/v1/models")
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "list"
    assert body["data"][0]["id"] == settings.anthropic_model


# AC 2 — 串流相容:chat.completion.chunk 串接 + finish_reason + [DONE]
def test_completions_stream(oai_client):
    r = oai_client.post("/v1/chat/completions", json={
        "model": "ignored", "stream": True,
        "messages": [{"role": "user", "content": "用一句話解釋什麼是 RAG"}],
    })
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    events = _data_events(r.text)
    assert events[-1] == "[DONE]"                                   # 結束標記

    chunks = [json.loads(e) for e in events[:-1]]
    assert all(c["object"] == "chat.completion.chunk" for c in chunks)
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
    assert text == OAI_ANSWER                                       # delta.content 串接 == 完整答案
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"      # 末 chunk 收尾


# AC 3 — 非串流相容:單一 chat.completion + usage
def test_completions_nonstream(oai_client):
    r = oai_client.post("/v1/chat/completions", json={
        "stream": False,
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == OAI_ANSWER
    assert body["choices"][0]["finish_reason"] == "stop"           # end_turn → stop
    usage = body["usage"]
    assert usage["prompt_tokens"] == 11
    assert usage["completion_tokens"] == 7
    assert usage["total_tokens"] == 18


# AC 4 — system 抽取 + 多輪順序保留
def test_system_and_multiturn_mapping(oai_client):
    r = oai_client.post("/v1/chat/completions", json={
        "stream": True,
        "messages": [
            {"role": "system", "content": "你是個簡潔的助理"},
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
        ],
    })
    assert r.status_code == 200

    seen = oai_client.calls["stream_chat"]
    assert seen["system"] == "你是個簡潔的助理"                      # system 被抽到頂層
    assert seen["messages"] == [                                    # 其餘原順序、不含 system
        {"role": "user", "content": "Q1"},
        {"role": "assistant", "content": "A1"},
        {"role": "user", "content": "Q2"},
    ]


# AC 5 — 容忍未知 OpenAI 欄位
def test_tolerates_unknown_fields(oai_client):
    r = oai_client.post("/v1/chat/completions", json={
        "stream": False,
        "temperature": 0.7,
        "top_p": 0.9,
        "stream_options": {"include_usage": True},
        "messages": [{"role": "user", "content": "hi"}],
    })
    assert r.status_code == 200


# AC 6 — 空 messages → 422
def test_empty_messages_422(oai_client):
    r = oai_client.post("/v1/chat/completions", json={"messages": []})
    assert r.status_code == 422
