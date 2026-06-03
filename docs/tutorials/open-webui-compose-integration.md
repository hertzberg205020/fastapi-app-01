# 在 docker-compose 加入 Open WebUI(混合模式)

## Context

目前專案是 RAG 服務骨架:`docker compose up` 只起 `postgres`(pgvector) + `redis`,
API 依「混合模式」跑在 host 上(`uv run uvicorn fastapi_app_01.main:app --reload`),
透過 localhost 發布的埠連回 postgres/redis。`api` 服務藏在 `full` profile 後面,
且尚未有 Dockerfile。

目標:加入 Open WebUI 作為測試/操作介面,串接本機開發中的 API。已選定
**混合模式**——Open WebUI 跑在容器,API 仍跑在 host。

本文件聚焦兩個重點:**依賴關係**與**網路配置**。

---

## 一、網路配置(核心)

### 現況拓樸
- Compose 建立單一預設 bridge 網路;`postgres`/`redis` 在網路內、可用服務名互相解析。
- 兩者的埠都只發布到 `127.0.0.1`(5432 / 6379),不對區網開放。
- **API 不在這個網路裡**——它跑在 host,經 localhost 連 postgres/redis。

### 混合模式下 Open WebUI → host 的路徑
Open WebUI 在容器內,API 在 host,容器要連回 host 必須用 `host.docker.internal`:

```yaml
open-webui:
  image: ghcr.io/open-webui/open-webui:main
  profiles: ["ui"]                 # 跟 api 一樣藏在 profile 後,預設 up 仍維持精簡
  ports:
    - "127.0.0.1:3000:8080"        # 對外 3000,容器內固定 8080;比照本專案只綁 localhost
  environment:
    - OPENAI_API_BASE_URL=http://host.docker.internal:8000/v1
    - OPENAI_API_KEY=dummy-local   # 本機 API 不驗 key,給佔位字串即可
    - ENABLE_OLLAMA_API=false      # 不裝 Ollama,關掉以免一直嘗試連線
    - WEBUI_AUTH=false             # 測試介面免登入(正式環境勿用)
  extra_hosts:
    - "host.docker.internal:host-gateway"   # macOS 可省,但加上可跨 Linux 攜帶
  volumes:
    - open-webui:/app/backend/data
  restart: unless-stopped
```

並在 `volumes:` 區塊新增:
```yaml
  open-webui:
```

啟動:`docker compose --profile ui up -d open-webui`

### ⚠️ 兩個必處理的網路陷阱

1. **API 必須綁 0.0.0.0,不能綁 127.0.0.1。**
   `src/fastapi_app_01/__init__.py` 的 `main()` 與 README 的 `uv run uvicorn ... --reload`
   都會綁 `127.0.0.1`。綁在 loopback 的 host 程序,`host.docker.internal`(走 host-gateway,
   命中的是 docker 橋接介面而非 loopback)**連不到**。
   → host 端啟動 API 時改用 `--host 0.0.0.0`,例如
   `uv run uvicorn fastapi_app_01.main:app --host 0.0.0.0 --reload`。

2. **CORS / 來源。** Open WebUI 是 server 端轉發呼叫(不是瀏覽器直連),
   一般不需在 API 加 CORS。若日後改成瀏覽器側呼叫才需要。目前 `main.py` 無 CORS middleware,維持即可。

---

## 二、依賴關係

| 關係 | 說明 |
|------|------|
| Open WebUI → postgres/redis | **無依賴**。Open WebUI 有自己的資料儲存,預設用容器內 SQLite(存在 `open-webui` volume),不碰你的 ragdb / redis。 |
| Open WebUI → 你的 API | 這是**執行期依賴**,但因 API 在 host(非 compose 服務),**無法用 `depends_on` 表達**。Open WebUI 啟動時 API 沒起也不會壞,只是抓不到模型清單。 |
| Open WebUI → Ollama | 預設會嘗試連 Ollama;用 `ENABLE_OLLAMA_API=false` 關掉。 |

> 因此混合模式下 **不需要也無法加 `depends_on`**;依賴是靠 `OPENAI_API_BASE_URL` 指向 host 的 API,屬於設定層而非 compose 編排層。

---

## 三、前置條件(務必知道)

Open WebUI 透過 **OpenAI 相容協定** 串接,至少需要:
- `GET /v1/models` —— 列出可選模型(否則 UI 連上了卻沒有模型可選)
- `POST /v1/chat/completions` —— 對話(支援 `stream=true` 才有逐字輸出)

目前 `main.py` 只有 `/` 與 `/health`,**尚未實作這兩個端點**。
本文件只負責「把 Open WebUI 接進 compose + 網路打通」;實際對話要能跑,
需另行實作上述 OpenAI 相容端點(可後續再做)。先接 UI、確認 `/v1/models`
能被 Open WebUI 讀到,即可驗證網路鏈路。

---

## 要修改的檔案

- `docker-compose.yml` —— 新增 `open-webui` 服務(`ui` profile)與 `open-webui` named volume。
- `.env.example` / `README.md` —— 補充:啟動 UI 的指令、API 須以 `--host 0.0.0.0` 啟動的提醒。
  (`.env` 不需新增變數;OPENAI_API_BASE_URL/KEY 直接寫在 compose 即可,或視需要外移。)
- (非本文件範圍,但為了真正能對話)`src/fastapi_app_01/` 新增 OpenAI 相容端點。

---

## 驗證(end-to-end)

1. host 啟動基礎設施與 API(注意 `--host 0.0.0.0`):
   ```bash
   docker compose up -d postgres redis
   uv run uvicorn fastapi_app_01.main:app --host 0.0.0.0 --reload
   ```
2. 啟動 Open WebUI:`docker compose --profile ui up -d open-webui`
3. **驗證容器→host 鏈路**(不依賴 UI):
   ```bash
   docker compose exec open-webui curl -s http://host.docker.internal:8000/health
   ```
   能拿到 `/health` 回應 → 網路打通。
4. 瀏覽器開 `http://localhost:3000`,在 Settings → Connections 確認 OpenAI 連線指向
   `http://host.docker.internal:8000/v1`。
5. 待 `/v1/models`、`/v1/chat/completions` 實作後,模型清單應出現、可進行對話。
