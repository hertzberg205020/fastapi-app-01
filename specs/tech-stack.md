# Tech Stack — Iteration 1(Walking Skeleton)

> **用途**:給 Claude Code 與其他開發工具當參考 context——本專案在 **iteration 1** 用到哪些技術、
> 版本、怎麼用、有什麼慣例。
>
> **範圍**:**只涵蓋 iteration 1**(`POST /chat` → Claude,不串流、不接 DB、不做 RAG)。
> PostgreSQL/pgvector、Redis、OpenAI embeddings 等屬於**後續迭代**,iteration 1 **尚未使用**
> (見文末「後續迭代才引入」)。請勿假設它們已在使用中。

---

## 速查表

| 層級 | 技術 | 版本 | 角色 |
| ---------------- | ------------------------- | ------------------- | ----------------------------------- |
| 語言 | Python | 3.12 | 執行環境(`requires-python >=3.12`) |
| 套件 / 建置 | uv | 0.11.14 | 依賴管理、虛擬環境、建置後端、執行 |
| Web 框架 | FastAPI(`fastapi[standard]`) | 0.136.3 | REST 端點、請求驗證、`/docs` |
| ASGI 底層 | Starlette | 1.2.1 | FastAPI 的底層(routing/ASGI) |
| ASGI server | Uvicorn | 0.48.0 | 跑 FastAPI app(`--reload` 開發) |
| 資料驗證 | Pydantic v2 | 2.13.4(core 2.46.4) | 請求/回應模型(`ChatRequest/Response`) |
| 設定管理 | pydantic-settings | 2.14.1 | 從環境變數 / `.env` 載入設定 |
| HTTP client(transitive) | httpx | 0.28.1 | anthropic SDK、FastAPI TestClient 用 |
| LLM SDK | anthropic(Python) | `uv add` 時鎖最新 | 呼叫 Claude(`AsyncAnthropic`) |
| 容器化 | Docker / docker compose | v2 | 可發布映像 + 發布驗證(`full` profile) |
| LLM 服務 | Anthropic Claude | model `claude-sonnet-4-6`(預設) | 產生回答 |

---

## 各技術詳述

### Python 3.12
- **用途**:專案執行環境。`.python-version` 釘 `3.12`,`pyproject.toml` 要求 `>=3.12`。
- **本專案怎麼用**:大量使用 type hints;設定用 `str | None`(PEP 604)等 3.10+ 語法。
- **文件**:https://docs.python.org/3.12/

### uv 0.11.14
- **用途**:取代 pip/venv/build 的一體工具。依賴鎖在 `uv.lock`,建置後端是 `uv_build`。
- **本專案怎麼用**:
  - `uv add <pkg>` 加依賴(會同步 `pyproject.toml` + `uv.lock`)。
  - `uv sync --frozen` 依 lock 還原環境(Dockerfile 用)。
  - `uv run uvicorn fastapi_app_01.main:app --reload` 在 host 開發。
- **文件**:https://docs.astral.sh/uv/

### FastAPI 0.136.3(`fastapi[standard]`)
- **用途**:定義 REST 端點、自動請求驗證、自動 `/docs`(Swagger UI)。
- **`[standard]` extra** 已含:Uvicorn、Starlette、Pydantic、`python-multipart`、httpx 等,
  所以不必個別安裝 uvicorn。
- **本專案怎麼用**:`APIRouter` 拆路由(`api/chat.py`),`main.py` 以 `app.include_router(...)` 註冊;
  端點用 `async def`。
- **文件**:https://fastapi.tiangolo.com/

### Uvicorn 0.48.0
- **用途**:ASGI server,實際跑 FastAPI app。
- **本專案怎麼用**:
  - host 開發:`uv run uvicorn fastapi_app_01.main:app --reload`
  - 容器:`uvicorn fastapi_app_01.main:app --host 0.0.0.0 --port 8000`(見 `docker-compose.yml`)
  - reload 可由 `UVICORN_RELOAD` 控制(專案既有慣例)。
- **文件**:https://www.uvicorn.org/

### Pydantic v2 2.13.4
- **用途**:request/response 的資料模型與驗證。
- **本專案怎麼用**:`schemas/chat.py` 定義 `ChatRequest`(`question: str`,`min_length=1`)、
  `ChatResponse`(`answer: str`);FastAPI 用它做自動驗證與 OpenAPI schema。
- **文件**:https://docs.pydantic.dev/latest/

### pydantic-settings 2.14.1
- **用途**:集中式設定,從環境變數(優先)再 `.env` 載入並驗證。
- **本專案怎麼用**:`config.py` 的 `Settings(BaseSettings)`,在 import 時建立 `settings` 單例,
  各處 `from fastapi_app_01.config import settings` 取用。`.env` 路徑錨定在專案根(不受 cwd 影響)。
  iteration 1 會新增 `anthropic_api_key`(必填)、`anthropic_model`(預設);`database_url`/`redis_url` 改選填。
- **文件**:https://docs.pydantic.dev/latest/concepts/pydantic_settings/

### anthropic(Python SDK)
- **用途**:呼叫 Anthropic Claude 產生回答。iteration 1 用 `uv add anthropic` 引入(安裝時鎖最新穩定版)。
- **本專案怎麼用**:FastAPI 端點是 async,故用 **`AsyncAnthropic`**:
  ```python
  from anthropic import AsyncAnthropic
  client = AsyncAnthropic(api_key=settings.anthropic_api_key)
  msg = await client.messages.create(
      model=settings.anthropic_model,           # 預設 claude-sonnet-4-6
      max_tokens=1024,
      messages=[{"role": "user", "content": question}],
  )
  answer = msg.content[0].text                  # 非串流:取第一個 content block 的 text
  ```
- **注意**:iteration 1 非串流;迭代 2 才改用 `client.messages.stream(...)`。
- **文件**:SDK https://github.com/anthropics/anthropic-sdk-python ・ API https://docs.anthropic.com/en/api/

### Docker / docker compose(v2)
- **用途**:把 API 打包成**可發布映像**,並做發布驗證(release gate)。
- **本專案怎麼用**:
  - `docker-compose.yml` 的 `api` 服務藏在 `full` profile(`build: .`),iteration 1 要補 **multi-stage uv `Dockerfile`** 讓它可用。
  - 發布驗證:`docker compose --profile full up --build`。
  - 開發**不**用容器(host 跑即可),容器只在收工前驗證可發布。
- **注意**:現有 `api` 服務 `depends_on` postgres+redis,iteration 1 不需 DB——實作時決定是否為本迭代瘦身
  (詳見 `plans/iteration-1-walking-skeleton.md` Step 9)。
- **文件**:https://docs.docker.com/compose/

---

## 專案慣例(工具請遵循)

- **原始碼布局**:`src/` layout,套件在 `src/fastapi_app_01/`;模組以 `fastapi_app_01.xxx` 匯入。
- **設定**:一律經 `config.py` 的 `settings` 單例,不要在各處直接讀 `os.environ`。
- **祕密**:`.env`(已 gitignore)放真值;`.env.example` 放範本。用 `cp -n` 避免覆蓋既有 `.env`。
- **async 一致性**:端點 `async def` 就搭 async client(`AsyncAnthropic`),勿在事件迴圈內做阻塞 I/O。
- **路由**:每個資源一個 `APIRouter` 模組(`api/`),於 `main.py` 統一註冊。

## 常用指令

```bash
# 依賴
uv add anthropic                 # 加依賴(同步 pyproject.toml + uv.lock)
uv sync --frozen                 # 依 lock 還原環境

# 開發(host)
uv run uvicorn fastapi_app_01.main:app --reload

# 發布驗證(容器)
docker compose --profile full up --build
```

---

## 後續迭代才引入(iteration 1 尚未使用)

> 以下技術已出現在 repo 的基礎建設(如 `docker-compose.yml` 的 postgres/redis),但 **iteration 1 不使用**。
> 工具請勿假設它們已接上。

| 技術 | 角色 | 預計迭代 |
| ----------------------- | ----------------------- | ------ |
| PostgreSQL + pgvector(`pgvector/pgvector:pg16`) | 對話/文件持久化、向量檢索 | 迭代 3 |
| OpenAI embeddings(或等價) | 文字轉向量 | 迭代 4 |
| Redis(`redis:7-alpine`) | 限流 | 迭代 6 |
| 監控 / metrics | `/metrics` 觀測 | 迭代 7 |

---

## 延伸閱讀

- 迭代藍圖與當前範圍:`README.md`(迭代藍圖 Roadmap)
- iteration 1 執行計畫(步驟 + DoD):`plans/iteration-1-walking-skeleton.md`
