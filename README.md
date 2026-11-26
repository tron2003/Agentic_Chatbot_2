# Reittiä: an agentic chatbot that picks the route

*Reittiä* is Finnish for "route". It's a LangGraph assistant that sends every message down one of three routes, and remembers you between conversations:

| Route | Used for | What happens |
|---|---|---|
| **Chat** | Explanations, writing, small talk, questions about the conversation | One model call with the conversation and what it knows about you |
| **Documents** | Questions about files in your library | MMR retrieval over pgvector; the answer cites passages like `[1]` |
| **Deep research** | Anything current, look-ups, calculations, research reports | Quick questions go to a tool agent (web search, calculator, spreadsheets, your library, MCP tools). Research requests are planned into sub-questions, searched in parallel and written up as a cited report you can export as a PDF |

Answers stream token by token. While Reittiä works, it types out what it's doing ("Searching “Python 3.15 release notes”…"), the timeline shows each step with the sites it found, and sources show under each answer.

![Welcome screen](docs/screenshots/welcome-dark.png)

## Features

### Answers
- **Real streaming** over Server-Sent Events: route decision, steps, tokens and sources arrive as they happen.
- **Live activity line**: instead of a loading skeleton, the current step is typed out (the query being searched, the site being read, "Crunching the numbers…", "Writing the report…"), with a stack of badges for the sites found. Finished searches list their results as linked chips in the timeline.
- **Stop, regenerate, copy, export**: regenerate forks the LangGraph checkpoint, so the model never sees the question twice. Conversations export as Markdown.
- **Conversation history**: search, rename, delete, auto-generated titles, grouped by date.

### Deep research
- Switch on **Deep research** in the composer (one message at a time), or just ask for research, a report, a comparison or an analysis.
- `research_plan` splits the question into up to 4 sub-questions → one `research_worker` per sub-question runs in parallel (LangGraph `Send`) → `research_review` checks for gaps and runs one follow-up round → `research_write` streams a Markdown report with a summary, themed sections, tables and links like `[3](url)`.
- Built to work with small free models: sources are spread evenly across sub-questions and kept to a text budget, an empty report is retried with fewer sources, and structured calls ask for plain JSON first (`utils/structured.py`).
- **Export PDF** under every report: the report's heading as the title, the question, date and model, tables and lists kept, and a linked source list. Unicode fonts (Segoe UI on Windows, DejaVu in Docker), so ₹ and € print correctly.

### Your spreadsheets, calculated exactly
- Every uploaded `.xlsx`, `.xlsm`, `.xls`, `.csv` or `.tsv` becomes a SQL table as well as searchable text. Ask "total refund per party" or "revenue by month" and the agent runs a query instead of estimating.
- Parsing handles real-world exports: title rows above the header, `₹ 1,250.50`, `Rs`, `%`, `(300)` as negative, real dates, and **Total** rows removed so sums aren't doubled.
- Queries run in DuckDB with file and network access turned off: one `SELECT`/`WITH` only, at most 50 rows, and the file used is cited as the source.

### Memory
- **Short-term**: the conversation in each thread (LangGraph checkpointer). Each turn sends the newest messages that fit a token budget, and a **summarise** block folds older messages into a running summary once the thread grows past 6,000 tokens or 24 messages.
- **Long-term**: facts about you (name, role, projects, preferences) kept across conversations in the LangGraph store, in **PostgreSQL** when `DB_URI` is reachable. A **recall** block loads them at the start of every turn; a **remember** block runs after the answer, only when you said something about yourself, and adds, updates or deletes facts. Passwords, keys and card numbers are never stored.
- The **Memory** panel in the sidebar lists, adds and deletes memories; a "Memory updated" pill appears under an answer when something was saved. `LONG_TERM_MEMORY=off` turns it off.

### Documents
- Drag in files or folders: PDF, Word (`.docx`), Excel (`.xlsx`, `.xlsm`, `.xls`), CSV, Markdown, text, JSON and code. Remove documents one at a time; answers cite passages.
- Oversized files are stopped before upload with the reason shown. In development, Reittiä starts Ollama for embeddings if it's installed but not running.

### Models and search
- **Model picker**: click the model name in the sidebar to choose a provider and model from live lists (OpenRouter with free models first, installed Ollama models, OpenAI, Anthropic, any OpenAI-compatible server). Models that can't call tools are marked. The choice applies on the next message, with an optional separate model for routing, titles and summaries.
- **Providers**: Claude, OpenAI, OpenRouter, Ollama, any OpenAI-compatible server, plus a `demo` model that needs no key.
- **Web search**: Tavily when `TAVILY_API_KEY` is set, otherwise DuckDuckGo (no key needed); Tavily failures also fall back to DuckDuckGo.
- **Routing**: the router model decides, with a plain one-word retry and a keyword fallback when the model is rate-limited. Explicit research requests always go to Deep research, and calculations about your spreadsheets always go to the tool agent.

### Platform
- **Optional integrations** (off by default): delegate tasks to **OpenClaw**, Hermes or any OpenAI-compatible agent; let those apps use Reittiä as their model through an OpenAI-compatible `/v1` API; signed webhooks (OpenClaw hooks, n8n, Zapier); Reittiä as an **MCP server** for Claude Desktop, Cursor and other MCP clients. See [docs/integrations.md](docs/integrations.md).
- **Production basics**: optional API-key auth, per-client rate limiting, request IDs in every log line and error, JSON logs, `/health` + `/ready` probes, upload size and type limits, sandboxed file tools, and graceful fallback to in-memory storage when Postgres, Ollama, MCP or a provider is missing in development.
- **Live config reload**: saving `.env` or `config/config.yaml` takes effect on the next request, no restart needed.
- **UI**: layered parallax, light/dark/system theme, keyboard shortcuts (`Ctrl K` new chat, `/` focus, `Esc` stop), responsive down to phone width, and reduced-motion support for every animation.

## How a message flows

```mermaid
flowchart LR
    S([message]) --> recall
    recall --> router
    router -->|Chat| chat
    router -->|Documents| rag
    router -->|Deep research| plan[research_plan]
    plan -->|quick look-up or spreadsheet| agent[tool agent]
    plan -->|research| workers[research_worker × N]
    workers --> review[research_review]
    review -->|gaps| workers
    review --> write[research_write]
    chat & rag & agent & write --> remember & summarize
    remember & summarize --> E([done])
```

`remember` and `summarize` run in parallel after every answer. More detail is in [ARCHITECTURE.md](ARCHITECTURE.md).

## Quick start (local)

Requirements: Python 3.11+, Node 20.11+. Postgres and Ollama are optional.

```bash
# 1. Backend
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env
#    edit .env: set a provider key (ANTHROPIC_API_KEY, OPENROUTER_API_KEY, ...)
#    or LLM_PROVIDER=demo to try it without a key
python run.py                     # http://localhost:8001  (API docs at /docs)

# 2. Frontend (second terminal)
cd frontend
npm install
npm run dev                       # http://localhost:3000, proxies /api to :8001
```

You can also pick the model in the UI afterwards; the choice is saved to `config/model_selection.json` (git-ignored) and overrides `LLM_PROVIDER`.

Without `DB_URI`, conversations, both memories and documents live in memory and reset on restart. Point `DB_URI` at Postgres with pgvector to keep them:

```bash
docker compose up -d db           # just the database, from docker-compose.yml
# .env: DB_URI=postgresql://chatbot:change-me@localhost:5432/chatbot
```

For the document library you need an embedding model: `ollama pull qwen3-embedding:0.6b` (default), or set `EMBEDDING_PROVIDER=openai`. Changing the embedding model later means re-adding your documents.

## Run everything in Docker

```bash
cp .env.example .env              # add your keys
docker compose up -d --build      # Postgres + app; UI and API on http://localhost:8001
```

The image builds the React app and FastAPI serves it, so one container and one port cover both. For Ollama on the host machine, set `OLLAMA_BASE_URL=http://host.docker.internal:11434`.

## Integrations (optional)

Turn any of these on in `.env`. They're configured in `config/integrations.yaml`, and the full setup, including OpenClaw config snippets, is in [docs/integrations.md](docs/integrations.md).

| Want to… | Set |
|---|---|
| Have Reittiä ask your OpenClaw assistant to do things (message people, set reminders) | `OPENCLAW_ENABLED=true`, `OPENCLAW_URL`, `OPENCLAW_GATEWAY_TOKEN` |
| Hand tasks to Hermes Agent | `HERMES_ENABLED=true`, `HERMES_URL`, `HERMES_API_KEY` |
| Use Reittiä as the model inside OpenClaw, Hermes, Open WebUI or any OpenAI SDK | `ENABLE_OPENAI_API=true`, `OPENAI_API_KEYS` |
| Get OpenClaw (or n8n/Zapier) notified about answers and new documents | `OPENCLAW_HOOKS_ENABLED=true` / `WEBHOOK_ENABLED=true` |
| Use Reittiä from Claude Desktop, Cursor or other MCP clients | `ENABLE_MCP_SERVER=true`, `MCP_SERVER_API_KEYS` |

For compatibility with apps already connected, the `X-Junction-*` webhook headers, the `junction` model id of the OpenAI-compatible API and the `junction.*` browser storage keys keep their old names.

## Deploy to Render

`render.yaml` is a Blueprint for a Docker web service and a managed Postgres. In Render choose **New > Blueprint**, select the repo, and fill in `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (embeddings), `TAVILY_API_KEY` and `API_KEYS` when prompted. Set `API_KEYS` on any public deployment: the UI asks for the key once and keeps it in the browser.

## Configuration

Secrets and deployment settings go in `.env` (documented in `.env.example`). Model and pipeline tuning goes in `config/config.yaml`, which can reference env vars as `${VAR}` or `${VAR:-default}`. Both are re-read when saved.

| Setting | Where | Default |
|---|---|---|
| App name | `APP_NAME` | `Reittiä` |
| Model provider and names | `LLM_PROVIDER`, `CLAUDE_MODEL`, `config.yaml > llm`, or the model picker | `claude`, `claude-sonnet-5-5` |
| Router/title/summary model | `ROUTER_PROVIDER`, `CLAUDE_ROUTER_MODEL`, or the model picker | the answer model |
| Web search | `WEB_SEARCH_PROVIDER` (`auto`, `tavily`, `duckduckgo`, `off`) | `auto` |
| Embeddings | `EMBEDDING_PROVIDER`, `OLLAMA_EMBED_MODEL`, `OLLAMA_AUTOSTART` | `ollama`, `qwen3-embedding:0.6b`, on (development only) |
| Retrieval | `config.yaml > rag` (`k`, `fetch_k`, chunking, optional rerank) | k=6, MMR |
| Tool agent | `config.yaml > agent` | 8 iterations, 45 s per tool |
| Deep research | `config.yaml > research` | 4 sub-questions, 2 rounds, 12 report sources |
| Short-term memory | `config.yaml > memory` | 3,000-token window, summarise after 6,000 tokens or 24 messages |
| Long-term memory | `LONG_TERM_MEMORY`, `MEMORY_USER_ID`, `config.yaml > memory` | on, `local`, 200 memories |
| Uploads | `MAX_UPLOAD_MB` | 25 MB per file |
| MCP servers | `config/mcp_servers.yaml`, `ENABLE_MCP` | filesystem, GitHub (if `GITHUB_TOKEN`) |

## API

Interactive docs at `/docs` (development) or `/api/docs` (production).

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/chat/stream` | Stream an answer (SSE). Body: `{message, conversation_id?, attachments?, mode?}` (`mode`: `auto` or `deep_research`), or `{conversation_id, regenerate: true}` |
| POST | `/api/chat` | Same, as one JSON response |
| GET | `/api/conversations?q=` | List or search conversations |
| GET / PATCH / DELETE | `/api/conversations/{id}` | Open, rename, delete |
| GET | `/api/conversations/{id}/export` | Download as Markdown |
| GET | `/api/conversations/{id}/messages/{message_id}/pdf` | Download one answer (a Deep research report) as a PDF |
| POST / GET | `/api/documents` | Upload files (multipart `files`), list library |
| DELETE | `/api/documents/{id}` | Remove one document, its vectors and its spreadsheet table |
| GET / PUT / DELETE | `/api/models` | List providers and models, save a choice, reset to `.env` |
| GET / POST / DELETE | `/api/memory`, `/api/memory/{id}` | List, add and delete long-term memories (`DELETE /api/memory?confirm=true` forgets all) |
| GET | `/api/meta`, `/health`, `/ready` | Capabilities (model, web search, memory, Deep research), liveness, readiness |
| GET | `/api/integrations?refresh=` | Integration status (re-checks external agents) |
| GET / POST | `/v1/models`, `/v1/chat/completions` | OpenAI-compatible API (when `ENABLE_OPENAI_API=true`) |
| POST | `/mcp` | MCP server, streamable HTTP (when `ENABLE_MCP_SERVER=true`) |

`POST /chat` and `/chat/stream` with `thread_id` still work for older scripts. SSE events: `route`, `step` (updated by id, with the `items` a search found), `token`, `draft_reset`, `sources`, `answer` and `done`; details in [ARCHITECTURE.md](ARCHITECTURE.md#streaming-protocol).

## Project layout

```
backend_api.py                 ASGI entry point (uvicorn backend_api:app)
run.py                         dev/prod launcher
config/                        config.yaml (models, RAG, agent, research, memory), mcp_servers.yaml, integrations.yaml
src/agentic_chatbot/
  api/                         FastAPI app, routes (chat, history, documents, models, memory, system), auth + rate limit
  pipelines/chatbot_pipeline   LangGraph graph + streaming adapter
  nodes/                       router, chat, rag, agent, research (plan/worker/review/write), memory (recall/remember), summarizer
  services/                    chat turns, conversation store, knowledge base, long-term memory, spreadsheets, report PDF
  integrations/                optional: external agents, OpenAI-compatible API, webhooks, MCP server
  components/                  LLM, embeddings, vector store, checkpointer + store, Ollama autostart, demo model
  tools/                       web search, calculator, date/time, library search, spreadsheet SQL, read_pdf, MCP
  prompts/                     prompt builders (dates and memories injected per request)
  utils/                       document loaders, context window, structured output
frontend/                      React 19 + Vite + Tailwind 4 + Motion
tests/                         pytest suite (runs on the demo model, no keys, no network)
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest                         # 101 tests: SSE protocol, routes, routing, regenerate, RAG, memory, Deep research,
                               # spreadsheets and SQL safety, PDF export, model picker, web search, config reload,
                               # database fallback, auth, limits, integrations (incl. a live MCP client)
ruff check src tests
cd frontend && npm test && npm run build   # 39 UI tests, type check, production build
```

Tests never go online, start Ollama, or touch your saved model choice. CI (`.github/workflows/ci.yml`) runs all three plus a Docker build.
