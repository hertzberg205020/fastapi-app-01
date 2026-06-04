# Tech Stack — Iteration 1(Walking Skeleton)

> **定位**:本檔為 **迭代 1** 技術棧參考;**迭代 2 的串流變更**(`/chat` 改 SSE、`messages.stream`、
> 移除 `ChatResponse`)見 `plans/iteration-2-streaming.md`;**迭代 3 已加 OpenAI 相容 `/v1`**
> (`/v1/chat/completions`、`/v1/models`、多輪 + system 轉接)見 `plans/iteration-3-openai-compat.md`。
> 檔內 `messages.create` / `r.json()["answer"]` 等為**迭代 1 範例**,請勿當成最新狀態。
>
> **用途**:給 Claude Code 與其他開發工具當參考 context——本專案在 **iteration 1** 用到哪些技術、
> 版本、怎麼用、有什麼慣例、以及**怎麼驗收**。
>
> **範圍**:**只涵蓋 iteration 1**(`POST /chat` → Claude,不串流、不接 DB、不做 RAG)。
> PostgreSQL/pgvector、Redis、OpenAI embeddings 等屬於**後續迭代**,iteration 1 **尚未使用**
> (見文末「後續迭代才引入」)。請勿假設它們已在使用中。

---

## 應用技術棧

| 面向 | 選擇 | 版本 |
| ---------------- | ------------------------- | ------------------- |
| 語言 | Python | 3.12 |
| 套件 / 建置 | uv | 0.11.14 |
| Web 框架 | FastAPI(`fastapi[standard]`) | 0.136.3 |
| ASGI 底層 | Starlette | 1.2.1 |
| ASGI server | Uvicorn | 0.48.0 |
| 資料驗證 | Pydantic v2 | 2.13.4(core 2.46.4) |
| 設定管理 | pydantic-settings | 2.14.1 |
| HTTP client(transitive) | httpx | 0.28.1 |
| LLM SDK | anthropic(Python,`AsyncAnthropic`) | `uv add` 時鎖最新 |
| LLM 服務 | Anthropic Claude | model `claude-sonnet-4-6`(預設) |
| 容器化 | Docker / docker compose | v2 |

## 測試技術棧

> 回答「手動 `curl` 能不能用測試框架驗收?」——**可以**。`curl` 就是一次 HTTP 呼叫,
> 測試框架做的是「發同樣的請求 + 對回應下斷言」。本專案分兩個層級(見下方對照表)。
>
> ⚠️ **與現行 DoD 的關係**:README / `plans/iteration-1-walking-skeleton.md` 目前把自動測試列為
> **後續補上**(iteration 1 以手動 curl 驗收)。本節是「採用測試時請依此模式」的**參考**,不是硬性完成條件。

| 面向 | 選擇 |
| --------------- | ------------------------------------------------ |
| 測試框架 | pytest(`uv add --dev pytest`) |
| HTTP 測試(主) | FastAPI `TestClient`(in-process,httpx 為底,免起 server) |
| HTTP 測試(E2E) | httpx `Client`(對跑起來的 host/容器服務做黑箱) |
| LLM 模擬 | monkeypatch `llm.answer`(避免打真 Anthropic API) |
| 非同步 | `TestClient` 同步介面即可跑 async 端點 |
| 測試隔離 | iteration 1 無 DB → 無需 truncate;只需重置被 mock 的接縫 |
| 環境 | `conftest.py` 先設假 `ANTHROPIC_API_KEY`(見 gotcha) |

---

## 依賴現況(已裝 vs 待裝)

> 給開發工具一眼看懂:現在裝了什麼、iteration 1 還要 `uv add` 什麼。

**已安裝**(`pyproject.toml` + `uv.lock`):
- `fastapi[standard]` 0.136.3 —— extra 已帶進 `uvicorn` 0.48.0、`starlette` 1.2.1、`pydantic` 2.13.4、
  `httpx` 0.28.1、`anyio` 4.13.0、`python-multipart` 等。
- `pydantic-settings` 2.14.1。
- ⇒ **`TestClient` 已可用**(靠既有的 httpx + anyio),無需額外安裝。

**iteration 1 待安裝**:

| 套件 | 用途 | 必要性 | 指令 |
| ---------- | ----------------------------- | --------------- | ---------------------- |
| `anthropic` | 呼叫 Claude(`AsyncAnthropic`) | **必裝**(runtime) | `uv add anthropic` |
| `pytest` | 自動化測試(採用文件測試時) | 選用(dev) | `uv add --dev pytest` |

**不需要**:`requests`(改用 httpx)、`pytest-asyncio`(文件用的 `TestClient` 是同步介面)、
`uvicorn`(已含於 `fastapi[standard]`)。

---

## 各技術詳述

### Python 3.12
- **用途**:專案執行環境。`.python-version` 釘 `3.12`,`pyproject.toml` 要求 `>=3.12`。
- **本專案怎麼用**:大量 type hints;設定用 `str | None`(PEP 604)等 3.10+ 語法。
- **文件**:https://docs.python.org/3.12/

### uv 0.11.14
- **用途**:取代 pip/venv/build 的一體工具。依賴鎖在 `uv.lock`,建置後端是 `uv_build`。
- **本專案怎麼用**:
  - `uv add <pkg>` / `uv add --dev <pkg>` 加(開發)依賴。
  - `uv sync --frozen` 依 lock 還原環境(Dockerfile 用)。
  - `uv run uvicorn ...` / `uv run pytest` 執行。
- **文件**:https://docs.astral.sh/uv/

### FastAPI 0.136.3(`fastapi[standard]`)
- **用途**:定義 REST 端點、自動請求驗證、自動 `/docs`。
- **`[standard]` extra** 已含:Uvicorn、Starlette、Pydantic、`python-multipart`、**httpx**(故 `TestClient` 免額外安裝)。
- **本專案怎麼用**:`APIRouter` 拆路由(`api/chat.py`),`main.py` 以 `app.include_router(...)` 註冊;端點 `async def`。
- **文件**:https://fastapi.tiangolo.com/

### Uvicorn 0.48.0
- **用途**:ASGI server,實際跑 FastAPI app。
- **本專案怎麼用**:host 開發 `uv run uvicorn fastapi_app_01.main:app --reload`;容器 `--host 0.0.0.0 --port 8000`。reload 可由 `UVICORN_RELOAD` 控制。
- **文件**:https://www.uvicorn.org/

### Pydantic v2 2.13.4 / pydantic-settings 2.14.1
- **用途**:資料模型驗證(Pydantic)+ 集中式設定(pydantic-settings)。
- **本專案怎麼用**:
  - `schemas/chat.py`:`ChatRequest`(`question: str`,`min_length=1`)、`ChatResponse`(`answer: str`)。
  - `config.py`:`Settings(BaseSettings)`,import 時建 `settings` 單例;`.env` 路徑錨定專案根。
    iteration 1 新增 `anthropic_api_key`(必填)、`anthropic_model`(預設);`database_url`/`redis_url` 改選填。
- **文件**:https://docs.pydantic.dev/latest/ ・ https://docs.pydantic.dev/latest/concepts/pydantic_settings/

### anthropic(Python SDK)
- **用途**:呼叫 Claude 產生回答。`uv add anthropic` 引入。
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
- **注意**:此為 iteration 1 非串流範例;**迭代 2 已採用** `client.messages.stream(...)` 逐字串流(見 `plans/iteration-2-streaming.md`)。
- **文件**:SDK https://github.com/anthropics/anthropic-sdk-python ・ API https://docs.anthropic.com/en/api/

### pytest + FastAPI TestClient + httpx
- **用途**:把手動 `curl` 驗收自動化(發請求 + 斷言)。
- **本專案怎麼用**:見下方「測試 Fixtures」與「測試層級對照」。`TestClient` 在記憶體內呼叫 app(免起 server);
  httpx `Client` 則對真的跑起來的服務做黑箱 E2E。Claude 一律 mock,避免花錢/不穩/需金鑰。
- **文件**:pytest https://docs.pytest.org/ ・ TestClient https://fastapi.tiangolo.com/reference/testclient/ ・ httpx https://www.python-httpx.org/

### Docker / docker compose(v2)
- **用途**:把 API 打包成**可發布映像**,並做發布驗證(release gate)。
- **本專案怎麼用**:`api` 服務在 `full` profile(`build: .`),iteration 1 補 **multi-stage uv `Dockerfile`**;發布驗證 `docker compose --profile full up --build`。開發**不**用容器。
- **注意**:現有 `api` 服務 `depends_on` postgres+redis,iteration 1 不需 DB——是否瘦身見 `plans/iteration-1-walking-skeleton.md` Step 9。
- **文件**:https://docs.docker.com/compose/

---

## 測試 Fixtures(預計;`tests/conftest.py`)

> 所有程式碼標「**預計**」——目前 repo 尚無 `tests/`。採用測試時依此模式建立。

```python
# tests/conftest.py(預計)
import os

# Gotcha:config.py 在 import 時就建立 Settings(),anthropic_api_key 必填;
# llm.py 也在 import 時建立 AsyncAnthropic。故必須在「import app 之前」就備妥假金鑰。
# conftest.py 於測試模組之前載入,這行放最上方即可。
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    """In-process:免起 server,並 mock 掉 Claude(在 llm.answer 接縫換假回應)。"""
    from fastapi_app_01.core import llm

    async def fake_answer(question: str) -> str:
        return f"stub answer for: {question}"

    monkeypatch.setattr(llm, "answer", fake_answer)

    from fastapi_app_01.main import app
    with TestClient(app) as c:          # with 區塊會觸發 app lifespan
        yield c


@pytest.fixture
def api_client():
    """黑箱 E2E:對「已經跑起來」的服務(host 或容器)打,httpx 原生支援 base_url。"""
    base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
    with httpx.Client(base_url=base_url, headers={"Content-Type": "application/json"}) as c:
        yield c
```

### In-process 測試(主)

```python
# tests/test_chat.py(預計)
def test_chat_returns_answer(client):
    r = client.post("/chat", json={"question": "用一句話解釋什麼是 RAG"})
    assert r.status_code == 200
    assert r.json()["answer"]                    # 等同 curl,但可程式斷言

def test_chat_rejects_empty_question(client):
    r = client.post("/chat", json={"question": ""})
    assert r.status_code == 422                   # 由 ChatRequest 的 min_length=1 把關
```

### 黑箱 E2E(發布驗證)

```python
# tests/test_e2e.py(預計;需先把服務跑起來)
def test_chat_smoke(api_client):
    r = api_client.post("/chat", json={"question": "ping"})
    assert r.status_code == 200
    assert "answer" in r.json()
```

> 黑箱跑的是**真進程**,無法用 monkeypatch mock Claude。取捨:
> (A) 當 smoke test,只斷言「形狀」(200 + 有 `answer`),接受可能打真 API;
> (B) 讓 app 支援 stub 模式(env 旗標)再做黑箱。iteration 1 建議 (A)。

---

## 測試層級對照

| 面向 | 手動 `curl` | In-process `TestClient` | 黑箱 E2E（httpx） |
| ------------ | ----------- | ----------------------- | ----------------- |
| 需起 server | 是 | **否**(記憶體內) | 是(host / 容器) |
| Claude | 真打 | **mock** | 真打或 stub |
| 速度 | 看手速 | **最快** | 中 |
| 斷言 | 人眼看 | 程式斷言 | 程式斷言 |
| 適用 | 臨時試 | 開發迴圈、CI | 發布驗證(release gate) |

---

## 紅燈階段定義(TDD;採 test-first 時)

「紅燈階段」——先寫會失敗的測試,再實作讓它變綠。

### 需要先定義(紅燈)
- `tests/conftest.py`(env 設定 + mock + `client` fixtures)
- `tests/test_chat.py`(對 `/chat` 的 happy-path + 422 斷言)

### 不定義(留到綠燈才實作)
- `api/chat.py` 的 `/chat` 路由、`core/llm.py` 的 `llm.answer`

### 測試失敗原因(紅燈)
- HTTP **404**(`/chat` 尚未實作)→ 實作路由後轉綠。

---

## 專案結構

```
fastapi-app-01/
├── src/fastapi_app_01/
│   ├── __init__.py            # 既有:entry point
│   ├── main.py                # 既有:/ 、/health(iteration 1:include chat router)
│   ├── config.py              # 既有:Settings 單例
│   ├── api/chat.py            # 預計(iteration 1):POST /chat
│   ├── core/llm.py            # 預計(iteration 1):AsyncAnthropic 封裝
│   └── schemas/chat.py        # 預計(iteration 1):ChatRequest / ChatResponse
├── tests/                     # 預計:採用測試時建立
│   ├── conftest.py            #   env + mock Claude + client / api_client fixtures
│   ├── test_chat.py           #   in-process /chat
│   └── test_e2e.py            #   黑箱 E2E(選用)
├── scripts/init_db.sql        # 既有:pgvector(schema 仍註解,對話表迭代 4、向量表迭代 5)
├── docker-compose.yml         # 既有:api 在 full profile
├── Dockerfile                 # 預計(iteration 1):multi-stage uv
├── pyproject.toml / uv.lock   # 既有
└── README.md
```

---

## 專案慣例(工具請遵循)

- **原始碼布局**:`src/` layout,套件在 `src/fastapi_app_01/`;以 `fastapi_app_01.xxx` 匯入。
- **設定**:一律經 `config.py` 的 `settings` 單例,勿在各處直接讀 `os.environ`。
- **祕密**:`.env`(已 gitignore)放真值;`.env.example` 放範本。用 `cp -n` 避免覆蓋既有 `.env`。
- **async 一致性**:端點 `async def` 就搭 async client(`AsyncAnthropic`),勿在事件迴圈內做阻塞 I/O。
- **路由**:每個資源一個 `APIRouter` 模組(`api/`),於 `main.py` 統一註冊。
- **JSON 欄位命名**:本專案請求/回應用 snake_case(`question` / `answer`),測試斷言以此為準。
- **測試接縫**:路由呼叫 `await llm.answer(...)`(模組屬性),測試在此 monkeypatch,不必碰 Anthropic SDK 內部。

## 常用指令

```bash
# 依賴
uv add anthropic                 # 應用依賴(同步 pyproject.toml + uv.lock)
uv add --dev pytest              # 測試依賴(dev group)
uv sync --frozen                 # 依 lock 還原環境

# 開發(host)
uv run uvicorn fastapi_app_01.main:app --reload

# 測試
uv run pytest                    # in-process(免起 server)
API_BASE_URL=http://localhost:8000 uv run pytest tests/test_e2e.py   # 黑箱(需先起服務)

# 發布驗證(容器)
docker compose --profile full up --build
```

---

## 後續迭代才引入(iteration 1 尚未使用)

> 以下已出現在 repo 基礎建設(如 `docker-compose.yml` 的 postgres/redis),但 **iteration 1 不使用**。工具請勿假設它們已接上。

| 技術 | 角色 | 預計迭代 |
| ----------------------- | ----------------------- | ------ |
| PostgreSQL(`pgvector/pgvector:pg16`) | 對話歷史持久化 | 迭代 4 |
| pgvector(同上映像) | 向量儲存 / 檢索 | 迭代 5 |
| OpenAI embeddings(或等價) | 文字轉向量 | 迭代 5 |
| Redis(`redis:7-alpine`) | 限流 | 迭代 6 |
| 監控 / metrics | `/metrics` 觀測 | 迭代 6 |
| **Testcontainers + SQLAlchemy** E2E | 對真 DB 的整合測試與隔離 | 迭代 4+(接 DB 後) |

---

## 延伸閱讀

- 迭代藍圖與當前範圍:`README.md`(迭代藍圖 Roadmap)
- iteration 1 執行計畫(步驟 + DoD):`plans/iteration-1-walking-skeleton.md`
