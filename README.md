# RAG Service (作業練習骨架)

一個最小可行的「知識庫問答」後端服務:上傳文件 → 切塊 → 存進向量資料庫 → 檢索 → 用 LLM 串流回答。

技術組合對應 JD 的基本條件:**FastAPI(REST + SSE 串流)、PostgreSQL + pgvector、Redis 限流、Anthropic Claude、Docker Compose**。

> ⚠️ 這是「練習骨架」,不是現成可交的作品。基礎建設已接好讓它能跑,但標 `TODO` 的核心邏輯(切塊策略、Prompt 組裝、檢索調校)請你自己動手,那才是面試官會問、也是展現能力的地方。

---

## 架構

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

## 資料夾說明

| 路徑                     | 職責                                          |
| ------------------------ | --------------------------------------------- |
| `app/main.py`            | FastAPI 進入點,管理連線池生命週期、註冊路由   |
| `app/config.py`          | 用 pydantic-settings 集中讀取環境變數         |
| `app/api/chat.py`        | 問答端點(SSE 串流)                            |
| `app/api/documents.py`   | 文件上傳 / 匯入端點                           |
| `app/api/health.py`      | 健康檢查                                      |
| `app/core/llm.py`        | 封裝 Anthropic 串流生成                       |
| `app/core/embeddings.py` | 文字轉向量(預設 OpenAI)                       |
| `app/core/rag.py`        | **核心**:切塊 + 檢索 + Prompt 組裝(多處 TODO) |
| `app/core/rate_limit.py` | Redis 限流                                    |
| `app/db/database.py`     | PostgreSQL 連線池 / Redis client              |
| `app/db/repository.py`   | 所有 SQL 集中於此                             |
| `app/schemas/chat.py`    | 請求 / 回應的 Pydantic 模型                   |
| `scripts/init_db.sql`    | 啟用 pgvector、建表、建索引                   |

## 快速啟動

```bash
# 1. 設定環境變數
cp .env.example .env
#    填入 ANTHROPIC_API_KEY 與 OPENAI_API_KEY

# 2. 一鍵啟動 (API + PostgreSQL + Redis)
docker compose up --build

# 3. 確認服務正常
curl http://localhost:8000/health

# 4. 互動式 API 文件
open http://localhost:8000/docs
```

## 本機開發(混合模式,推薦)

日常開發採「**基礎服務容器化、API 本機跑**」:Postgres / Redis 用 compose 起,
FastAPI 用 PyCharm 綠色三角(或 `uv run`)在本機跑並連 `localhost`。好處是
debugger 零設定即可中斷、`--reload` 即時、改 code 免 rebuild image。

```bash
# 1. 準備環境變數(.env 已 gitignore)
cp .env.example .env

# 2. 只啟動相依服務(api 服務被 "full" profile 閘控,不會起)
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

## 使用範例

```bash
# 上傳一份文字檔進知識庫
curl -X POST http://localhost:8000/documents \
  -F "file=@your_notes.txt"

# 提問 (SSE 串流, -N 關閉緩衝才能逐字看到)
curl -N -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "demo-1", "question": "這份文件在講什麼?"}'
```

## 跑測試

```bash
pip install -r requirements.txt
pytest
```

## 練習的待辦事項(依重要性)

這些就是把骨架變成「能拿去面試」的關鍵,`rag.py` 內有對應的 `TODO` 註解:

1. **切塊策略**:目前是固定字數切,改成依語意 / 句子邊界,並說明取捨。
2. **檢索品質**:加距離門檻過濾、調 `top_k`、(進階)做 re-rank。
3. **引用來源**:回答時標出答案來自哪個片段,提升可信度。
4. **文件格式**:支援 PDF / Word 解析,不只純文字。
5. **測試**:補 API 層測試,把 LLM/Embedding/DB mock 掉。
6. **(進階)限流**:固定視窗改滑動視窗或 token bucket。
7. **(進階)監控**:加上 `/metrics`(請求數、延遲、token 用量)。

> 小提醒:作業好不好,常不在「做了多少功能」,而在你能不能清楚講出**每個設計選擇的理由與取捨**。把你做的決定寫進這份 README,會比多寫一個功能更有說服力。
