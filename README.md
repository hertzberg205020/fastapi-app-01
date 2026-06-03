# RAG Service(敏捷迭代練習)

一個以**敏捷增量**方式逐步長出來的「知識庫問答」後端。終局願景是:上傳文件 → 切塊 → 存進向量資料庫 → 檢索 → 用 LLM 串流回答。

但我們**不一次端出整套**。改成一個迭代一個迭代地推進,每次迭代交付一個**垂直切片(vertical slice)**——貫穿各層、能 `curl` 出結果的薄片,而非水平堆一層基礎建設。每一片都把最難的風險先打通。

> 🎯 **當前迭代 = Walking Skeleton**:FastAPI + Docker 跑起來,`POST /chat` 直接接 Claude,**不串流、不接資料庫、不做 RAG**,`curl` 能拿到一句回答就收工。
>
> 這次迭代的價值:證明最難的整條管線(容器、API key、路由)是通的——後面所有功能都是往這根骨架上長。

技術組合(終局)對應 JD 的基本條件:**FastAPI(REST + SSE 串流)、PostgreSQL + pgvector、Redis 限流、Anthropic Claude、Docker Compose**。

> ⚠️ 這是「練習骨架」,不是現成可交的作品。基礎建設已接好,核心邏輯依重要性**一個迭代一個迭代長出來**;標 `TODO` 的部分請你自己動手,那才是面試官會問、也是展現能力的地方。

---

## 迭代藍圖(Roadmap)

每個迭代都交付一個能獨立 `curl` 驗收的**垂直切片**,不是水平堆基礎建設。

| 迭代 | 名稱 | 內容 | 狀態 |
| ---- | --------------------- | -------------------------------------------------------- | -------- |
| 1    | **Walking Skeleton**  | `POST /chat` → Claude → 一句回答。不串流 / 不接 DB / 不做 RAG | ✅ **進行中** |
| 2    | SSE 串流              | `/chat` 改逐字串流回傳(Server-Sent Events)               | ⬜ 規劃中 |
| 3    | 持久化                | Postgres + pgvector 落地(對話 / 文件)                    | ⬜       |
| 4    | 文件匯入              | `POST /documents` 上傳 + 切塊 + embedding                 | ⬜       |
| 5    | 檢索 / RAG            | 檢索相近片段、組 Prompt + 對話歷史                        | ⬜       |
| 6    | 限流                  | Redis 每 IP 每分鐘上限                                    | ⬜       |
| 7    | 監控                  | `/metrics`(請求數、延遲、token 用量)                      | ⬜       |

**迭代 1、2** 只需要 Claude;**迭代 3 起** 才需要 postgres / redis 容器。

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

## 迭代 1(Iteration 1):Walking Skeleton

### 目標

容器跑起來,`curl POST /chat` 得到 Claude 的一句回答。整條管線(容器 → API key → 路由 → Claude)一次打通。

### 驗收標準(Definition of Done)

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "用一句話解釋什麼是 RAG"}'
# → {"answer": "..."}   # 非串流,單一 JSON 回應
```

### 待實作清單

> 以下是這次迭代**要動的程式碼**(目前尚未完成)。完成後上面的驗收標準才會成立。

- [ ] `pyproject.toml`:加 `anthropic` 依賴
- [ ] `config.py`:加 `anthropic_api_key`;把 `database_url` / `redis_url` 改為**選填**(本迭代不接 DB)
- [ ] 新增 `POST /chat` 路由:非串流,直接呼叫 Claude 回傳 `{"answer": ...}`
- [ ] `.env.example`:加 `ANTHROPIC_API_KEY`
- [ ] 啟動只需 `ANTHROPIC_API_KEY`,**不需** postgres / redis

---

## 快速啟動(迭代 1)

> ⚠️ 此啟動方式依賴上方「待實作清單」落地後才成立。目前程式碼僅有 `GET /` 與 `GET /health`。

```bash
# 1. 設定環境變數
cp .env.example .env
#    填入 ANTHROPIC_API_KEY

# 2. 啟動 API(本迭代不需 postgres / redis)
docker compose up --build

# 3. 提問,拿到一句回答
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"question": "用一句話解釋什麼是 RAG"}'

# 4. 互動式 API 文件
open http://localhost:8000/docs
```

---

## 資料夾說明

### 現在實際有的

| 路徑                  | 職責                                          |
| --------------------- | --------------------------------------------- |
| `src/fastapi_app_01/main.py`   | FastAPI 進入點;目前有 `GET /`、`GET /health` |
| `src/fastapi_app_01/config.py` | 用 pydantic-settings 集中讀取環境變數         |
| `scripts/init_db.sql` | 啟用 pgvector(建表 schema 仍為註解,待迭代 3)|

### 後續迭代才加入(尚未存在)

| 路徑                     | 職責                                          | 迭代 |
| ------------------------ | --------------------------------------------- | ---- |
| `app/api/chat.py`        | 問答端點(迭代 1 非串流 → 迭代 2 SSE 串流)      | 1、2 |
| `app/core/llm.py`        | 封裝 Anthropic 生成                           | 1    |
| `app/schemas/chat.py`    | 請求 / 回應的 Pydantic 模型                   | 1    |
| `app/db/database.py`     | PostgreSQL 連線池 / Redis client              | 3    |
| `app/db/repository.py`   | 所有 SQL 集中於此                             | 3    |
| `app/api/documents.py`   | 文件上傳 / 匯入端點                           | 4    |
| `app/core/embeddings.py` | 文字轉向量(預設 OpenAI)                       | 4    |
| `app/core/rag.py`        | **核心**:切塊 + 檢索 + Prompt 組裝(多處 TODO) | 5    |
| `app/core/rate_limit.py` | Redis 限流                                    | 6    |
| `app/api/health.py`      | 健康檢查(目前 inline 在 main.py)             | —    |

---

## 本機開發(混合模式,推薦)

日常開發採「**基礎服務容器化、API 本機跑**」:Postgres / Redis 用 compose 起(**迭代 3 起才需要**),
FastAPI 用 PyCharm 綠色三角(或 `uv run`)在本機跑並連 `localhost`。好處是
debugger 零設定即可中斷、`--reload` 即時、改 code 免 rebuild image。

```bash
# 1. 準備環境變數(.env 已 gitignore)
cp .env.example .env

# 2. (迭代 3 起)只啟動相依服務
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

**偶爾做全容器 / parity 驗證**(需先補上 multi-stage uv `Dockerfile`):

```bash
docker compose --profile full up      # 含 api
docker compose --profile full watch   # 改 code 自動同步進容器
```

---

## 跑測試

> 目前尚無測試;測試會隨各迭代補上(見待辦)。

```bash
uv run pytest
```

---

## 待辦事項(對齊迭代藍圖)

把骨架變成「能拿去面試」的關鍵,就是把每個迭代做扎實。下面 TODO 標出所屬迭代:

- **迭代 1(Walking Skeleton)**:加 `anthropic` 依賴、`POST /chat` 非串流接 Claude、`ANTHROPIC_API_KEY` 設定。
- **迭代 2(串流)**:`/chat` 改 SSE 逐字回傳。
- **迭代 3(持久化)**:接 Postgres + pgvector,uncomment `init_db.sql` 的 schema 並客製。
- **迭代 4(文件)**:`POST /documents` 上傳 + **切塊策略**(從固定字數改成依語意 / 句子邊界,並說明取捨)+ embedding;支援 PDF / Word 解析。
- **迭代 5(RAG)**:**檢索品質**(距離門檻過濾、調 `top_k`、進階 re-rank)、**引用來源**(標出答案來自哪個片段)。
- **迭代 6(限流)**:Redis 固定視窗 →(進階)滑動視窗或 token bucket。
- **迭代 7(監控)**:`/metrics`(請求數、延遲、token 用量)。
- **貫穿各迭代**:補 API 層測試,把 LLM / Embedding / DB mock 掉。

> 小提醒:作業好不好,常不在「做了多少功能」,而在你能不能清楚講出**每個設計選擇的理由與取捨**。把你做的決定寫進這份 README,會比多寫一個功能更有說服力。
