def test_chat_returns_answer(client):
    r = client.post("/chat", json={"question": "用一句話解釋什麼是 RAG"})
    assert r.status_code == 200
    assert r.json()["answer"]


def test_chat_rejects_empty_question(client):
    r = client.post("/chat", json={"question": ""})
    assert r.status_code == 422
