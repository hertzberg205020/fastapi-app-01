# 待辦清單 — 迭代 1(Iteration 1):Walking Skeleton

> **用途**:給 Claude Code(或其他開發工具)照著**逐項打勾**的執行清單。
> plan 講「為什麼 / 怎麼做」,本清單講「做了沒 / 怎麼確認」。
>
> **來源**:`plans/iteration-1-walking-skeleton.md`(步驟與 DoD)、`specs/api.yml`(端點契約)、
> `specs/tech-stack.md`(技術棧與測試模式)。任務代號 **T0–T9** 對應 plan 的 Step 0–9。
>
> **原則**:不擴張範圍、不與 plan 的 DoD 衝突。**硬性收工條件**仍是「手動 curl + 容器發布驗證」;
> 自動化測試(`TestClient` / 黑箱 E2E)列為**建議 / 選用**,見〈驗收測試〉〈整合測試〉。

---

## 前置條件

- [ ] 已讀 `plans/iteration-1-walking-skeleton.md`、`specs/api.yml`、`specs/tech-stack.md`。
- [ ] 確認在功能分支上(非 `main`;見 T0)。
- [ ] `.env` 已存在且含 `ANTHROPIC_API_KEY`(用 `cp -n .env.example .env` 不覆蓋既有檔,再手動補 key)。
- [ ] 確認現況基準:`pyproject.toml` 目前只有 `fastapi[standard]` + `pydantic-settings`;
      `src/fastapi_app_01/` 只有 `__init__.py` / `main.py` / `config.py`(尚無 `api/`、`core/`、`schemas/`)。

---

## 任務待辦(T0–T9)

### T0 — 開分支(plan Step 0)

- **動到**:git 分支。
- [ ] `git switch -c feat/iteration-1-walking-skeleton`(或同等命名)。
- **Acceptance**:`git branch --show-current` 顯示新分支,非 `main`。

### T1 — 加 `anthropic` 依賴(plan Step 1)

- **動到**:`pyproject.toml`、`uv.lock`。
- [ ] `uv add anthropic`。
- [ ] `pyproject.toml` 的 `dependencies` 出現 `anthropic`,`uv.lock` 同步更新。
- **Acceptance**:`uv run python -c "import anthropic"` 無誤;`git diff` 只動到 `pyproject.toml` / `uv.lock`。
- **注意**:`anthropic` 鎖最新即可;`pytest` 屬選用(`uv add --dev pytest`,僅在採用自動化測試時)。

### T2 — `config.py`:加 Claude 設定、DB/Redis 改選填(plan Step 2)

- **動到**:`src/fastapi_app_01/config.py`。
- [ ] 加 `anthropic_api_key: str`(**必填**,無預設 → 缺 key 即 fail fast)。
- [ ] 加 `anthropic_model: str = "claude-sonnet-4-6"`(有預設,可被環境覆寫)。
- [ ] 將 `database_url` / `redis_url` 從必填改為 `str | None = None`(本迭代不接 DB)。
- **Acceptance**:設了 `ANTHROPIC_API_KEY`、未設 `DATABASE_URL` / `REDIS_URL` 時,
      `uv run python -c "from fastapi_app_01.config import settings; print(settings.anthropic_model)"` 成功印出 model。
- **注意**:⚠️ 此改動會讓現有 `main.py` 的 `/health`(`urlparse(settings.database_url)`)在
      `database_url=None` 時炸掉 → **必須在 T5 一併修掉**,否則 `/health` 壞。

### T3 — `schemas/chat.py`:請求 / 回應模型(plan Step 3)

- **動到**:新增 `src/fastapi_app_01/schemas/__init__.py`、`src/fastapi_app_01/schemas/chat.py`。
- [ ] `ChatRequest`:`question: str = Field(min_length=1)`。
- [ ] `ChatResponse`:`answer: str`。
- **Acceptance**:欄位名 / 型別與 `specs/api.yml` 的 `ChatRequest` / `ChatResponse` 一致(snake_case、`question` `minLength: 1`)。

### T4 — `core/llm.py`:封裝 Anthropic 呼叫(plan Step 4)

- **動到**:新增 `src/fastapi_app_01/core/__init__.py`、`src/fastapi_app_01/core/llm.py`。
- [ ] 用 **`AsyncAnthropic`**(配合 async 端點),client 用 `settings.anthropic_api_key` 建立。
- [ ] `async def answer(question: str) -> str`:呼叫 `messages.create`,
      `model=settings.anthropic_model`、`max_tokens=1024`,回傳 `msg.content[0].text`。
- **Acceptance**:模組可被 import(已設假 / 真 key 時),`answer` 為 async 函式。
- **注意**:`answer` 是**模組層函式**(測試在此 monkeypatch);本迭代非串流(串流留迭代 2 的 `messages.stream`)。

### T5 — `api/chat.py`:路由 + `main.py` 註冊 + 修 `/health`(plan Step 5)

- **動到**:新增 `src/fastapi_app_01/api/__init__.py`、`src/fastapi_app_01/api/chat.py`;改 `src/fastapi_app_01/main.py`。
- [ ] `api/chat.py`:`APIRouter`,`@router.post("/chat", response_model=ChatResponse)`,
      `async def chat(req: ChatRequest)` 回 `ChatResponse(answer=await llm.answer(req.question))`。
- [ ] `main.py`:`app.include_router(chat_router)`。
- [ ] **修 `/health`**:移除 `urlparse(settings.database_url)`,改回
      `{"database_configured": bool(settings.database_url), "redis_configured": bool(settings.redis_url), "model": settings.anthropic_model}`。
- [ ] 移除 `main.py` 中因上述改動而不再用到的 import(如 `urlparse`)。
- **Acceptance**:`/chat` 端點存在且回 `{"answer": ...}`;`/health` 在無 DB 時不再噴錯,
      回傳結構與 `specs/api.yml` 的 `HealthResponse` 一致。
- **注意**:`/health` 改動是 T2 的連帶必要修正,不是可選;對齊 `specs/api.yml` 的 `HealthResponse`。

### T6 — `.env.example`:補上 key(plan Step 6)

- **動到**:`.env.example`(範本;`.env` 本身手動補,勿覆蓋)。
- [ ] 在 `.env.example` 加 `ANTHROPIC_API_KEY=sk-ant-...`(必填)與註解掉的 `# ANTHROPIC_MODEL=claude-sonnet-4-6`(可選)。
- **Acceptance**:`.env.example` 含 Anthropic 區塊;`.env`(gitignored)由開發者手動補上真 key。
- **注意**:用 `cp -n` 心智 —— 不覆蓋既有 `.env`。

### T7 — host 手動驗收(plan Step 7)【硬性 DoD】

- **動到**:無(執行驗證)。
- [ ] `uv run uvicorn fastapi_app_01.main:app --reload` 起得來。
- [ ] `curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{"question": "用一句話解釋什麼是 RAG"}'` 回 `{"answer": "..."}`。
- [ ] 未設 `ANTHROPIC_API_KEY` 時啟動即報清楚的 `ValidationError`(fail fast)。
- [ ] 空 `question`(`{"question": ""}`)回 **422**。
- **Acceptance**:上述 curl 拿到單一 JSON 回答(非串流);驗證情境符合預期狀態碼。

### T8 — multi-stage uv `Dockerfile`(plan Step 8)

- **動到**:新增 repo 根目錄 `Dockerfile`。
- [ ] builder 階段:`uv sync --frozen --no-install-project --no-dev` 再 `uv sync --frozen --no-dev`。
- [ ] runtime 階段:複製 `/app`,`CMD` 用 `uv run uvicorn fastapi_app_01.main:app --host 0.0.0.0 --port 8000`。
- **Acceptance**:`docker build -t fastapi-app-01 .` 成功(讓 compose 的 `build: .` 從 placeholder 變可用)。

### T9 — 容器發布驗證(plan Step 9)【硬性 DoD】

- **動到**:無(執行驗證);視決策可能動 `docker-compose.yml`(見下方決策點)。
- [ ] `docker compose --profile full up --build` 起得來。
- [ ] 對容器版打同一個 curl(埠 8000)也回得出 `{"answer": ...}`。
- **Acceptance**:可發布映像在容器內也 work,容器版 curl 通過。

---

## 決策點(實作時定案,並記錄於 commit message)

> 來自 plan Step 9:現有 `api` 服務 `depends_on` postgres+redis 且注入 `DATABASE_URL` / `REDIS_URL`,
> 與「本迭代不接 DB」精神不符。二選一:

- [ ] **(A) 維持現狀**:DB/Redis 跟著起來但 `/chat` 不碰它們。改動最小,先求發布驗證會過。
- [ ] **(B) 為迭代 1 瘦身(plan 建議)**:拿掉 `api` 的 `depends_on` 與 DB/Redis `environment`,
      讓發布產物真的只依賴 Claude;迭代 3 接 DB 時再加回。最誠實,但要動 `docker-compose.yml`。
- [ ] 已在 commit message 註明採用 A 或 B。

---

## 驗收測試(預期;建議 / 選用 —— **非硬性 DoD**)

> 把 T7 的手動 curl 自動化。對齊 `specs/tech-stack.md` 的 `tests/conftest.py` 模式
> (import app 前先設假 `ANTHROPIC_API_KEY`、monkeypatch `llm.answer`、`TestClient(app)`)。
> Claude 一律 mock,不打真 API。對應 `specs/api.yml` 的 200 / 422 契約。

- [ ] (選用)`uv add --dev pytest`,建 `tests/conftest.py`(假 key + `client` fixture)。
- [ ] (選用)happy path:`client.post("/chat", json={"question": "..."})` → `200` 且 `r.json()["answer"]` 非空。
- [ ] (選用)輸入驗證:`client.post("/chat", json={"question": ""})` → `422`(由 `ChatRequest` `min_length=1` 把關)。
- **注意**:in-process `TestClient` 免起 server、最快,適合開發迴圈 / CI;此章節**不**列入迭代 1 收工硬條件。

---

## 整合測試(預期;建議 / 選用 —— **非硬性 DoD**)

> 對「已跑起來」的 host / 容器服務做黑箱 smoke(httpx `api_client`,`base_url` 由 `API_BASE_URL` 控制)。
> 打真進程,無法 mock Claude → 採 tech-stack.md 取捨 (A):只斷言「形狀」,接受可能打真 API。
> 對應發布驗證(release gate)。

- [ ] (選用)`GET /` → `200`,body 含 `message`。
- [ ] (選用)`GET /health` → `200`,body 含 `database_configured` / `redis_configured` / `model`。
- [ ] (選用)`POST /chat {"question": "ping"}` smoke → `200` 且含 `answer`。
- [ ] (選用)對**容器版**(T9 起的服務)重跑同一組黑箱斷言。
- **注意**:需先把服務跑起來;`API_BASE_URL=http://localhost:8000 uv run pytest tests/test_e2e.py`。

---

## Definition of Done(對映 plan 的 6 條)

- [ ] **host 能回答**:`curl POST /chat` 回 `{"answer": "..."}`(單一 JSON、非串流)。【T7】
- [ ] **不需 DB 即可啟動**:沒設定 / 沒起 postgres、redis 也能跑並回答(DB/Redis 選填)。【T2 / T5】
- [ ] **缺 key 會 fail fast**:未設 `ANTHROPIC_API_KEY` 時啟動即報清楚的 `ValidationError`。【T2 / T7】
- [ ] **輸入驗證**:空 `question` 回 422(`ChatRequest` `min_length=1`)。【T3 / T7】
- [ ] **可發布**:`docker compose --profile full up --build` 起得來,容器版同一 curl 也回得出答案。【T8 / T9】
- [ ] **文件對齊**:README 迭代 1「待實作清單」對應項目可全部勾掉。

---

## 注意事項彙總(避免踩坑)

- **`/health` 連帶炸點**:`database_url` 改 `str | None = None` 後,現有 `urlparse(settings.database_url)`
  會在 `None` 時拋錯 → T5 必須一併改成回「是否設定」+ model。
- **import 時即建立物件**:`config.py` 在 import 時就建 `Settings()`,`core/llm.py` 在 import 時就建
  `AsyncAnthropic`。缺 `ANTHROPIC_API_KEY` 會在**啟動 / import 當下**失敗 → 測試需在 import app **之前**
  先設假 key(見 tech-stack.md 的 `conftest.py`)。
- **async 一致性**:端點是 `async def`,務必用 `AsyncAnthropic`,勿在事件迴圈內做阻塞 I/O。
- **JSON 欄位 snake_case**:`question` / `answer` / `database_configured` …,測試斷言與 `specs/api.yml` 以此為準。
- **錯誤處理刻意最小**:本迭代不特別包 Anthropic 逾時 / 限流,讓它自然冒 **500**(plan 與 `api.yml` 已載明);
  健全錯誤處理排進後續迭代,勿在此過度設計。
- **不引入後續迭代技術**:串流、Postgres/pgvector、Redis、RAG 一律不碰(見 tech-stack.md「後續迭代才引入」)。

---

## 完成後 → 下一個迭代

迭代 2(SSE 串流):把 `/chat` 從一次回傳整段改為逐字 `text/event-stream` 串流
(`AsyncAnthropic` 的 `messages.stream`)。骨架不變,只換「回應方式」。
