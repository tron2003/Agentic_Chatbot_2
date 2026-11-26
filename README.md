# Junction: an agentic chatbot that picks the route

A LangGraph assistant that sends every message down one of three routes:

| Route | Used for | What happens |
|---|---|---|
| **Chat** | Explanations, writing, small talk, questions about the conversation | One model call with conversation memory |
| **Documents** | Questions about files in your library | MMR retrieval over pgvector, answer cites passages like `[1]` |
| **Research** | Anything current, or tasks that need tools | A ReAct agent calls web search, calculator, date/time, your library and MCP tools, then answers with sources |

Answers stream token by token. Research steps appear live as a "transit line" timeline, and sources show under each answer.

![Welcome screen](docs/screenshots/welcome-dark.png)

## Features

- **Real streaming** over Server-Sent Events: route decision, reasoning steps, tokens and sources arrive as they happen (the old `/chat/stream` waited for the full answer, then replayed it)
- **Stop, regenerate, copy, export**: regenerate forks the LangGraph checkpoint, so the model never sees the question twice
- **Conversation history**: search, rename, delete, auto-generated titles, grouped by date
- **Document library**: drag in files or folders (PDF, Markdown, text, CSV, JSON, code), remove single documents, answers cite passages
- **Long-memory summarisation** that folds old turns into a running summary
- **Providers**: Claude, OpenAI, OpenRouter, Ollama, any OpenAI-compatible server, plus a `demo` model that needs no key
- **Optional integrations** (off by default): delegate tasks to **OpenClaw**, Hermes or any OpenAI-compatible agent; let those apps use Junction as their model through an OpenAI-compatible `/v1` API; signed webhooks (incl. OpenClaw hooks, n8n, Zapier); Junction as an **MCP server** for Claude Desktop, Cursor and other MCP clients. See [docs/integrations.md](docs/integrations.md)
- **Production basics**: optional API-key auth, per-client rate limiting, request IDs in every log line and error, JSON logs, `/health` + `/ready` probes, upload size and type limits, sandboxed file tools, graceful degradation when Postgres, MCP or a provider is missing
- **UI**: layered parallax (pointer and scroll), light/dark/system theme, keyboard shortcuts (`Ctrl K` new chat, `/` focus, `Esc` stop), responsive down to phone width, reduced-motion support

## Quick start (local)

Requirements: Python 3.11+, Node 20.11+. Postgres is optional.

```bash
# 1. Backend
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env            # macOS/Linux: cp .env.example .env
#    edit .env: set ANTHROPIC_API_KEY (or LLM_PROVIDER=demo to try it without a key)
python run.py                     # http://localhost:8001  (API docs at /docs)

# 2. Frontend (second terminal)
cd frontend
npm install
npm run dev                       # http://localhost:3000, proxies /api to :8001
```

Without `DB_URI`, conversations, memory and documents live in memory and reset on restart. Point `DB_URI` at Postgres with pgvector to keep them:

```bash
docker compose up -d db           # just the database, from docker-compose.yml
# .env: DB_URI=postgresql://chatbot:change-me@localhost:5432/chatbot
```

For the document library you need an embedding model: `ollama pull qwen3-embedding:0.6b` (default), or set `EMBEDDING_PROVIDER=openai`.

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
| Have Junction ask your OpenClaw assistant to do things (message people, set reminders) | `OPENCLAW_ENABLED=true`, `OPENCLAW_URL`, `OPENCLAW_GATEWAY_TOKEN` |
| Hand tasks to Hermes Agent | `HERMES_ENABLED=true`, `HERMES_URL`, `HERMES_API_KEY` |
| Use Junction as the model inside OpenClaw, Hermes, Open WebUI or any OpenAI SDK | `ENABLE_OPENAI_API=true`, `OPENAI_API_KEYS` |
| Get OpenClaw (or n8n/Zapier) notified about answers and new documents | `OPENCLAW_HOOKS_ENABLED=true` / `WEBHOOK_ENABLED=true` |
| Use Junction from Claude Desktop, Cursor or other MCP clients | `ENABLE_MCP_SERVER=true`, `MCP_SERVER_API_KEYS` |

## Deploy to Render

`render.yaml` is a Blueprint for a Docker web service and a managed Postgres. In Render choose **New > Blueprint**, select the repo, and fill in `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` (embeddings), `TAVILY_API_KEY` and `API_KEYS` when prompted. Set `API_KEYS` on any public deployment: the UI asks for the key once and keeps it in the browser.

## Configuration

Secrets and deployment settings go in `.env` (documented in `.env.example`). Model and pipeline tuning goes in `config/config.yaml`, which can reference env vars as `${VAR}` or `${VAR:-default}`.

| Setting | Where | Default |
|---|---|---|
| Model provider and names | `LLM_PROVIDER`, `CLAUDE_MODEL`, `config.yaml > llm` | `claude`, `claude-sonnet-5-5` |
| Router/title/summary model | `CLAUDE_ROUTER_MODEL` or `llm.router_provider` | `claude-haiku-5-5` |
| Retrieval | `config.yaml > rag` (`k`, `fetch_k`, chunking, optional rerank) | k=6, MMR |
| Agent limits | `config.yaml > agent` | 8 iterations, 45 s per tool |
| Memory | `config.yaml > memory` | summarise after 24 messages |
| MCP servers | `config/mcp_servers.yaml`, `ENABLE_MCP` | filesystem, GitHub (if `GITHUB_TOKEN`) |

## API

Interactive docs at `/docs` (development) or `/api/docs` (production).

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/chat/stream` | Stream an answer (SSE). Body: `{message, conversation_id?, attachments?}` or `{conversation_id, regenerate: true}` |
| POST | `/api/chat` | Same, as one JSON response |
| GET | `/api/conversations?q=` | List or search conversations |
| GET / PATCH / DELETE | `/api/conversations/{id}` | Open, rename, delete |
| GET | `/api/conversations/{id}/export` | Download as Markdown |
| POST / GET | `/api/documents` | Upload files (multipart `files`), list library |
| DELETE | `/api/documents/{id}` | Remove one document (and its vectors) |
| GET | `/api/meta`, `/health`, `/ready` | Capabilities, liveness, readiness |
| GET | `/api/integrations?refresh=` | Integration status (re-checks external agents) |
| GET / POST | `/v1/models`, `/v1/chat/completions` | OpenAI-compatible API (when `ENABLE_OPENAI_API=true`) |
| POST | `/mcp` | MCP server, streamable HTTP (when `ENABLE_MCP_SERVER=true`) |

`POST /chat` and `/chat/stream` with `thread_id` still work for older scripts. The SSE event types are listed in [ARCHITECTURE.md](ARCHITECTURE.md#streaming-protocol).

## Project layout

```
backend_api.py                 ASGI entry point (uvicorn backend_api:app)
run.py                         dev/prod launcher
config/                        config.yaml (models, RAG, agent), mcp_servers.yaml, integrations.yaml
src/agentic_chatbot/
  api/                         FastAPI app, routes, middleware, auth + rate limit
  pipelines/chatbot_pipeline   LangGraph graph + streaming adapter
  nodes/                       router, chat, rag, agent, summarizer
  services/                    chat turn orchestration, conversation store, knowledge base
  integrations/                optional: external agents, OpenAI-compatible API, webhooks, MCP server
  components/                  LLM, embeddings, vector store, checkpointer, demo model
  tools/                       web search, calculator, date/time, library search, read_pdf, MCP
  prompts/                     prompt builders (dates injected per request)
frontend/                      React 19 + Vite + Tailwind 4 + Motion
tests/                         pytest suite (runs on the demo model, no keys needed)
```

## Tests

```bash
pip install -r requirements-dev.txt
pytest                         # 42 tests: SSE protocol, routes, regenerate, RAG, auth, limits, integrations (incl. a live MCP client)
ruff check src tests
cd frontend && npm test && npm run build   # 14 UI tests, typecheck, production build
```

CI (`.github/workflows/ci.yml`) runs all three plus a Docker build.
