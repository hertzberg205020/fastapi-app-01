# 待辦清單 — 迭代 2(Iteration 2):SSE 串流

> **用途**:給 Claude Code(或其他開發工具)照著**逐項打勾**的執行清單。
> plan 講「為什麼 / 怎麼做」,本清單講「做了沒 / 怎麼確認」。
>
> **來源**:`plans/iteration-2-streaming.md`(步驟、決策、DoD)、`specs/api.yml`(端點契約)、
> `specs/tech-stack.md`(技術棧與測試模式)。任務代號 **T0–T7** 對應 plan 的 Step 0–7。
>
> **本質**:骨架不變,只把 `POST /chat` 的回應方式從「非串流 JSON」換成「SSE 逐字串流」。
>
> **原則**:不擴張範圍、不與 plan 的決策(D1–D5)衝突。本迭代的**硬性收工條件**包含
> 「自動測試綠燈 + `curl -N` live 串流 + 容器發布驗證」(與迭代 1 不同,自動測試已是 DoD)。

---

## 已定案決策(實作時遵守,並記於 commit message)

> 來自 plan「決策點」一節,**皆已討論定案**,實作不需再選,只需照做並在 commit 註明:

- [ ] **D1 替換 `/chat` 為串流**(不另開 `/chat/stream`)→ 取代迭代 1 的 JSON 契約。
- [ ] **D2 SSE 格式 = JSON 包裝 + 結束標記**:每段 `data: {"text": "<delta>"}\n\n`,結尾 `data: [DONE]\n\n`。
- [ ] **D3 移除 `core/llm.py` 的 `answer()`**(替換為 `stream_answer()`,舊函式成孤兒)。
- [ ] **D4 移除 `schemas/chat.py` 的 `ChatResponse`**(串流不走 Pydantic 序列化)。
- [ ] **D5 採自訂 SSE**;OpenAI 相容 `/v1/chat/completions` 留待迭代 3,本迭代不做。
- [ ] 另:串流中途錯誤 / client 斷線維持最小處理(排迭代 6);**不引入 `sse-starlette`**。

---

## 前置條件

- [ ] 已讀 `plans/iteration-2-streaming.md`、`specs/api.yml`、`specs/tech-stack.md`。
- [ ] 確認在功能分支上(非 `main`;見 T0)。
- [ ] `.env` 已存在且含 `ANTHROPIC_API_KEY`(沿用迭代 1;`curl -N` live 驗收需真 key)。
- [ ] 確認現況基準(迭代 1 已交付):
      `core/llm.py` 有 `async def answer() -> str`(`messages.create`);
      `api/chat.py` 回 `ChatResponse`(`response_model=ChatResponse`);
      `schemas/chat.py` 有 `ChatRequest` + `ChatResponse`;
      `tests/test_chat.py` 斷言 `r.json()["answer"]`;`tests/conftest.py` monkeypatch `llm.answer`。
- [ ] **無需新增依賴**:`StreamingResponse` 已含於 `fastapi[standard]`,`json` 為 stdlib。

---

## 任務待辦(T0–T7)

### T0 — 開分支(plan Step 0)

- **動到**:git 分支。
- [ ] `git switch -c feat/iteration-2-streaming`(或同等命名)。
- **Acceptance**:`git branch --show-current` 顯示新分支,非 `main`。

### T1 — `core/llm.py`:`answer()` → `stream_answer()`(plan Step 1)

- **動到**:`src/fastapi_app_01/core/llm.py`。
- [ ] client 建立方式不變(`_client = AsyncAnthropic(api_key=settings.anthropic_api_key)`)。
- [ ] **移除** `async def answer(...)`,**新增** `async def stream_answer(question: str) -> AsyncIterator[str]`。
- [ ] 用 `async with _client.messages.stream(model=..., max_tokens=1024, messages=[{"role":"user","content":question}]) as stream:`,
      內層 `async for text in stream.text_stream: yield text`。
- [ ] 補 `from collections.abc import AsyncIterator` import。
- **Acceptance**:模組可被 import(有假 / 真 key 時);`stream_answer` 為 async generator
      (`inspect.isasyncgenfunction(llm.stream_answer)` 為真);`answer` 已不存在。
- **注意**:`stream_answer` **只 yield 純文字 delta**,保持傳輸無關;SSE 線格式化留給 T2 的 api 層。
      `messages.stream` 是 async context manager,**必須**在 `async with` 內把 `text_stream` 消費完。

### T2 — `api/chat.py`:回 `StreamingResponse`(SSE)(plan Step 2)

- **動到**:`src/fastapi_app_01/api/chat.py`。
- [ ] 新增 `_sse(question)` async generator:
      `async for text in llm.stream_answer(question): yield f"data: {json.dumps({'text': text}, ensure_ascii=False)}\n\n"`;
      迴圈後 `yield "data: [DONE]\n\n"`。
- [ ] 端點改為 `@router.post("/chat")`(**移除** `response_model=ChatResponse`),
      回 `StreamingResponse(_sse(req.question), media_type="text/event-stream")`。
- [ ] import 調整:加 `import json`、`from collections.abc import AsyncIterator`、
      `from fastapi.responses import StreamingResponse`;**移除** `ChatResponse` 的 import(只留 `ChatRequest`)。
- **Acceptance**:`POST /chat` 回 `Content-Type: text/event-stream`;本文為多段 `data: {"text": ...}\n\n` + 結尾 `data: [DONE]\n\n`。
- **注意**:`ensure_ascii=False` 讓中文不被轉成 `\uXXXX`;delta 含 `\n` 時靠 JSON 包裝避免破壞 SSE 框架(D2 的理由)。

### T3 — `schemas/chat.py`:移除孤兒 `ChatResponse`(plan Step 3 / 決策 D4)

- **動到**:`src/fastapi_app_01/schemas/chat.py`。
- [ ] 動工前先 `grep -rn "ChatResponse" src/ tests/` 確認除即將改的 `api/chat.py` 外無其他引用。
- [ ] 移除 `ChatResponse` 類別,只留 `ChatRequest`。
- **Acceptance**:`grep -rn "ChatResponse" src/` 無命中;`main.py` 未直接引用故不需改。
- **注意**:`ChatRequest`(`question: str = Field(min_length=1)`)**不變** —— 422 驗證沿用它。

### T4 — 更新測試:斷言串流契約(plan Step 4)【硬性 DoD】

- **動到**:`tests/conftest.py`、`tests/test_chat.py`。
- [ ] `conftest.py`:`client` fixture 的 mock 接縫從 `llm.answer` 換成
      `monkeypatch.setattr(llm, "stream_answer", fake_stream)`,其中 `fake_stream` 為 async generator
      `yield` 出 `["stub ", "answer ", f"for: {question}"]`。
- [ ] `conftest.py`:新增第二個 fixture `newline_client`(同樣 monkeypatch `stream_answer`,
      改用 `newline_stream`,yield `["line1\n", "line2"]`),供測試 3 用。
- [ ] `test_chat.py`:加 SSE 解析小工具 `_data_events(body)`(取所有 `data:` payload)。
- [ ] **測試 1**`test_chat_streams_answer`:`200` + `content-type` 開頭 `text/event-stream`;
      `_data_events` 末項 == `"[DONE]"`;前面各項的 `text` 串接 == `"stub answer for: <question>"`。
- [ ] **測試 2**`test_chat_rejects_empty_question`:空 `question` → `422`。
- [ ] **測試 3**`test_newline_delta_stays_one_frame`:用 `newline_client`;事件數 == 3
      (2 內容 + `[DONE]`),`json.loads(events[0])["text"] == "line1\n"`、`events[1] == "line2"`。
- **Acceptance**:`uv run pytest` 三條全綠;測試全程 mock,不打真 Claude。
- **注意**:`TestClient`(httpx)會把串流**緩衝**成完整本文,`r.text` 即整段 SSE,足以斷言契約;
      **真正的逐 token 增量遞送 in-process 測不準**,留待 T5 的 `curl -N` 肉眼確認(誠實邊界)。

### T5 — host 手動驗收(plan Step 5)【硬性 DoD,需真 key,會計費】

- **動到**:無(執行驗證)。
- [ ] `uv run uvicorn fastapi_app_01.main:app --reload` 起得來。
- [ ] `curl -N -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{"question": "用一句話解釋什麼是 RAG"}'`
      → **逐段**印出 `data: {"text":"..."}`,最後 `data: [DONE]`。
- [ ] 未設 `ANTHROPIC_API_KEY` 時啟動即報清楚的 `ValidationError`(fail fast,沿用迭代 1)。
- [ ] 空 `question`(`{"question": ""}`)回 **422**。
- **Acceptance**:`-N`(關 curl 緩衝)下肉眼可見逐字浮現,且收到 `[DONE]`;驗證情境符合預期狀態碼。
- **注意**:會**真實呼叫 Anthropic API(計費)**,做一次最小呼叫即可。

### T6 — 文件對齊(plan Step 6)

- **動到**:`specs/api.yml`、`README.md`、`specs/tech-stack.md`。
- [ ] `specs/api.yml`:
      - `info.description` 頂部「當前為 **Iteration 1(Walking Skeleton)**」與「`POST /chat`…(**非串流**…)」改為反映迭代 2 串流;`SSE 串流` 自「後續迭代」清單移除。
      - `/chat` 的 `200`:由 `$ref: ChatResponse` 改描述為 `text/event-stream`(`data: {"text": "..."}` + `data: [DONE]`)。
      - 移除 `ChatResponse` schema(grep 確認無其他 `$ref`);`422` / `RootResponse` / `HealthResponse` 不變。
- [ ] `README.md`:迭代藍圖第 2 列狀態 🚧→✅;迭代 1/2 區塊與「快速啟動」`curl` 範例補 `-N` 與 SSE 說明;架構圖標示串流回應。
- [ ] `specs/tech-stack.md`(維持「迭代 1 技術棧」定位,**不擴大範圍**):開頭加定位說明
      (本檔為迭代 1 參考,串流變更見 `plans/iteration-2-streaming.md`);`anthropic` 段「迭代 2 才改 `messages.stream`」點明已採用。
- **Acceptance**:`specs/api.yml` 仍為合法 YAML;`grep -rn "ChatResponse" specs/` 無命中;README 第 2 列為 ✅。
- **注意**:specs 描述**已交付狀態**,故本步驟與程式**同批** commit,避免文件先於程式宣稱串流。

### T7 — 容器發布驗證(plan Step 7)【硬性 DoD,需真 key,會計費】

- **動到**:無(執行驗證)。
- [ ] `docker compose --profile full up --build -d api`(compose B:只起 api,不拉 postgres/redis)。
- [ ] 對容器版打同一個 `curl -N`(埠 8000)→ 同樣**逐段串流** + `[DONE]`。
- [ ] 收工:`docker compose --profile full down`。
- **Acceptance**:可發布映像在容器內也串流得出答案。
- **注意**:會**真實呼叫 Anthropic API(計費)**,做一次最小呼叫即可。

---

## 驗收測試(自動;對應 Layer 1 —— **本迭代屬硬性 DoD**)

> 把 T5 的串流契約自動化。沿用 `specs/tech-stack.md` 的 `conftest.py` 模式
> (import app 前先設假 `ANTHROPIC_API_KEY`、在 `llm` 接縫 monkeypatch、`TestClient(app)`)。
> Claude 一律 mock,不打真 API。對應 `specs/api.yml` 的 200(SSE) / 422 契約。

- [ ] happy-path(AC 1–4):`text/event-stream` + 各 `data` 串接 == 完整答案 + 末項 `[DONE]`。
- [ ] 輸入驗證(AC 6):空 `question` → `422`。
- [ ] 換行不破框(AC 5,守 D2):含 `\n` 的 delta 被 JSON 轉義在 payload 內,事件數不暴增。
- **注意**:in-process `TestClient` 免起 server、最快,適合開發迴圈 / CI;**逐 token 增量**靠 T5 肉眼驗。

---

## 整合測試(Layer 4 容器冒煙 + Layer 5 live E2E —— 對應發布驗證)

> 對「已跑起來」的 host / 容器服務做黑箱驗證。打真進程,無法 mock Claude。

- [ ] (Layer 4)`docker build` / `docker compose --profile full up` 起得來(形狀,AC 9)。
- [ ] (Layer 5)host `curl -N`:逐段 `data: {"text":...}` + `[DONE]`(AC 1–4,真實逐字浮現)。
- [ ] (Layer 5)容器 `curl -N`:同一請求同樣串流得出(AC 9)。
- **注意**:Layer 5 會**真實呼叫 Anthropic(計費)**,host + 容器各一次即可。

---

## Definition of Done(對映 plan 的 8 條)

- [ ] **逐字串流**:`curl -N POST /chat` 逐段收到 `data: {"text": "..."}`,結尾 `data: [DONE]`。【T5 / T7】
- [ ] **content-type 正確**:回應 `Content-Type: text/event-stream`。【T2 / T4】
- [ ] **輸入驗證不變**:空 `question` 仍回 422(`ChatRequest` 的 `min_length=1`)。【T3 / T4】
- [ ] **缺 key 仍 fail fast**:未設 `ANTHROPIC_API_KEY` 啟動即報 `ValidationError`(沿用迭代 1)。【T5】
- [ ] **不需 DB 即可啟動**:沿用迭代 1,Postgres/Redis 仍非必要。【T5】
- [ ] **測試綠燈**:`uv run pytest` 通過(串流 happy-path、422、換行不破框 共三條)。【T4】
- [ ] **可發布**:容器版同一 `curl -N` 也串流得出答案。【T7】
- [ ] **文件對齊**:README 迭代 2 狀態、`specs/api.yml` 的 `/chat` 已反映 SSE;無孤兒 `ChatResponse` 殘留。【T3 / T6】

---

## 注意事項彙總(避免踩坑)

- **async generator 生命週期**:`messages.stream` 是 async context manager,務必在 `async with` 內把
  `text_stream` 消費完;放進 `StreamingResponse` 的 generator 自然滿足(generator 跑完才結束)。
- **SSE 框架 vs 換行**:delta 內含 `\n` 會破壞 `data:` 框架 → 採 D2 的 JSON 包裝規避(`ensure_ascii=False`)。
- **測試接縫換名**:接縫從 `llm.answer` 變 `llm.stream_answer`,且改為 **async generator** —— conftest 的 mock 要對應改;
  路由透過模組屬性 `llm.stream_answer(...)` 呼叫,monkeypatch 模組屬性即可。
- **in-process 測不到增量性**:`TestClient` 緩衝整段,Layer 1 驗的是 SSE **契約**,逐字浮現靠 `curl -N`。
- **契約破壞是刻意的**:D1 替換後迭代 1 的 `{"answer": ...}` JSON 契約被取代(README 藍圖即如此規劃),非疏漏;
  連帶要更新 `specs/api.yml` 與既有測試,勿留舊 JSON 斷言。
- **OpenAPI 文件**:`StreamingResponse` 無 `response_model`,`/docs` 對 `/chat` 回應描述較簡略 → 以 `specs/api.yml` 手動補述。
- **錯誤處理刻意最小**:不特別處理 client 斷線 / 串流中途上游錯誤,讓其自然冒出;健全處理排迭代 6,勿過度設計。
- **不引入後續迭代技術**:OpenAI 相容 `/v1`(迭代 3)、Postgres(迭代 4)、RAG(迭代 5)、Redis/限流(迭代 6)一律不碰。
- **不加新依賴**:`StreamingResponse` 內建、`json` 為 stdlib;不引入 `sse-starlette`。

---

## 完成後 → 下一個迭代

迭代 3(OpenAI 相容 `/v1`):新增 `/v1/chat/completions`,把本迭代的串流重塑成 OpenAI 相容格式
(`data: {"choices":[{"delta":{"content":...}}]}`),即可接 Open WebUI 等前端;多輪歷史由前端帶在
`messages` 陣列送入,無需伺服器端持久化(伺服器端記憶留待迭代 4)。骨架與串流機制不變。
