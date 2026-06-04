# 待辦清單 — 迭代 3(Iteration 3):OpenAI 相容 `/v1`

> **用途**:給 Claude Code(或其他開發工具)照著**逐項打勾**的執行清單。
> plan 講「為什麼 / 怎麼做」,本清單講「做了沒 / 怎麼確認」。
>
> **來源**:`plans/iteration-3-openai-compat.md`(步驟、決策、DoD)、`specs/api.yml`(端點契約)、
> `specs/tech-stack.md`(技術棧與測試模式)。任務代號 **T0–T9** 對應 plan 的 Step 0–9。
>
> **本質**:**新增**對外相容層——OpenAI 相容 `POST /v1/chat/completions`(串流 + 非串流)與 `GET /v1/models`,
> 把既有 Claude 串流重塑成 OpenAI 格式,讓 Open WebUI 直接可用。**不改核心能力、不替換 `/chat`**。
>
> **開發順序(輕量 spec-first,沿用迭代 2)**:先改**契約**(`api.yml`,T1)→ 依約實作(T2–T4)→ 測試斷言契約(T5)
> → host 驗收 + `/openapi.json` 比對(T6)→ 容器發布(T7)→ Open WebUI 整合(T8)→ 最後補**敘述**文件(T9)。
>
> **原則**:不擴張範圍、不與決策(D1–D8)衝突。硬性收工含「自動測試綠燈 + `curl` live(串流+非串流)+ 容器發布 + Open WebUI 可對話」。

---

## 已定案決策(實作時遵守,並記於 commit message)

- [ ] **D1** 新增 `POST /v1/chat/completions` + `GET /v1/models`(後者供 Open WebUI 填模型下拉)。
- [ ] **D2** 依 `stream` 旗標分流:`true` → SSE `chat.completion.chunk` + `[DONE]`;`false` → 單一 `chat.completion` JSON(**兩條都做**)。
- [ ] **D3** **新增、不替換**:`/chat`(迭代 2)原樣保留。
- [ ] **D4** `/v1/models` 回 `id == settings.anthropic_model`;`/v1/chat/completions` 忽略請求 `model`,一律用 `settings.anthropic_model`。
- [ ] **D5** `system` role 抽成 Anthropic 頂層 `system`;其餘 `user`/`assistant` 原順序映成 `messages`;只處理 `content` 為**字串**。
- [ ] **D6** 接受並**忽略** `Authorization`(本機不驗證)。
- [ ] **D7** `id="chatcmpl-"+uuid4().hex`、`created=int(time.time())`;`stop_reason→finish_reason`(`end_turn`/`stop_sequence`→`stop`、`max_tokens`→`length`);非串流附 `usage`,串流不附。
- [ ] **D8** compose 加 `openwebui` 服務(profile `webui`,opt-in),`OPENWEBUI_API_BASE` 預設 `host.docker.internal`。
- [ ] ⚠️ 非串流會讓 Open WebUI 背景呼叫(標題/標籤)**真打 Claude**(計費);測試想省可在 UI Admin 關閉。

---

## 前置條件

- [ ] 已讀 `plans/iteration-3-openai-compat.md`、`specs/api.yml`、`specs/tech-stack.md`。
- [ ] 確認在功能分支上(非 `main`;見 T0)。
- [ ] `.env` 已存在且含 `ANTHROPIC_API_KEY`(沿用前迭代;`curl` / Open WebUI live 驗收需真 key)。
- [ ] 確認現況基準(迭代 2 已交付):
      `core/llm.py` 有 `stream_answer(question)`(單輪);`api/chat.py` 為自訂 SSE `/chat`;
      `schemas/chat.py` 只有 `ChatRequest`;`main.py` 只 include chat router;尚無 `/v1`。
- [ ] **無需新增依賴**:`StreamingResponse` 內建,`json` / `time` / `uuid` / `dataclasses` 為 stdlib。

---

## 任務待辦(T0–T9)

### T0 — 開分支(plan Step 0)

- **動到**:git 分支。
- [ ] `git switch -c feat/iteration-3-openai-compat`。
- **Acceptance**:`git branch --show-current` 顯示新分支,非 `main`。

### T1 — spec-first:先更新 `specs/api.yml` 契約(plan Step 1)

- **動到**:`specs/api.yml`(**只動契約**;敘述文件留 T9)。
- [ ] 新增 `POST /v1/chat/completions`:requestBody `$ref: ChatCompletionRequest`;`200` 兩種——`text/event-stream`(`stream=true`,`chat.completion.chunk` 事件流 + `[DONE]`)與 `application/json`(`stream=false`,`$ref: ChatCompletion`);`422`(messages 空)。
- [ ] 新增 `GET /v1/models`:`200` `application/json`,`{object:"list", data:[Model]}`。
- [ ] 新增 schemas:`ChatMessage`(`role`、`content`)、`ChatCompletionRequest`(`model?`、`messages`(minItems 1)、`stream`(預設 false)、`max_tokens?`;註明**容忍其他 OpenAI 欄位**)、`ChatCompletion` / `Model`(描述層級即可)。
- [ ] `info.description`:當前迭代更新到迭代 3;後續迭代清單移除「OpenAI 相容 `/v1`」。
- **Acceptance**:`specs/api.yml` 仍為合法 YAML;T2–T5 以此契約為準。
- **注意**:OpenAI 對 SSE 描述力有限,`chat.completion.chunk` 以**文字描述**即可;真正線上契約由 D7 / 測試把關。

### T2 — `schemas/openai.py`:OpenAI 請求模型(plan Step 2)

- **動到**:新增 `src/fastapi_app_01/schemas/openai.py`。
- [ ] `ChatMessage`:`role: str`、`content: str`。
- [ ] `ChatCompletionRequest`:`model_config = ConfigDict(extra="ignore")`(容忍未知欄位);
      `model: str | None = None`、`messages: list[ChatMessage] = Field(min_length=1)`、`stream: bool = False`、`max_tokens: int | None = None`。
- **Acceptance**:多帶 `temperature` 等欄位建構不報錯;`messages=[]` 觸發驗證錯誤。
- **注意**:回應(`chat.completion(.chunk)`)用 dict 直接組,不另立輸出模型。

### T3 — `core/llm.py`:加 `stream_chat` / `complete_chat`(多輪 + system)(plan Step 3)

- **動到**:`src/fastapi_app_01/core/llm.py`。
- [ ] **保留** `stream_answer`(迭代 2,給 `/chat` 用),不動。
- [ ] 加 `@dataclass ChatResult`(`text`、`stop_reason`、`input_tokens`、`output_tokens`)。
- [ ] 加 `_kwargs(messages, system)`:組 `model` / `max_tokens` / `messages`,`system` 有值才加入。
- [ ] `async def stream_chat(messages, system=None) -> AsyncIterator[str]`:`messages.stream(**_kwargs)`,`async for text in stream.text_stream: yield text`。
- [ ] `async def complete_chat(messages, system=None) -> ChatResult`:`messages.create(**_kwargs)`,回 `text=content[0].text`、`stop_reason`、`usage.input_tokens` / `output_tokens`。
- **Acceptance**:模組可 import;`stream_chat` 為 async generator;`complete_chat` 回 `ChatResult`。
- **注意**:`core/llm` 只收**已轉好**的 anthropic messages + system,保持與 OpenAI / 傳輸無關(轉接在 T4)。

### T4 — `api/openai_compat.py`:轉接層 + 端點 + `main.py` 註冊(plan Step 4)

- **動到**:新增 `src/fastapi_app_01/api/openai_compat.py`;改 `src/fastapi_app_01/main.py`。
- [ ] `router = APIRouter(prefix="/v1")`;`_FINISH = {"end_turn":"stop","stop_sequence":"stop","max_tokens":"length"}`。
- [ ] `_split(messages)`:`system` role 併成字串(無則 None)、其餘原順序映成 `[{"role","content"}]`。
- [ ] `GET /models`:回 `{object:"list", data:[{id: settings.anthropic_model, object:"model", created:0, owned_by:"anthropic"}]}`。
- [ ] `POST /chat/completions`:`_split` → `cid/created/model`;
      `stream=true` → `StreamingResponse(gen(), media_type="text/event-stream")`,gen 先送 `delta:{role:"assistant"}` 首塊、逐段送 `delta:{content:text}`(`ensure_ascii=False`)、末塊 `finish_reason:"stop"`、最後 `data: [DONE]`;
      `stream=false` → `await llm.complete_chat`,組 `chat.completion`(`choices[0].message.content`、`finish_reason` 經 `_FINISH` 映射、`usage` 三欄)。
- [ ] `main.py`:`app.include_router(openai_router)`。
- **Acceptance**:`/v1/models` 回模型清單;`/v1/chat/completions` 兩條路徑回應結構與 T1 契約一致;`/chat` 不受影響。
- **注意**:`Authorization` 收到即忽略(D6);請求 `model` 忽略,用 `settings.anthropic_model`(D4)。

### T5 — 測試:斷言 OpenAI 契約(plan Step 5)【硬性 DoD】

- **動到**:`tests/conftest.py`、新增 `tests/test_openai_compat.py`。
- [ ] `conftest.py`:加 fixture monkeypatch `llm.stream_chat`(async generator,**記錄收到的 `(messages, system)`** 供斷言)與 `llm.complete_chat`(回固定 `ChatResult`)。
- [ ] `test_models`:`GET /v1/models` → 200,`object=="list"`,`data[0]["id"] == settings.anthropic_model`。
- [ ] `test_completions_stream`:`stream=true` → `text/event-stream`;各 chunk `object=="chat.completion.chunk"`;`delta.content` 串接 == 完整答案;末 chunk `finish_reason=="stop"`;結尾 `data: [DONE]`。
- [ ] `test_completions_nonstream`:`stream=false` → 200,`object=="chat.completion"`,`choices[0].message.content` == 完整答案,`finish_reason` 有值,`usage` 三欄齊。
- [ ] `test_system_and_multiturn_mapping`:送含 `system` + 多輪 `user`/`assistant`,斷言傳給 `llm.stream_chat` 的 `system` 已抽出、`convo` 不含 system 且順序保留。
- [ ] `test_tolerates_unknown_fields`:請求多帶 `temperature` / `stream_options`,不報 422。
- [ ] `test_empty_messages_422`:`messages:[]` → 422。
- **Acceptance**:`uv run pytest` 全綠;全程 mock,不打真 Claude。
- **注意**:逐 token 增量遞送 in-process 測不準(`TestClient` 緩衝),靠 T6 `curl -N` 肉眼確認。

### T6 — host 手動驗收 + 契約比對(plan Step 6)【硬性 DoD,需真 key,會計費】

- **動到**:無(執行驗證)。
- [ ] `uv run uvicorn fastapi_app_01.main:app --host 0.0.0.0 --reload` 起得來。
- [ ] `curl -s http://localhost:8000/v1/models` → `object=list`,含模型 id。
- [ ] `curl -N` `/v1/chat/completions`(`stream:true`)→ 逐段 `chat.completion.chunk`,末 `finish_reason:"stop"` + `data: [DONE]`。
- [ ] `curl -s` `/v1/chat/completions`(`stream:false`)→ 單一 `chat.completion`,含 `usage`。
- [ ] **契約比對**:開 `http://localhost:8000/openapi.json`(或 `/docs`),確認 `/v1/chat/completions`、`/v1/models` 與 T1 的 `api.yml` 一致;`/chat`(迭代 2)仍在、未被破壞。
- **Acceptance**:三類請求皆符合預期;openapi 與 `api.yml` 對得起來。
- **注意**:會**真實呼叫 Anthropic(計費)**,各做一次最小呼叫即可。

### T7 — 容器發布驗證(plan Step 7)【硬性 DoD,需真 key,會計費】

- **動到**:無(執行驗證)。
- [ ] `docker compose --profile full up --build -d api`(compose B:只起 api)。
- [ ] 對容器版 `curl -N` `/v1/chat/completions`(`stream:true`)→ 同樣串流得出。
- [ ] 收工:`docker compose --profile full down`。
- **Acceptance**:可發布映像在容器內也回得出 `/v1` 串流。
- **注意**:會**真實呼叫 Anthropic(計費)**。

### T8 — Open WebUI 整合(plan Step 8)【本迭代展示成果,會計費】

- **動到**:`docker-compose.yml`(新增 `openwebui` 服務 + `openwebui-data` volume)。
- [ ] 加 `openwebui` 服務:`profiles: ["webui"]`、`image: ghcr.io/open-webui/open-webui:main`、`ports: ["3000:8080"]`、
      `environment` 含 `OPENAI_API_BASE_URL: ${OPENWEBUI_API_BASE:-http://host.docker.internal:8000/v1}` 與 `OPENAI_API_KEY: dummy`、
      `extra_hosts: ["host.docker.internal:host-gateway"]`、`volumes: ["openwebui-data:/app/backend/data"]`;**不放 `depends_on`**。
- [ ] 檔尾 `volumes:` 區塊加 `openwebui-data:`。
- [ ] **混合跑法**:host 起 API(`--host 0.0.0.0`)→ `docker compose --profile webui up -d openwebui` → 開 `localhost:3000`。
- [ ] **全容器跑法**:`OPENWEBUI_API_BASE=http://api:8000/v1 docker compose --profile full --profile webui up`。
- [ ] **手動驗證**:UI 模型下拉**列得出**模型;對話**逐字串流**;接續再問,**多輪**前文有被帶上。
- **Acceptance**:Open WebUI 能列模型並逐字串流多輪對話。
- **注意**:API 須綁 `0.0.0.0`;容器內 UI 連 host 用 `host.docker.internal`(Linux 靠 `extra_hosts`)。背景呼叫計費,可在 UI Admin 關標題生成。

### T9 — 敘述文件對齊(plan Step 9)

- **動到**:`README.md`、`specs/tech-stack.md`。
- [ ] `README.md`:迭代藍圖第 3 列 🚧→✅;banner / 「下一個迭代」改指向迭代 4(對話記憶);
      把既有「Open WebUI 串接(迭代 3,規劃中 🚧)」段**去掉「規劃中」**、改為已可用,確認兩種跑法指令正確。
- [ ] `specs/tech-stack.md`:維持「迭代 1 技術棧」定位,頂部定位說明補一句「迭代 3 已加 OpenAI 相容 `/v1`,見 `plans/iteration-3-openai-compat.md`」。
- **Acceptance**:README 第 3 列為 ✅、Open WebUI 段不再標規劃中。
- **注意**:敘述文件與程式**同批** commit / 合併。

---

## 驗收測試(自動;對應 Layer 1 —— **本迭代屬硬性 DoD**)

> mock `llm.stream_chat` / `complete_chat`。沿用 `conftest.py` 模式(import app 前設假 key、`llm` 接縫 monkeypatch、`TestClient`)。對應 T1 的 `api.yml` 契約。

- [ ] `GET /v1/models`(AC 1)。
- [ ] 串流 `chat.completion.chunk` 串接 + `finish_reason` + `[DONE]`(AC 2)。
- [ ] 非串流 `chat.completion` + `usage`(AC 3)。
- [ ] system 抽取 + 多輪順序(AC 4)。
- [ ] 容忍未知欄位(AC 5)、空 messages 422(AC 6)。
- [ ] `/chat`(迭代 2)未被破壞(AC 7)。

---

## 整合測試(Layer 4 容器冒煙 + Layer 5 live + Layer 6 Open WebUI)

- [ ] (Layer 4)`docker compose --profile full up` 起得來(AC 9 形狀)。
- [ ] (Layer 5)host / 容器 `curl /v1`:串流 + 非串流皆得出(AC 2/3/9,真 Claude,計費)。
- [ ] (Layer 6)Open WebUI 指向 `/v1`:列模型 + 逐字串流 + 多輪(AC 10,計費)。

---

## Definition of Done(對映 plan 的 9 條)

- [ ] **模型列得出**:`GET /v1/models` 回 OpenAI 格式清單。【T5 / T6】
- [ ] **串流相容**:`stream=true` 回 `chat.completion.chunk` + `[DONE]`,逐字浮現。【T5 / T6】
- [ ] **非串流相容**:`stream=false` 回單一 `chat.completion`,含 `finish_reason` 與 `usage`。【T5 / T6】
- [ ] **多輪 + system 正確轉接**:歷史由前端帶入即支援多輪;`system` 走 Anthropic `system` 參數。【T5】
- [ ] **健壯解析**:容忍未知欄位;空 `messages` 回 422。【T5】
- [ ] **不破壞既有**:`/chat`、`/health` 不變;`uv run pytest` 全綠。【T5 / T6】
- [ ] **可發布**:容器版同樣回得出 `/v1` 串流。【T7】
- [ ] **Open WebUI 可用**:指向 `/v1` 後能列模型並逐字串流對話。【T8】
- [ ] **契約與文件對齊**:`specs/api.yml` 含 `/v1` 且與 `/openapi.json` 一致;README 第 3 列為 ✅。【T1 / T6 / T9】

---

## 注意事項彙總(避免踩坑)

- **轉接層是新增複雜度**:`system` 抽取、`finish_reason` / `usage` 映射、chunk 組裝集中在 `openai_compat.py`;`core/llm` 保持中立。
- **OpenAI 只做夠用子集**:不支援多模態 content parts、tools、`logprobs`、`n>1`;`content` 假設字串(列為 Out)。
- **多輪歷史來源**:本迭代全由前端帶(Open WebUI 每次送完整 `messages`),無伺服器端狀態;迭代 4 才加持久化。
- **串流不附 usage**:省略 `stream_options.include_usage`;非串流才給 usage。
- **Open WebUI 網路**:容器內 UI 連 host API 用 `host.docker.internal`(mac/win 原生;Linux 靠 `extra_hosts`)。
- **非串流計費**:Open WebUI 背景呼叫(標題/標籤)會打真 Claude → 測試想省可在 UI Admin 關閉。
- **spec-first**:先改 `api.yml`(T1)再實作;T6 比對 `/openapi.json` 與 `api.yml` 不漂移;README/tech-stack 屬敘述,留 T9。
- **不破壞 `/chat`**:本迭代新增、不替換;測試保留 `/chat` 的既有斷言。
- **錯誤處理刻意最小**:串流中途 / client 斷線 / 上游錯誤不特別處理;健全處理排迭代 6。
- **不加新依賴**:全 stdlib + 內建 `StreamingResponse`;不引入 `openai` SDK、不引入 `sse-starlette`。

---

## 完成後 → 下一個迭代

迭代 4(對話記憶):接 Postgres 存對話歷史、支援**伺服器端**多輪。屆時 `/v1` 的「前端帶歷史」與
新的「伺服器端持久化」並存,需定義以哪個為準;`core/llm` 的 messages 由 DB 取出的歷史組裝。骨架與串流機制不變。
