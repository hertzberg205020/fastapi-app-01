# RAG Service(敏捷迭代練習)

一個以**敏捷增量**方式逐步長出來的「知識庫問答」後端。終局願景是:上傳文件 → 切塊 → 存進向量資料庫 → 檢索 → 用 LLM 串流回答。

但我們**不一次端出整套**。改成一個迭代一個迭代地推進,每次迭代交付一個**垂直切片(vertical slice)**——貫穿各層、能 `curl` 出結果的薄片,而非水平堆一層基礎建設。每一片都把最難的風險先打通。

> ✅ **迭代 1(Walking Skeleton)已完成**:FastAPI + Docker 跑起來,`POST /chat` 直接接 Claude(**不串流、不接資料庫、不做 RAG**),host 與容器版 `curl` 都能拿到一句回答。最難的整條管線(容器、API key、路由)已打通——後面所有功能都是往這根骨架上長。
>
> 🎯 **下一個迭代 = SSE 串流**:把 `/chat` 從一次回傳整段,改成逐字串流(Server-Sent Events)。骨架不變,只換回應方式。

技術組合(終局)對應 JD 的基本條件:**FastAPI(REST + SSE 串流)、PostgreSQL + pgvector、Redis 限流、Anthropic Claude、Docker Compose**。

> ⚠️ 這是「練習骨架」,不是現成可交的作品。基礎建設已接好,核心邏輯依重要性**一個迭代一個迭代長出來**;標 `TODO` 的部分請你自己動手,那才是面試官會問、也是展現能力的地方。

---

## 迭代藍圖(Roadmap)

每個迭代都交付一個能獨立 `curl` 驗收的**垂直切片**,不是水平堆基礎建設。

| 迭代 | 名稱 | 內容 | 狀態 |
| ---- | --------------------- | -------------------------------------------------------- | -------- |
| 1    | **Walking Skeleton**  | `POST /chat` → Claude → 一句回答。不串流 / 不接 DB / 不做 RAG | ✅ **完成** |
| 2    | SSE 串流              | `/chat` 改逐字串流回傳(Server-Sent Events)               | 🚧 下一步 |
| 3    | OpenAI 相容 `/v1`     | 新增 `/v1/chat/completions`(OpenAI 相容、串流),可接 Open WebUI 等前端;多輪歷史由前端帶入 | ⬜       |
| 4    | 對話記憶              | 接 Postgres 存對話歷史、支援多輪(伺服器端持久化)        | ⬜       |
| 5    | 知識庫 / RAG          | `/documents` 上傳 → 切塊 → embedding → pgvector;`/chat` 先檢索再回答 | ⬜       |
| 6    | 上線品質(Hardening)  | Redis 限流、健康檢查、錯誤處理、`/metrics`、補測試         | ⬜       |
| 7    | 加分項                | PDF / Word 解析、檢索 re-rank、引用來源、滑動視窗限流      | ⬜       |

**迭代 1、2、3** 只需要 Claude(`/v1` 的多輪歷史由前端帶入);**Postgres 從迭代 4 起**、**Redis 從迭代 6 起** 才需要容器。

---

## 架構

### 當前(迭代 1):Walking Skeleton

```ascii
   提問 ──POST /chat──▶ ┌──────────┐ ──▶ ┌────────┐ ──▶ 一句回答 (單一 JSON)
                        │ FastAPI  │     │ Claude │
                        └──────────┘     └────────┘
```

### 終局目標架構(後續迭代逐步補齊)

```ascii
              ┌──────────────┐
   上傳文件 ──▶│  /documents  │── 切塊 ─▶ Embedding ─▶ ┐
              └──────────────┘                        │
                                                 ┌─────▼──────────────┐
   提問 ──────▶┌──────────────┐── 檢索相近片段 ──│ PostgreSQL+pgvector │
              │    /chat      │◀────────────────└────────────────────┘
              └──────┬───────┘
                     │ 組 Prompt + 對話歷史
                     ▼
              ┌──────────────┐
              │ Claude (串流) │──▶ SSE 逐字回傳給前端
              └──────────────┘

   限流: 每次請求先過 Redis 檢查 (每 IP 每分鐘上限)
```

---

## 迭代 1(Iteration 1):Walking Skeleton ✅

### 目標

host 上 `curl POST /chat` 得到 Claude 的一句回答,並能以容器形式發布。整條管線(API key → 路由 → Claude → 可發布映像)一次打通。

### 開發環境 vs 發布產物

敏捷的精神是「每個迭代都是可發布的增量」。所以開發跑在 host、發布以容器驗證,兩者分工:

| 階段 | 環境 | 做什麼 |
| ---------------------- | ------ | ----------------------------------------------- |
| 開發迴圈(inner loop) | **host** | `uv run uvicorn --reload`,debugger 零設定、改 code 免 rebuild |
| 初步測試               | **host** | `curl POST /chat` 拿到一句回答                   |
| 發布驗證(release gate) | **容器** | 建 image 跑起來,確認可發布產物在容器內也 work,才算 Done |

### 驗收標準(Definition of Done)

```bash
# host 開發版:
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "用一句話解釋什麼是 RAG"}'
# → {"answer": "..."}   # 非串流,單一 JSON 回應
```

並且「可發布」:`docker compose --profile full up` 起得來、同一個 curl 打容器版也回得出答案。

### 完成項目(Done)

> 以下是這次迭代動到的程式碼,皆已完成,上面的驗收標準均已通過(host + 容器 `curl`、`uv run pytest` 綠燈)。

- [x] `pyproject.toml`:加 `anthropic` 依賴
- [x] `config.py`:加 `anthropic_api_key`;把 `database_url` / `redis_url` 改為**選填**(本迭代不接 DB)
- [x] 新增 `POST /chat` 路由:非串流,直接呼叫 Claude 回傳 `{"answer": ...}`
- [x] `.env.example`:加 `ANTHROPIC_API_KEY`
- [x] 補 multi-stage uv `Dockerfile` → 讓 compose `full` profile 從 placeholder 變可用(發布產物)
- [x] 開發只需 `ANTHROPIC_API_KEY`,**不需** postgres / redis

---

## 快速啟動(迭代 1)

> ✅ 迭代 1 已完成,以下指令可直接執行(`/chat`、`Dockerfile` 均已落地)。

### 開發 / debug(日常):在 host 跑

迭代 1 無第三方服務,直接在 host 跑最小且最快,debugger 也零設定。

```bash
# 1. 設定環境變數(-n: .env 已存在就不覆蓋,保留你現有的值)
cp -n .env.example .env
#    手動補上 ANTHROPIC_API_KEY 一行

# 2. host 啟動 API(本迭代不需 postgres / redis)
uv run uvicorn fastapi_app_01.main:app --reload

# 3. 提問,拿到一句回答
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "用一句話解釋什麼是 RAG"}'

# 4. 互動式 API 文件
open http://localhost:8000/docs
```

### 發布驗證(收工前):確認可發布產物能在容器內跑

```bash
docker compose --profile full up --build   # Dockerfile 已就緒
# 對容器版打同一個 curl,確認也回得出答案 → 這次迭代才算 Done
```

---

## 資料夾說明

### 現在實際有的

| 路徑                  | 職責                                          |
| --------------------- | --------------------------------------------- |
| `src/fastapi_app_01/main.py`         | FastAPI 進入點;`GET /`、`GET /health`、註冊 chat router |
| `src/fastapi_app_01/config.py`       | 用 pydantic-settings 集中讀取環境變數         |
| `src/fastapi_app_01/api/chat.py`     | `POST /chat` 路由(迭代 1:非串流)            |
| `src/fastapi_app_01/core/llm.py`     | 封裝 Anthropic 生成(`AsyncAnthropic`)        |
| `src/fastapi_app_01/schemas/chat.py` | 請求 / 回應的 Pydantic 模型                   |
| `Dockerfile`          | multi-stage uv 建置(可發布映像)              |
| `tests/`              | `POST /chat` 的 in-process 測試(TestClient)  |
| `scripts/init_db.sql` | 啟用 pgvector(建表 schema 仍為註解,對話表待迭代 4、向量表待迭代 5)|

### 後續迭代才加入(尚未存在)

| 路徑                     | 職責                                          | 迭代 |
| ------------------------ | --------------------------------------------- | ---- |
| `app/api/openai_compat.py` | OpenAI 相容 `/v1/chat/completions`(接 Open WebUI) | 3    |
| `app/db/database.py`     | PostgreSQL 連線池(Redis client 待迭代 6)      | 4    |
| `app/db/repository.py`   | 所有 SQL 集中於此                             | 4    |
| `app/api/documents.py`   | 文件上傳 / 匯入端點                           | 5    |
| `app/core/embeddings.py` | 文字轉向量(預設 OpenAI)                       | 5    |
| `app/core/rag.py`        | **核心**:切塊 + 檢索 + Prompt 組裝(多處 TODO) | 5    |
| `app/core/rate_limit.py` | Redis 限流                                    | 6    |
| `app/api/health.py`      | 健康檢查(目前 inline 在 main.py)             | 6    |

---

## 本機開發(混合模式,推薦)

日常開發採「**基礎服務容器化、API 本機跑**」:Postgres / Redis 用 compose 起(**迭代 4 起才需要**),
FastAPI 用 PyCharm 綠色三角(或 `uv run`)在本機跑並連 `localhost`。好處是
debugger 零設定即可中斷、`--reload` 即時、改 code 免 rebuild image。

```bash
# 1. 準備環境變數(.env 已 gitignore;-n: 已存在不覆蓋)
cp -n .env.example .env

# 2. (迭代 4 起)只啟動相依服務
docker compose up -d postgres redis
docker compose ps                 # 等 postgres / redis 變 healthy

# 3. 本機跑 API(等同 PyCharm 綠色三角)
uv run uvicorn fastapi_app_01.main:app --reload
curl http://localhost:8000/        # {"message":"Hello World"}
```

**PyCharm 綠色三角設定**:既有的 FastAPI run config 結構不必改,只要補上連線環境變數
(Run config → Environment variables,或裝 EnvFile plugin 載入 `.env`):

```
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/ragdb
REDIS_URL=redis://localhost:6379/0
```

> **host 差異**:本機跑 API 連 `localhost`(容器對外 publish 的 port);
> 若 API 也在容器內跑,則用服務名 `postgres` / `redis`——這部分 compose 會自動以
> `environment:` 覆寫,你不用手動切。

**偶爾做全容器 / parity 驗證**(multi-stage uv `Dockerfile` 已就緒):

```bash
docker compose --profile full up      # 含 api
docker compose --profile full watch   # 改 code 自動同步進容器
```

---

## 跑測試

> 迭代 1 已有 `POST /chat` 的 in-process 測試(`tests/`,Claude 被 mock);後續迭代持續補上。

```bash
uv run pytest
```

---

## 待辦事項(對齊迭代藍圖)

把骨架變成「能拿去面試」的關鍵,就是把每個迭代做扎實。下面 TODO 標出所屬迭代:

- ~~**迭代 1(Walking Skeleton)**:加 `anthropic` 依賴、`POST /chat` 非串流接 Claude、`ANTHROPIC_API_KEY` 設定。~~ ✅ 完成
- **迭代 2(串流,下一步)**:`/chat` 改 SSE 逐字回傳。
- **迭代 3(OpenAI 相容 `/v1`)**:新增 `/v1/chat/completions`(OpenAI 相容、串流),可接 Open WebUI 等前端;多輪歷史由前端帶入,無需伺服器端持久化。
- **迭代 4(對話記憶)**:接 Postgres 存對話歷史、支援多輪(伺服器端持久化);uncomment `init_db.sql` 的對話表 schema 並客製。
- **迭代 5(知識庫 / RAG)**:`/documents` 上傳純文字 + **切塊策略**(從固定字數改成依語意 / 句子邊界,並說明取捨)+ embedding + pgvector;`/chat` 先檢索再回答(整條垂直切片)。
- **迭代 6(上線品質)**:Redis 限流(固定視窗)、健康檢查、錯誤處理、`/metrics`(請求數、延遲、token 用量)、補 API 層測試。
- **迭代 7(加分)**:PDF / Word 解析、檢索 **re-rank**、**引用來源**(標出答案來自哪個片段)、滑動視窗 / token bucket 限流。
- **貫穿各迭代**:補 API 層測試,把 LLM / Embedding / DB mock 掉。

> 小提醒:作業好不好,常不在「做了多少功能」,而在你能不能清楚講出**每個設計選擇的理由與取捨**。把你做的決定寫進這份 README,會比多寫一個功能更有說服力。
