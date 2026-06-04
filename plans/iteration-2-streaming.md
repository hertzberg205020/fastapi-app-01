# 迭代 2(Iteration 2):SSE 串流

> 對應 README「迭代藍圖」第 2 列。這份文件是**可照著做的執行計畫**:規劃、決策點、有序步驟(含示範程式碼)、驗收標準。
> 文中所有程式碼皆標「**預計 / 待實作**」——目前 `/chat` 仍是迭代 1 的非串流 JSON 回應。

## Context

迭代 1 的 Walking Skeleton 已打通整條管線(容器 → API key → 路由 → Anthropic SDK)。
迭代 2 **不動骨架,只換回應方式**:把 `POST /chat` 從「一次回傳整段 JSON」改成
**逐字 Server-Sent Events(SSE)串流**。

> **`POST /chat` 改用 `AsyncAnthropic.messages.stream(...)`,以 `text/event-stream` 逐段把文字 delta 推給前端。**

價值:這是面對 LLM 應用最常見的 UX 要求(逐字浮現,而非等整段)。技術上要打通的新風險是
**串流回應**——非同步產生器(async generator)貫穿「SDK 串流 → FastAPI `StreamingResponse` → SSE 線格式」。
資料庫、RAG、限流仍不在本迭代。

---

## 範圍界定

| | 內容 |
| ----------- | -------------------------------------------------------------- |
| ✅ **In**  | `POST /chat` 改 SSE 逐字串流;`llm` 層提供串流接縫;更新測試與 `curl -N` 驗收;文件對齊 |
| ❌ **Out** | OpenAI 相容 `/v1/chat/completions`(Open WebUI 對外相容層,迭代 3)、對話記憶 / Postgres(迭代 4)、RAG / pgvector(迭代 5)、限流 / `/metrics` / 健全錯誤處理(迭代 6)、加分項(迭代 7) |

**刻意不做**:不做多輪歷史、不接 DB、不做檢索;串流中途上游失敗的**健全**錯誤處理仍延後(本迭代維持最小,讓錯誤自然冒出)。

---

## 架構(本迭代)

```ascii
   提問 ──POST /chat──▶ ┌──────────┐ ──messages.stream──▶ ┌────────┐
       {"question"}     │ FastAPI  │ ◀──text delta──────── │ Claude │
                        └────┬─────┘  逐段                  └────────┘
                             │ 每段包成 SSE
                             ▼
                   text/event-stream:
                   data: {"text": "..."}\n\n   ← 逐段
                   data: {"text": "..."}\n\n
                   data: [DONE]\n\n            ← 結束標記
```

骨架(路由、`llm` 封裝、schema)與迭代 1 相同;差別只在 `answer()`(回整段)換成
`stream_answer()`(逐段 yield),端點回 `StreamingResponse` 而非 `ChatResponse`。

---

## 與迭代 1 的差異(一眼看懂)

| 層 | 迭代 1(現況) | 迭代 2(本迭代) |
| ------------- | ----------------------------------- | ------------------------------------------- |
| `core/llm.py` | `async def answer() -> str`(`messages.create`,取 `content[0].text`) | `async def stream_answer() -> AsyncIterator[str]`(`messages.stream`,逐段 yield) |
| `api/chat.py` | 回 `ChatResponse`(JSON) | 回 `StreamingResponse`(`text/event-stream`) |
| `schemas/chat.py` | `ChatRequest` + `ChatResponse` | `ChatRequest`(不變);`ChatResponse` 變孤兒(見決策 D4) |
| 回應契約 | 單一 JSON `{"answer": "..."}` | SSE 事件流 `data: {...}\n\n` |
| 測試 | 斷言 JSON `answer` | 斷言 `text/event-stream` + 累積文字 + `[DONE]` |
| 依賴 | — | **無新增**(`StreamingResponse` 內建、`json` 為 stdlib) |

---

## 決策點(實作時定案,並記於 commit message)

迭代 1 的 compose A/B 一樣,以下需在動工時拍板:

### D1 — 端點:替換 `/chat` vs 另開 `/chat/stream`

- **(建議)替換 `/chat` 為串流**:符合 README 藍圖「把 `/chat` 改逐字串流」。代價:**取代**迭代 1 的 JSON 契約(`{"answer": ...}` 不再回);需同步更新測試與 `specs/api.yml`。骨架最乾淨。
- (備案)新增 `POST /chat/stream`、`/chat` 維持 JSON:不破壞舊契約,但留兩條重複路徑,與「只換回應方式」的精神不符。

### D2 — SSE payload 格式

- **(建議)JSON 包裝 + 結束標記**:每段 `data: {"text": "<delta>"}\n\n`,結尾 `data: [DONE]\n\n`。
  優點:文字含換行也不會破壞 SSE 框架(換行是 SSE 分隔符);未來要加 metadata(token 數、引用)可擴充;`[DONE]` 讓前端明確知道結束(OpenAI 慣例)。
- (備案)純文字 delta `data: <delta>\n\n`:最短,但 delta 內含 `\n` 會破框,且不易擴充。

### D3 — `core/llm.py` 的 `answer()`

替換後 `answer()` 無人呼叫。依 CLAUDE.md「移除你的改動造成的孤兒」:**建議移除** `answer()`,改為 `stream_answer()`。(若想保留非串流路徑備用則留著,但本迭代無使用點。)

### D4 — `schemas/ChatResponse`

`StreamingResponse` 不走 Pydantic 序列化,`ChatResponse` 變孤兒。**建議移除**,`schemas/chat.py` 只留 `ChatRequest`。

### D5 — 串流格式範圍:自訂 SSE vs OpenAI 相容 `/v1`

- **(定案)自訂 SSE**:本迭代只做 `data: {"text": "..."}` 自訂格式,專注打通「串流」這條技術風險。
- (迭代 3)**OpenAI 相容 `/v1/chat/completions`**(Open WebUI 直接可接的 `data: {"choices":[{"delta":{"content":...}}]}`)
  是與「串流」正交的**對外相容層**關注點,排進緊接的迭代 3 單獨做,避免本迭代範圍膨脹。

> **已定案(經討論)**:**D1 替換 `/chat`**、**D2 JSON 包裝 + `[DONE]`**、**D3 移除 `answer()`**、
> **D4 移除 `ChatResponse`**、**D5 採自訂 SSE(OpenAI 相容 `/v1` 延後)**。
> 另:串流中途錯誤 / client 斷線維持最小處理(排迭代 6);不引入 `sse-starlette`(內建 `StreamingResponse` 足夠)。
> 下方步驟依此撰寫。

---

## 執行步驟

> 每步標**動到的檔案**與**預計程式碼**。實作以 `anthropic` 當前 SDK 為準(已用 context7 確認 `messages.stream` / `text_stream`)。

### Step 0 — 開分支

```bash
git switch -c feat/iteration-2-streaming
```

### Step 1 — `core/llm.py`:`answer()` → `stream_answer()`

動到 `src/fastapi_app_01/core/llm.py`。client 建立方式不變,把非串流 `messages.create`
換成 `messages.stream` 的非同步產生器,逐段 yield 純文字(**保持傳輸無關**——SSE 格式化留給 api 層)。

```python
# 預計:src/fastapi_app_01/core/llm.py
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
```

### Step 2 — `api/chat.py`:回 `StreamingResponse`(SSE)

動到 `src/fastapi_app_01/api/chat.py`。新增一個把 `llm.stream_answer` 逐段包成 SSE 的
async generator;端點回 `StreamingResponse(..., media_type="text/event-stream")`。

```python
# 預計:src/fastapi_app_01/api/chat.py
import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from fastapi_app_01.core import llm
from fastapi_app_01.schemas.chat import ChatRequest

router = APIRouter()


async def _sse(question: str) -> AsyncIterator[str]:
    """把純文字 delta 逐段包成 SSE 事件,結尾送 [DONE]。"""
    async for text in llm.stream_answer(question):
        yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"


@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    return StreamingResponse(_sse(req.question), media_type="text/event-stream")
```

> 註:`response_model=ChatResponse` 拿掉了(串流不走 Pydantic 序列化)。`ensure_ascii=False` 讓中文不被轉成 `\uXXXX`。

### Step 3 — `schemas/chat.py`:移除孤兒 `ChatResponse`(決策 D4)

```python
# 預計:src/fastapi_app_01/schemas/chat.py
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, description="使用者的提問")
```

> `main.py` 不需改(只 `include_router`,未直接引用 `ChatResponse`)。動工前先 grep 確認 `ChatResponse` 無其他引用。

### Step 4 — 更新測試:斷言串流契約

動到 `tests/conftest.py` 與 `tests/test_chat.py`。共三條測試(對應下節「驗收與測試策略」的 Layer 1)。

`conftest.py`:把 mock 接縫從 `answer` 換成 `stream_answer`(回非同步產生器);
另加一個「delta 含換行」的 stub fixture,給測試 3 用:

```python
# 預計:tests/conftest.py(節錄)
# client fixture 內:
async def fake_stream(question: str):
    for chunk in ["stub ", "answer ", f"for: {question}"]:
        yield chunk

monkeypatch.setattr(llm, "stream_answer", fake_stream)

# 另一個 fixture(測試 3 用):delta 故意含換行
async def newline_stream(question: str):
    for chunk in ["line1\n", "line2"]:
        yield chunk
# → 同樣 monkeypatch.setattr(llm, "stream_answer", newline_stream)
```

`test_chat.py`:用一個 SSE 解析小工具,把斷言下在「框架 + 內容完整性 + 結束標記」上,
而非只看「有 data: 字串」:

```python
# 預計:tests/test_chat.py
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
```

> `TestClient`(httpx)會把串流回應**緩衝**成完整本文,`r.text` 即整段 SSE,足以斷言契約。
> 真正的「逐 token 增量遞送」測不準(見下節邊界),靠 Step 5 的 `curl -N` 肉眼確認。

### Step 5 — host 手動驗證(開發完成)

```bash
uv run uvicorn fastapi_app_01.main:app --reload

# -N 關掉 curl 緩衝,才看得到逐段浮現
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "用一句話解釋什麼是 RAG"}'
# 期望 → 逐段印出 data: {"text":"..."} ... 最後 data: [DONE]
```

### Step 6 — 文件對齊

> 原則:specs 描述的是**已交付狀態**,故這些變更與程式**同批**進,避免文件先於程式宣稱串流。

- `specs/api.yml`(單一真實契約,須完整更新到迭代 2):
  - `info.description`:頂部「當前為 **Iteration 1(Walking Skeleton)**」與「`POST /chat`…(**非串流**、無對話歷史、無 RAG)」兩句改為反映迭代 2 串流;`SSE 串流` 從「後續迭代」清單移除(已交付)。
  - `/chat` 的 `200`:從 `$ref: ChatResponse` 改描述為 `text/event-stream`(SSE 事件流,`data: {"text": "..."}` + `data: [DONE]`)。
  - `ChatResponse` schema 變孤兒 → 移除(grep 確認無其他 `$ref`)。`422`、`RootResponse`、`HealthResponse` 不變。
- `README.md`:迭代藍圖第 2 列狀態 🚧→✅;迭代 1/2 區塊與「快速啟動」的 `curl` 範例補 `-N` 與 SSE 說明;架構圖標示串流回應。
- `specs/tech-stack.md`(維持其「迭代 1 技術棧」定位,**不擴大範圍**):
  - 開頭加一句定位說明:「本檔為**迭代 1**技術棧參考;迭代 2 的串流變更見 `plans/iteration-2-streaming.md`」,避免讀者誤把檔內 `messages.create` / `r.json()["answer"]` 等**迭代 1 範例**當成最新。
  - 不逐處改寫該檔的非串流範例(它們是迭代 1 的忠實紀錄);僅 `anthropic` 段第 117 行「迭代 2 才改 `messages.stream`」可順手點明「迭代 2 已採用」。

### Step 7 — 發布驗證(收工前)

```bash
docker compose --profile full up --build -d api   # compose B:只起 api,不拉 postgres/redis
curl -N -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"question": "用一句話解釋什麼是 RAG"}'
# 期望:容器版同樣逐段串流 + [DONE]
docker compose --profile full down
```

---

## 驗收與測試策略

沿用迭代 1 的五層策略,把計費的真實呼叫壓到最後一層;每層各自涵蓋部分 AC。

| 層 | 做什麼 | 涵蓋 AC | 計費 |
| --- | ----------------------------------------- | -------------- | ---- |
| 1 自動測試(in-process,mock) | `uv run pytest`,mock `llm.stream_answer`;見 Step 4 三條 | 1–6 | 否 |
| 2 啟動冒煙 | dummy key 起 app,`/health` 回 200 | 7、8 | 否 |
| 3 config 行為 | `env -u ANTHROPIC_API_KEY` 確認 fail-fast | 7 | 否 |
| 4 容器冒煙 | `docker build` + `compose --profile full up` 起得來 | 9(形狀) | 否 |
| 5 **live E2E** | `curl -N` 對真 Claude(host + 容器各一次) | 1–4、9(真實逐字浮現) | **是** |

**AC 對照**(可觀察、可客觀判定):

1. `Content-Type: text/event-stream`
2. 本文由多個 `data: {"text": "..."}\n\n` 組成
3. 最後一個事件為 `data: [DONE]\n\n`
4. 各事件 `text` 串接 == 完整回答
5. delta 含換行不破壞 SSE 框架(`ensure_ascii=False` + JSON 包裝)
6. 空 `question` 回 422
7. 缺 `ANTHROPIC_API_KEY` 啟動即 `ValidationError`
8. 不需 Postgres/Redis 即可啟動
9. 容器版同一 `curl -N` 也串流得出
10. 無孤兒殘留(`answer()` / `ChatResponse` 無其他引用,grep 確認)

**誠實邊界(自動測不到的)**:

- **逐 token 增量遞送測不準**:`TestClient` 會把串流緩衝成完整本文,Layer 1 驗的是 **SSE 契約**(格式、順序、完整、結束標記),真實逐字浮現只能由 Layer 5 的 `curl -N` 肉眼確認。
- **真 Claude 串流**:Layer 1 全程 mock,不打真 API;真實串流只在 Layer 5 各做一次,計費最小化。

---

## 驗收標準(Definition of Done)

- [ ] **逐字串流**:`curl -N POST /chat` 逐段收到 `data: {"text": "..."}`,結尾 `data: [DONE]`。
- [ ] **content-type 正確**:回應 `Content-Type: text/event-stream`。
- [ ] **輸入驗證不變**:空 `question` 仍回 422(`ChatRequest` 的 `min_length=1`)。
- [ ] **缺 key 仍 fail fast**:未設 `ANTHROPIC_API_KEY` 啟動即報 `ValidationError`(沿用迭代 1)。
- [ ] **不需 DB 即可啟動**:沿用迭代 1,Postgres/Redis 仍非必要。
- [ ] **測試綠燈**:`uv run pytest` 通過(串流 happy-path、422、換行不破框 共三條)。
- [ ] **可發布**:容器版同一 `curl -N` 也串流得出答案。
- [ ] **文件對齊**:README 迭代 2 狀態、`specs/api.yml` 的 `/chat` 已反映 SSE;無孤兒 `ChatResponse` 殘留。

---

## 風險 / 取捨

- **async generator 生命週期**:`messages.stream` 是 async context manager,**必須**在 `async with` 內把
  `text_stream` 消費完;放進 FastAPI `StreamingResponse` 的 generator 自然滿足(generator 跑完才結束)。
- **SSE 框架 vs 換行**:delta 內含 `\n` 會破壞 `data:` 框架 → 採 D2 的 JSON 包裝規避。
- **客戶端中斷 / 中途錯誤**:本迭代維持最小——不特別處理 client 斷線或串流途中上游錯誤,排進迭代 6。
- **不引入 `sse-starlette`**:內建 `StreamingResponse` 已足夠;若日後要 ping/重連/斷線偵測再評估(迭代 6+)。
- **OpenAPI 文件**:`StreamingResponse` 無法用 `response_model` 自動產生 schema,`/docs` 對 `/chat` 的回應描述會較簡略——以 `specs/api.yml` 手動補述。
- **契約破壞**:採 D1 後迭代 1 的 JSON 契約被取代;這是有意識的演進(README 藍圖即如此規劃),非疏漏。

---

## 完成後 → 下一個迭代

迭代 3(OpenAI 相容 `/v1`):新增 `/v1/chat/completions`,把本迭代的串流重塑成 OpenAI 相容格式
(`data: {"choices":[{"delta":{"content":...}}]}`),即可接 Open WebUI 等前端;多輪歷史由前端
帶在 `messages` 陣列送入,無需伺服器端持久化(伺服器端記憶留待迭代 4)。骨架與串流機制不變。
