# 迭代 3(Iteration 3):OpenAI 相容 `/v1`

> 對應 README「迭代藍圖」第 3 列。這份文件是**可照著做的執行計畫**:規劃、決策點、有序步驟(含示範程式碼)、驗收標準。
> 文中所有程式碼皆標「**預計 / 待實作**」——目前只有自訂 SSE 的 `POST /chat`(迭代 2),尚無 `/v1`。

## Context

迭代 2 已把 `POST /chat` 做成自訂 SSE(`data: {"text": "..."}` + `[DONE]`),`llm.stream_answer(question)` 單輪、無 system、無歷史。
迭代 3 的目標是**讓服務能被現成前端(Open WebUI)直接使用**:

> **新增 OpenAI 相容的 `POST /v1/chat/completions`(串流 + 非串流)與 `GET /v1/models`,把 Claude 串流重塑成 OpenAI 線上格式。**

這是與「串流」正交的**對外相容層**:不新增核心能力,而是把既有串流包成業界標準介面。價值在於**可用真實圖形 UI 對話**(高展示回饋)。
多輪歷史**由前端帶在 `messages` 陣列**送入,故本迭代**仍不需伺服器端持久化**(那留待迭代 4)。

> **Open WebUI 整合前置**(其餘早已滿足,缺的就是 `/v1`):API 須綁 `0.0.0.0`(compose `command` 已是 `--host 0.0.0.0`)、
> compose 無多餘 `depends_on`(迭代 1 的 compose B 已拿掉)。本迭代補上 `/v1` 端點後即可串接。

---

## 範圍界定

| | 內容 |
| ----------- | -------------------------------------------------------------- |
| ✅ **In**  | `POST /v1/chat/completions`(`stream` 真/假兩條路徑)、`GET /v1/models`;OpenAI↔Anthropic 訊息/格式轉接;多輪歷史由前端帶入;Open WebUI 串接驗證;測試與文件對齊 |
| ❌ **Out** | 伺服器端對話記憶 / Postgres(迭代 4)、RAG / pgvector(迭代 5)、限流 / `/metrics` / 健全錯誤處理(迭代 6)、加分項(迭代 7);**多模態 content parts、tools/function-calling、`logprobs`、API key 驗證**(本迭代僅接受並忽略 `Authorization`) |

**刻意不做**:不驗證 API key(本機可用即可)、不支援 content 為陣列的多模態訊息(只處理純文字 `content`)、不做 tool use;`/chat`(迭代 2)**原樣保留**,本迭代是**新增**而非替換。

---

## 架構(本迭代)

```ascii
  Open WebUI ──GET /v1/models──────────▶ 列出可用模型(下拉選單)
       │
       └──POST /v1/chat/completions────▶ ┌────────────────┐
          {model, messages[], stream}    │ openai_compat   │  _split: system role → system 參數
                                          │  (轉接層)        │          其餘 → anthropic messages
                                          └───────┬────────┘
                                                  ▼ llm.stream_chat / complete_chat
                                          ┌────────────────┐ ──messages.stream──▶ ┌────────┐
                                          │   core/llm      │ ◀──text delta─────── │ Claude │
                                          └───────┬────────┘                       └────────┘
                                                  ▼ 重塑為 OpenAI 格式
        stream=true  → text/event-stream: data: {"object":"chat.completion.chunk","choices":[{"delta":{"content":"…"}}]} … data: [DONE]
        stream=false → application/json:   {"object":"chat.completion","choices":[{"message":{"content":"…"},"finish_reason":"stop"}],"usage":{…}}
```

骨架與串流機制不變;新增的是 `/v1` 路由 + 一層**雙向格式轉接**(OpenAI 請求 → Anthropic 呼叫 → OpenAI 回應)。

---

## 與現況的差異(一眼看懂)

| 層 | 現況(迭代 2) | 迭代 3(本迭代,新增) |
| ------------- | ----------------------------------- | ------------------------------------------- |
| `core/llm.py` | `stream_answer(question)`(單輪) | **新增** `stream_chat(messages, system)`、`complete_chat(...) -> ChatResult`(多輪 + system) |
| `api/` | `chat.py`(`/chat`) | **新增** `openai_compat.py`(`/v1/chat/completions`、`/v1/models`);`/chat` 不動 |
| `schemas/` | `chat.py`(`ChatRequest`) | **新增** `openai.py`(`ChatMessage`、`ChatCompletionRequest`,容忍未知欄位) |
| `main.py` | include chat router | **新增** include openai_compat router |
| 回應契約 | 自訂 SSE `{"text":...}` | OpenAI `chat.completion(.chunk)` 格式 + `[DONE]` |
| 依賴 | — | **無新增**(`StreamingResponse` 內建、`json`/`time`/`uuid`/`dataclasses` 為 stdlib) |

---

## 決策點(已定案,實作時遵守並記於 commit message)

### D1 — 端點集合

- **(定案)** 新增 `POST /v1/chat/completions` + `GET /v1/models`。`/v1/models` 是必要的:Open WebUI 靠它填模型下拉選單,缺了就選不到模型。

### D2 — `stream` 真假兩條路徑

- **(定案)** 依請求的 `stream` 旗標分流:`true` → SSE `chat.completion.chunk` + `[DONE]`;`false` → 單一 `chat.completion` JSON。
  Open WebUI 聊天走串流,但標題 / 標籤等輔助功能會發**非串流**呼叫 → 兩者都支援才完整相容(成本低)。
- ⚠️ **計費提醒**:支援非串流後,Open WebUI 的背景呼叫(標題 / 標籤 / 後續建議)會**真的打到 Claude**,
  每次對話多幾次計費 + 延遲。手動測試想省,可在 Open WebUI **Admin → Settings → Interface** 關掉「Title Generation」等。

### D3 — 與 `/chat` 的關係

- **(定案)** **新增、不替換**。`/chat`(迭代 2 自訂 SSE)原樣保留,作為「最薄自有契約」示範;`/v1` 是對外相容層。

### D4 — model 名稱處理

- **(定案)** `/v1/models` 回單一模型,`id == settings.anthropic_model`;`/v1/chat/completions` **忽略**請求的 `model`,一律用 `settings.anthropic_model`(回應的 `model` 欄回填實際使用者)。

### D5 — 訊息 / system 轉接(轉接層核心)

- **(定案)** OpenAI `messages` 內的 `system` role **抽出**併成 Anthropic 頂層 `system` 參數(str);其餘 `user`/`assistant` 原順序映成 Anthropic `messages`。
  只處理 `content` 為**字串**的訊息(多模態 content parts 不在範圍)。轉接(`_split`)屬 OpenAI 適配關注點,放 `api/openai_compat.py`;`core/llm` 只收「已轉好的 messages + system」,保持與傳輸無關。

### D6 — 認證

- **(定案)** 接受並**忽略** `Authorization: Bearer <key>`(本機可用即可);**不**強制驗證。健全認證排後續迭代。

### D7 — 識別欄與用量

- **(定案)** 每次回應產生 `id = "chatcmpl-" + uuid4().hex`、`created = int(time.time())`;`finish_reason` 由 Anthropic `stop_reason` 映射
  (`end_turn`/`stop_sequence` → `"stop"`,`max_tokens` → `"length"`);非串流回應帶 `usage`(由 `messages.create` 的 `usage` 轉 `prompt/completion/total_tokens`),串流回應本迭代**不**附 usage(省略 `stream_options.include_usage`)。

### D8 — Open WebUI 如何串接

- **(定案)** 在 `docker-compose.yml` 加一個 `openwebui` 服務,放**獨立 profile `webui`**(opt-in,不綁預設啟動)。
  `OPENAI_API_BASE_URL` 用環境變數帶預設:`${OPENWEBUI_API_BASE:-http://host.docker.internal:8000/v1}`
  —— **預設指向 host 上的 API**(對應日常混合模式);全容器時用環境變數覆寫成 `http://api:8000/v1`。
  搭配 `extra_hosts: ["host.docker.internal:host-gateway"]`(Linux 也連得到 host)、`openwebui-data` named volume(保留登入/設定)、`OPENAI_API_KEY: dummy`(我們不驗證,見 D6);**不放 `depends_on`**(沿用 compose B 精神,混合模式下 `api` 不在 compose 內)。
- **兩種跑法**(會寫進 README 與 Step 8):
  - **混合(日常)**:host 起 API(`--host 0.0.0.0`)→ `docker compose --profile webui up -d openwebui` → 開 `localhost:3000`。
  - **全容器**:`OPENWEBUI_API_BASE=http://api:8000/v1 docker compose --profile full --profile webui up`。

> 串流中途錯誤 / client 斷線維持最小處理(排迭代 6);不引入 `sse-starlette`(內建 `StreamingResponse` 足夠)。

---

## 執行步驟

> 每步標**動到的檔案**與**預計程式碼**。實作以 `anthropic` 當前 SDK 為準(已用 context7 確認 `system` 參數、多輪 `messages`、`get_final_message()`/`stop_reason`)。
>
> **開發順序(輕量 spec-first,沿用迭代 2)**:先改**契約**(`specs/api.yml`,Step 1)→ 依約實作(Step 2–4)→
> 測試斷言契約(Step 5)→ host 驗收 + `/openapi.json` 比對(Step 6)→ 容器發布(Step 7)→ Open WebUI 整合驗證(Step 8)→
> 最後補**敘述**文件(Step 9)。全程同一 feature 分支整批合併。

### Step 0 — 開分支

```bash
git switch -c feat/iteration-3-openai-compat
```

### Step 1 — spec-first:先更新 `specs/api.yml` 契約

動到 `specs/api.yml`(**只動契約**;敘述文件留 Step 9):
- 新增路徑 `POST /v1/chat/completions`:requestBody `$ref: ChatCompletionRequest`;`200` 兩種——`text/event-stream`(`stream=true`,`chat.completion.chunk` 事件流 + `[DONE]`)與 `application/json`(`stream=false`,`$ref: ChatCompletion`)。`422`(messages 空)沿用標準。
- 新增路徑 `GET /v1/models`:`200` `application/json`,回 `{object: "list", data: [Model]}`。
- 新增 schemas:`ChatMessage`(`role`、`content`)、`ChatCompletionRequest`(`model?`、`messages`(minItems 1)、`stream`(預設 false)、`max_tokens?`;註明**容忍其他 OpenAI 欄位**)、`ChatCompletion` / `Model`(描述層級即可)。
- `info.description`:把「當前迭代」更新到迭代 3;後續迭代清單移除「OpenAI 相容 `/v1`」。

> verify:`api.yml` 仍為合法 YAML;Step 2–5 以此契約為準。

### Step 2 — `schemas/openai.py`:OpenAI 請求模型(連同既有 `schemas/`)

```python
# 預計:src/fastapi_app_01/schemas/openai.py
from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: str            # "system" | "user" | "assistant"
    content: str


class ChatCompletionRequest(BaseModel):
    # 容忍 Open WebUI 多送的欄位(temperature、top_p、stream_options…),不報錯
    model_config = ConfigDict(extra="ignore")

    model: str | None = None
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    max_tokens: int | None = None
```

> 回應(`chat.completion(.chunk)`)用 dict 直接組,不另立輸出模型——欄位多且本迭代不需驗證輸出。

### Step 3 — `core/llm.py`:加 `stream_chat` / `complete_chat`(多輪 + system)

動到 `src/fastapi_app_01/core/llm.py`。`stream_answer`(迭代 2)**保留不動**(給 `/chat` 用);新增多輪版本。
`core/llm` 只收「已轉好的 anthropic messages + system」,保持與傳輸 / OpenAI 無關。

```python
# 預計:src/fastapi_app_01/core/llm.py(新增)
from dataclasses import dataclass


@dataclass
class ChatResult:
    text: str
    stop_reason: str | None
    input_tokens: int
    output_tokens: int


def _kwargs(messages: list[dict], system: str | None) -> dict:
    kw = {"model": settings.anthropic_model, "max_tokens": 1024, "messages": messages}
    if system:
        kw["system"] = system          # 無 system 就不傳該參數
    return kw


async def stream_chat(messages: list[dict], system: str | None = None) -> AsyncIterator[str]:
    """多輪串流:逐段 yield 文字 delta。"""
    async with _client.messages.stream(**_kwargs(messages, system)) as stream:
        async for text in stream.text_stream:
            yield text


async def complete_chat(messages: list[dict], system: str | None = None) -> ChatResult:
    """多輪非串流:回完整文字 + stop_reason + token 用量。"""
    msg = await _client.messages.create(**_kwargs(messages, system))
    return ChatResult(
        text=msg.content[0].text,
        stop_reason=msg.stop_reason,
        input_tokens=msg.usage.input_tokens,
        output_tokens=msg.usage.output_tokens,
    )
```

### Step 4 — `api/openai_compat.py`:轉接層 + 端點 + `main.py` 註冊

新增 `src/fastapi_app_01/api/openai_compat.py`;`main.py` 加 `include_router`。

```python
# 預計:src/fastapi_app_01/api/openai_compat.py
import json
import time
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from fastapi_app_01.config import settings
from fastapi_app_01.core import llm
from fastapi_app_01.schemas.openai import ChatCompletionRequest, ChatMessage

router = APIRouter(prefix="/v1")

# Anthropic stop_reason → OpenAI finish_reason
_FINISH = {"end_turn": "stop", "stop_sequence": "stop", "max_tokens": "length"}


def _split(messages: list[ChatMessage]) -> tuple[str | None, list[dict]]:
    """system role 併成 Anthropic 頂層 system;其餘原順序映成 messages。"""
    system = "\n\n".join(m.content for m in messages if m.role == "system") or None
    convo = [{"role": m.role, "content": m.content} for m in messages if m.role != "system"]
    return system, convo


@router.get("/models")
def list_models() -> dict:
    return {"object": "list", "data": [
        {"id": settings.anthropic_model, "object": "model", "created": 0, "owned_by": "anthropic"},
    ]}


@router.post("/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    system, convo = _split(req.messages)
    cid, created, model = f"chatcmpl-{uuid.uuid4().hex}", int(time.time()), settings.anthropic_model

    if req.stream:
        async def gen() -> AsyncIterator[str]:
            head = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                    "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]}
            yield f"data: {json.dumps(head)}\n\n"
            async for text in llm.stream_chat(convo, system):
                chunk = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                         "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}]}
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            tail = {"id": cid, "object": "chat.completion.chunk", "created": created, "model": model,
                    "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            yield f"data: {json.dumps(tail)}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(gen(), media_type="text/event-stream")

    r = await llm.complete_chat(convo, system)
    return {
        "id": cid, "object": "chat.completion", "created": created, "model": model,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": r.text},
                     "finish_reason": _FINISH.get(r.stop_reason, "stop")}],
        "usage": {"prompt_tokens": r.input_tokens, "completion_tokens": r.output_tokens,
                  "total_tokens": r.input_tokens + r.output_tokens},
    }
```

```python
# 預計:src/fastapi_app_01/main.py(節錄,新增)
from fastapi_app_01.api.openai_compat import router as openai_router
app.include_router(openai_router)
```

### Step 5 — 測試:斷言 OpenAI 契約(對應驗收策略 Layer 1)【硬性 DoD】

動到 `tests/`(新增 `tests/test_openai_compat.py`;`conftest.py` 加 mock 接縫)。沿用既有模式:import app 前設假 key、在 `llm` 接縫 monkeypatch、`TestClient`。

- [ ] `conftest.py`:加 fixture monkeypatch `llm.stream_chat`(async generator,並把收到的 `(messages, system)` 記錄供斷言)與 `llm.complete_chat`(回固定 `ChatResult`)。
- [ ] `test_models`:`GET /v1/models` → 200,`object == "list"`,`data[0]["id"] == settings.anthropic_model`。
- [ ] `test_completions_stream`(`stream=true`):`content-type` 為 `text/event-stream`;各 chunk `object == "chat.completion.chunk"`;`delta.content` 串接 == 完整答案;末 chunk `finish_reason == "stop"`;結尾 `data: [DONE]`。
- [ ] `test_completions_nonstream`(`stream=false`):200 JSON,`object == "chat.completion"`,`choices[0].message.content` == 完整答案,`finish_reason` 有值,`usage` 含三欄。
- [ ] `test_system_and_multiturn_mapping`:送含 `system` + 多輪 `user`/`assistant` 的 `messages`,斷言傳給 `llm.stream_chat` 的 `system` 已抽出、`convo` 不含 system 且順序保留。
- [ ] `test_tolerates_unknown_fields`:請求多帶 `temperature` / `stream_options` 等,不報 422。
- [ ] `test_empty_messages_422`:`messages: []` → 422(`min_length=1`)。
- **注意**:全程 mock,不打真 Claude;逐 token 增量遞送 in-process 測不準(緩衝),靠 Step 6 `curl -N` 肉眼確認。

### Step 6 — host 手動驗收 + 契約比對(開發完成)【硬性 DoD,需真 key,會計費】

```bash
uv run uvicorn fastapi_app_01.main:app --host 0.0.0.0 --reload   # 0.0.0.0 供之後容器內 Open WebUI 連得到

curl -s http://localhost:8000/v1/models                          # 期望:object=list,含模型 id

# 串流(逐字浮現 + OpenAI chunk + [DONE])
curl -N -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"x","stream":true,"messages":[{"role":"user","content":"用一句話解釋什麼是 RAG"}]}'

# 非串流(單一 chat.completion + usage)
curl -s -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"x","stream":false,"messages":[{"role":"user","content":"hi"}]}'
```

> **契約比對(SDD 驗證環)**:開 `http://localhost:8000/openapi.json`(或 `/docs`),確認新增的 `/v1/chat/completions`、`/v1/models` 與 Step 1 的 `api.yml` 一致;`/chat`(迭代 2)仍在、未被破壞。

### Step 7 — 容器發布驗證(收工前)【硬性 DoD,需真 key,會計費】

```bash
docker compose --profile full up --build -d api
curl -N -X POST http://localhost:8000/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"stream":true,"messages":[{"role":"user","content":"用一句話解釋什麼是 RAG"}]}'
docker compose --profile full down
```

### Step 8 — Open WebUI 整合(本迭代的展示成果)

新增 `openwebui` 服務到 `docker-compose.yml`(profile `webui`,見 D8):

```yaml
# 預計新增到 docker-compose.yml
  openwebui:
    profiles: ["webui"]
    image: ghcr.io/open-webui/open-webui:main
    ports: ["3000:8080"]
    environment:
      OPENAI_API_BASE_URL: ${OPENWEBUI_API_BASE:-http://host.docker.internal:8000/v1}
      OPENAI_API_KEY: dummy
    extra_hosts: ["host.docker.internal:host-gateway"]
    volumes: ["openwebui-data:/app/backend/data"]
# 並在檔尾 volumes: 區塊加 openwebui-data:
```

**兩種跑法**:
```bash
# 混合(日常):host 起 API(0.0.0.0),compose 只起 UI
uv run uvicorn fastapi_app_01.main:app --host 0.0.0.0 --reload
docker compose --profile webui up -d openwebui          # 開 http://localhost:3000

# 全容器:API 也在 compose,UI 指向服務名 api
OPENWEBUI_API_BASE=http://api:8000/v1 docker compose --profile full --profile webui up
```

**手動驗證**(本迭代展示成果):
- [ ] Open WebUI 模型下拉**列得出**模型(證明 `/v1/models` 通)。
- [ ] 在 UI 對話**逐字串流**浮現(證明 `/v1/chat/completions` `stream=true` 通)。
- [ ] 多輪:接續再問一題,前文有被帶上(證明前端帶歷史 + 多輪轉接通)。
- **注意**:API 須綁 `0.0.0.0`(host:`--host 0.0.0.0`;容器:compose `command` 已是);
  容器內 UI 連 host 用 `host.docker.internal`(mac/win 原生;Linux 靠上面的 `extra_hosts`)。

### Step 9 — 敘述文件對齊(收工前)

- `README.md`:迭代藍圖第 3 列 🚧→✅;「下一個迭代」改指向迭代 4(對話記憶);架構/快速啟動補 `/v1`;
  **新增「Open WebUI 串接」段,記錄 Step 8 的兩種跑法**(混合 / 全容器)與所需環境變數。
- `specs/tech-stack.md`:維持「迭代 1 技術棧」定位,僅在頂部定位說明補一句「迭代 3 已加 OpenAI 相容 `/v1`,見 `plans/iteration-3-openai-compat.md`」。

---

## 驗收與測試策略

沿用五層策略,把計費的真實呼叫壓到後面;每層各自涵蓋部分 AC。

| 層 | 做什麼 | 涵蓋 AC | 計費 |
| --- | ----------------------------------------- | -------------- | ---- |
| 1 自動測試(in-process,mock) | `uv run pytest`,mock `llm.stream_chat`/`complete_chat`;見 Step 5 | 1–7 | 否 |
| 2 啟動冒煙 | dummy key 起 app,`GET /v1/models` 回 200 | 1 | 否 |
| 3 config 行為 | `env -u ANTHROPIC_API_KEY` 確認 fail-fast | — | 否 |
| 4 容器冒煙 | `docker build` + `compose --profile full up` 起得來 | 9(形狀) | 否 |
| 5 **live E2E** | `curl` 對真 Claude(host + 容器,串流 + 非串流) | 2–3、9 | **是** |
| 6 **Open WebUI 整合** | UI 列模型 + 逐字對話 + 多輪 | 10 | **是** |

**AC 對照**(可觀察、可客觀判定):

1. `GET /v1/models` → 200,`{object:"list", data:[{id == anthropic_model, …}]}`。
2. `POST /v1/chat/completions`(`stream=true`)→ `text/event-stream`;chunk `object=="chat.completion.chunk"`;`delta.content` 串接 == 完整答案;末 chunk `finish_reason=="stop"`;結尾 `data: [DONE]`。
3. (`stream=false`)→ 200 JSON,`object=="chat.completion"`,`choices[0].message.content` == 完整答案,`finish_reason` 有值,`usage` 三欄齊。
4. `system` role 被抽到 Anthropic `system` 參數;`user`/`assistant` 多輪順序保留。
5. 容忍未知 OpenAI 欄位(`temperature` 等)不報錯。
6. 空 `messages` → 422。
7. `/chat`(迭代 2)維持原樣,未被破壞。
8. `/openapi.json` 含 `/v1` 路徑且與 `specs/api.yml` 一致。
9. 真 Claude:host + 容器 `curl /v1` 串流 / 非串流皆得出。
10. Open WebUI 指向 `/v1` 後可列模型並逐字串流多輪對話。

**誠實邊界**:

- **逐 token 增量遞送 in-process 測不準**(`TestClient` 緩衝)→ Layer 1 驗 OpenAI **契約**,真實逐字浮現靠 Layer 5/6。
- **真 Claude / Open WebUI** 只在 Layer 5/6 各做最小一次,計費最小化。

---

## 驗收標準(Definition of Done)

- [ ] **模型列得出**:`GET /v1/models` 回 OpenAI 格式模型清單。【Step 5/6】
- [ ] **串流相容**:`/v1/chat/completions` `stream=true` 回 `chat.completion.chunk` 事件流 + `[DONE]`,逐字浮現。【Step 5/6】
- [ ] **非串流相容**:`stream=false` 回單一 `chat.completion` JSON,含 `finish_reason` 與 `usage`。【Step 5/6】
- [ ] **多輪 + system 正確轉接**:歷史由前端帶入即支援多輪;`system` 走 Anthropic `system` 參數。【Step 5】
- [ ] **健壯解析**:容忍未知欄位;空 `messages` 回 422。【Step 5】
- [ ] **不破壞既有**:`/chat`(迭代 2)與 `/health` 不變;`uv run pytest` 全綠。【Step 5/6】
- [ ] **可發布**:容器版同樣回得出 `/v1` 串流。【Step 7】
- [ ] **Open WebUI 可用**:指向 `/v1` 後能列模型並逐字串流對話。【Step 8】
- [ ] **契約與文件對齊**:`specs/api.yml` 含 `/v1` 且與 `/openapi.json` 一致;README 第 3 列為 ✅。【Step 1/6/9】

---

## 風險 / 取捨

- **轉接層是新增複雜度**:OpenAI↔Anthropic 的 `system` 抽取、`finish_reason`/`usage` 映射、chunk 組裝是本迭代主要風險;以 `_split` + `_FINISH` 表 + dict 組裝把它收斂在 `openai_compat.py`,`core/llm` 保持中立。
- **OpenAI 格式只做夠用子集**:不支援多模態 content parts、tools、`logprobs`、`n>1`;`content` 假設為字串。超出即明確回最小錯誤或忽略(列為 Out)。
- **多輪歷史來源**:本迭代歷史**全由前端帶**(Open WebUI 每次送完整 `messages`)→ 無伺服器端狀態;迭代 4 才加伺服器端持久化。兩者是不同來源,屆時要講清楚取捨。
- **串流不附 usage**:OpenAI 串流的 usage 需 `stream_options.include_usage` 與額外尾包,本迭代省略(非串流才給 usage)。如 Open WebUI 顯示 token 數有缺,排後續補。
- **Open WebUI 網路**:容器內 UI 連 host 的 API 要用 `host.docker.internal`(mac/win);這是環境細節,非程式問題,文件需寫清楚。
- **錯誤處理刻意最小**:串流中途 / client 斷線 / 上游錯誤不特別處理,自然冒出;健全處理排迭代 6。
- **不引入新依賴**:全部用 stdlib + 內建 `StreamingResponse`;不引入 `openai` SDK、不引入 `sse-starlette`。

---

## 完成後 → 下一個迭代

迭代 4(對話記憶):接 Postgres 存對話歷史、支援**伺服器端**多輪。屆時 `/v1` 的「前端帶歷史」與
新的「伺服器端持久化」並存,需定義以哪個為準(或如何合併);`core/llm` 的 messages 由 DB 取出的歷史組裝。骨架與串流機制不變。
