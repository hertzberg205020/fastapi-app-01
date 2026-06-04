# 迭代 1(Iteration 1):Walking Skeleton

> 對應 README「迭代藍圖」第 1 列。這份文件是**可照著做的執行計畫**:規劃、有序步驟(含示範程式碼)、驗收標準。
> 文中所有程式碼皆標「**預計 / 待實作**」——目前 repo 只有 `GET /`、`GET /health`。

## Context

RAG 服務採敏捷增量開發,每個迭代交付一個能 `curl` 驗收的**垂直切片**。第一個迭代刻意做到最薄:

> **`POST /chat` 直接接 Claude,回一句話。不串流、不接資料庫、不做 RAG。**

這個迭代的價值不在功能,而在**打通最難的整條管線**:相依套件 → API key → 路由 →
Anthropic SDK → 可發布的容器映像。骨架一旦立起來,後面所有功能(串流、pgvector、RAG…)
都是往這根骨架上長。

---

## 範圍界定

| | 內容 |
| ----------- | -------------------------------------------------------------- |
| ✅ **In**  | `POST /chat` 非串流接 Claude;host 上開發/debug;容器化並做發布驗證 |
| ❌ **Out** | 串流(迭代 2)、OpenAI 相容 /v1(迭代 3)、對話記憶/Postgres(迭代 4)、RAG/pgvector(迭代 5)、限流/監控/錯誤處理(迭代 6)、加分項(迭代 7)、自動化測試(隨後續迭代補) |

**刻意不做**的事同樣重要:不接 DB、不存對話歷史、不做檢索、不做認證/限流、錯誤處理只做最小。
這些不是遺漏,是排進後面的迭代。

---

## 架構(本迭代)

```ascii
   提問 ──POST /chat──▶ ┌──────────┐ ──▶ ┌────────┐ ──▶ 一句回答 (單一 JSON)
       {"question"}     │ FastAPI  │     │ Claude │      {"answer"}
                        └──────────┘     └────────┘
```

整條路徑同步走完:request 進來 → 呼叫 Anthropic `messages.create` → 取回文字 → 包成 JSON 回傳。

---

## 開發環境 vs 發布產物

敏捷精神:**每個迭代都是可發布的增量**。所以開發跑 host、發布以容器驗證。

| 階段 | 環境 | 做什麼 |
| ---------------------- | ------ | ----------------------------------------------- |
| 開發迴圈(inner loop) | **host** | `uv run uvicorn --reload`,debugger 零設定、改 code 免 rebuild |
| 初步測試               | **host** | `curl POST /chat` 拿到一句回答                   |
| 發布驗證(release gate) | **容器** | `docker compose --profile full up`,確認可發布映像在容器內也 work |

---

## 執行步驟

> 每一步都標出**動到的檔案**與**預計程式碼**。實作時以 `anthropic` 最新 SDK 與當前可用 model 為準。

### Step 0 — 開分支

```bash
git switch -c feat/iteration-1-walking-skeleton
```

### Step 1 — 加 `anthropic` 依賴

```bash
uv add anthropic        # 更新 pyproject.toml 的 dependencies 與 uv.lock
```

> 目前 `pyproject.toml` 只有 `fastapi[standard]` 與 `pydantic-settings`。

### Step 2 — `config.py`:加 Claude 設定、DB/Redis 改選填

動到 `src/fastapi_app_01/config.py`。加入 `anthropic_api_key`(必填)與 `anthropic_model`
(有預設);把 `database_url`/`redis_url` 從必填改為**選填**——本迭代不接 DB。

```python
# 預計:src/fastapi_app_01/config.py
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 迭代 1 必要:沒有 key 就 fail fast。
    anthropic_api_key: str
    anthropic_model: str = "claude-sonnet-4-6"

    # 迭代 4 起才需要 → 本迭代設為選填,缺了也能啟動。
    database_url: str | None = None
    redis_url: str | None = None
```

> ⚠️ **連帶修正**:現有 `main.py` 的 `/health` 直接 `urlparse(settings.database_url)`。
> `database_url` 改成可為 `None` 後,`/health` 要先判斷 `None`(見 Step 5),否則會炸。

### Step 3 — `schemas/chat.py`:請求/回應模型

新增 `src/fastapi_app_01/schemas/chat.py`(連同 `schemas/__init__.py`)。

```python
# 預計:src/fastapi_app_01/schemas/chat.py
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, description="使用者的提問")


class ChatResponse(BaseModel):
    answer: str
```

### Step 4 — `core/llm.py`:封裝 Anthropic 呼叫

新增 `src/fastapi_app_01/core/llm.py`(連同 `core/__init__.py`)。用 **async** client
配合 FastAPI 的 async 端點。

```python
# 預計:src/fastapi_app_01/core/llm.py
from anthropic import AsyncAnthropic

from fastapi_app_01.config import settings

_client = AsyncAnthropic(api_key=settings.anthropic_api_key)


async def answer(question: str) -> str:
    """把問題丟給 Claude,回一段純文字。本迭代:單輪、無 system prompt、無歷史。"""
    msg = await _client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1024,
        messages=[{"role": "user", "content": question}],
    )
    # 非串流回應:內容在 content blocks,第一塊取 text。
    return msg.content[0].text
```

### Step 5 — `api/chat.py`:路由 + 在 `main.py` 註冊

新增 `src/fastapi_app_01/api/chat.py`(連同 `api/__init__.py`):

```python
# 預計:src/fastapi_app_01/api/chat.py
from fastapi import APIRouter

from fastapi_app_01.core import llm
from fastapi_app_01.schemas.chat import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    return ChatResponse(answer=await llm.answer(req.question))
```

在 `src/fastapi_app_01/main.py` 註冊 router,並修掉 `/health` 對 `database_url` 的假設:

```python
# 預計:src/fastapi_app_01/main.py(節錄)
from fastapi import FastAPI

from fastapi_app_01.api.chat import router as chat_router
from fastapi_app_01.config import settings

app = FastAPI()
app.include_router(chat_router)


@app.get("/")
def read_root():
    return {"message": "Hello World"}


@app.get("/health")
def health():
    # database_url 在迭代 1 可能為 None(尚未接 DB)。
    return {
        "database_configured": bool(settings.database_url),
        "redis_configured": bool(settings.redis_url),
        "model": settings.anthropic_model,
    }
```

### Step 6 — `.env.example`:補上 key

動到 `.env.example`(加註解的範本)。`.env` 本身用 `cp -n` 不覆蓋,手動補一行即可。

```bash
# 預計新增到 .env.example
# --- Anthropic ---
ANTHROPIC_API_KEY=sk-ant-...        # 必填
# ANTHROPIC_MODEL=claude-sonnet-4-6 # 可選,預設見 config.py
```

### Step 7 — host 手動驗證(開發完成)

```bash
cp -n .env.example .env             # 已存在不覆蓋;手動補 ANTHROPIC_API_KEY
uv run uvicorn fastapi_app_01.main:app --reload

curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "用一句話解釋什麼是 RAG"}'
# 期望 → {"answer": "..."}
```

### Step 8 — 補 multi-stage uv `Dockerfile`(可發布產物)

新增 repo 根目錄 `Dockerfile`,讓 compose 的 `full` profile(`build: .`)從 placeholder 變可用。

```dockerfile
# 預計:Dockerfile(multi-stage uv)
# ---- builder:裝依賴 ----
FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ---- runtime ----
FROM python:3.12-slim
# compose 的 command 用 `uv run ...`,故 runtime 也保留 uv。
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "fastapi_app_01.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Step 9 — 發布驗證(收工前)

```bash
docker compose --profile full up --build
# 對容器版打同一個 curl(埠一樣 8000):
curl -X POST http://localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"question": "用一句話解釋什麼是 RAG"}'
```

> ⚠️ **compose 的取捨**:目前 `api` 服務 `depends_on` postgres+redis(healthy)、且 `environment:`
> 注入 `DATABASE_URL`/`REDIS_URL`。照現狀 `--profile full up` 會**一併拉起 postgres/redis**,
> 與「本迭代不接 DB」的精神不符(只是能跑、較重)。兩個選項:
> - **(A) 維持現狀**:DB/Redis 跟著起來但 `/chat` 不碰它們。改動最小,先求發布驗證會過。
> - **(B) 為迭代 1 瘦身**(建議):把 `api` 的 `depends_on` 與 DB/Redis `environment` 拿掉,
>   讓發布產物真的只依賴 Claude;等迭代 4 接 DB 時再加回。最誠實,但要動 `docker-compose.yml`。
>
> 本迭代採哪個請在實作時定案並記錄於 commit message。

---

## 驗收標準(Definition of Done)

- [ ] **host 能回答**:`curl POST /chat` 回 `{"answer": "..."}`(單一 JSON、非串流)。
- [ ] **不需 DB 即可啟動**:沒設定/沒起 postgres、redis 也能跑起來並回答(DB/Redis 為選填)。
- [ ] **缺 key 會 fail fast**:未設 `ANTHROPIC_API_KEY` 時啟動即報清楚的 `ValidationError`。
- [ ] **輸入驗證**:空 `question` 回 422(由 `ChatRequest` 的 `min_length=1` 把關)。
- [ ] **可發布**:`docker compose --profile full up --build` 起得來,容器版同一 curl 也回得出答案。
- [ ] **文件對齊**:README 迭代 1「待實作清單」對應項目可全部勾掉。

---

## 風險 / 取捨

- **async vs sync client**:端點是 `async def`,故用 `AsyncAnthropic`,避免在事件迴圈裡做阻塞 I/O。
- **model 選擇**:預設 `claude-sonnet-4-6`(夠用且比 Opus 省);用 `ANTHROPIC_MODEL` 可覆寫。
- **錯誤處理深度**:本迭代刻意最小——不特別包 Anthropic 的逾時/限流錯誤,讓它自然冒 500。
  健全的錯誤處理排進後續迭代,避免在第一個迭代就過度設計。
- **不寫測試**:Walking Skeleton 以「能 curl」為驗收,自動化測試隨 `/chat` 穩定後於後續迭代補
  (屆時把 LLM mock 掉)。這是有意識的取捨,不是疏漏。
- **`/health` 語意改變**:從回傳 DB host/port 改為回傳「是否設定」+ model,反映 DB 在本迭代為選填。

---

## 完成後 → 下一個迭代

迭代 2(SSE 串流):把 `/chat` 從一次回傳整段,改成逐字 `text/event-stream` 串流回傳
(`AsyncAnthropic` 的 `messages.stream`)。骨架不變,只把「回應方式」換成串流。
