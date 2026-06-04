import json


def _data_events(body: str) -> list[str]:
    """從 SSE 本文取出所有 data: 的 payload(去掉前綴與空白)。"""
    return [ln[len("data:"):].strip() for ln in body.splitlines() if ln.startswith("data:")]


# 測試 1 — 串流 happy-path(AC 1–4)
def test_chat_streams_answer(client):
    r = client.post("/chat", json={"question": "用一句話解釋什麼是 RAG"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    events = _data_events(r.text)
    assert events[-1] == "[DONE]"                                  # AC 3:結束標記
    text = "".join(json.loads(e)["text"] for e in events[:-1])
    assert text == "stub answer for: 用一句話解釋什麼是 RAG"        # AC 4:串接 == 完整答案


# 測試 2 — 輸入驗證不變(AC 6)
def test_chat_rejects_empty_question(client):
    r = client.post("/chat", json={"question": ""})
    assert r.status_code == 422


# 測試 3 — delta 含換行不破框(AC 5;守 D2 的取捨)
def test_newline_delta_stays_one_frame(newline_client):
    r = newline_client.post("/chat", json={"question": "hi"})
    events = _data_events(r.text)
    assert events[-1] == "[DONE]"
    # 兩個內容事件,換行被 JSON 轉義在 payload 內,而非真的換行多切出事件
    assert len(events) == 3
    assert json.loads(events[0])["text"] == "line1\n"
    assert json.loads(events[1])["text"] == "line2"
