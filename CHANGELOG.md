# Changelog

## 2.6.0 (branch feature/connector-hub, 2026-11-27)

### Added: Projects
- A project is a workspace with its own chats, files and instructions (`chatbot_projects` table; `project_id` added to conversations and documents, existing rows stay outside projects).
- `core/scope.py`: each chat turn sets its project scope once in a context variable. The router, document search (a `doc_id` filter on PGVector or the in-memory store), the agent's knowledge-base tool, spreadsheet SQL and every prompt read it, so a project chat sees only that project's files and follows its instructions, and chats outside projects never see a project's files. Long-term memory stays shared.
- API: `/api/projects` (list with chat and file counts, create, get, rename or change instructions, delete with `?confirm=true`, which removes the project's chats, their threads and its documents). `project_id` on `POST /api/chat/stream` starts a chat in a project (a conversation never changes project); `project_id` form field on uploads; `?project=<id>|none` filters on `/api/conversations` and `/api/documents`.
- UI: Projects in the sidebar (project chats live on their project's page), a project page with editable name, instructions, files and chats, a breadcrumb back to the project from its chats, project tags on the home board, and the library and attachments scoped to the current project.

### Fixed
- `config/connections.json` could be read back stale right after a save on Windows (two writes in the same file-time tick); a save now clears the cache.

### Tests
- `tests/test_projects.py` (6): counts and renaming, chats and documents kept apart, an empty project not routing to documents, instructions in prompts, spreadsheets scoped to the project, unknown project and cascading delete. pytest 134 passed (also on the Windows dev machine), vitest 44, tsc, ruff and the build clean.

## 2.5.0 (branch feature/connector-hub, 2026-11-27)

### Added: approval before actions
- `services/tool_policy.py` sorts every tool into **read** (look-ups) or **act** (send, create, delete, write, `ask_<agent>`). MCP tools use the server's `readOnlyHint` / `destructiveHint`; otherwise the name decides, and anything unclear counts as an action.
- When the agent asks for an act tool, read tools from the same turn still run, the agent saves its loop in state (`agent_scratch`, `agent_round`, `agent_sources`, `pending_actions`), and the graph pauses in a new `approval` node with `interrupt()`. The pause lives in its own small node because LangGraph re-runs the interrupted node on resume, which would have repeated the model call and the finished tools.
- New SSE event `approval_required`; the paused answer is stored with `metadata.pending_approval`. `POST /api/chat/approve` resumes with `Command(resume=…)` and streams the rest into the same message; `metadata.approvals` records each decision. "Don't ask again" saves the tool as Always allow.
- A new message on a paused chat declines the action (the stored message is marked "Not approved"), and the new turn clears the saved loop.
- Runs with nobody to approve (OpenAI-compatible API, MCP server `ask`) decline act tools with a note to approve them in the app. `TOOL_APPROVALS=off` / `approvals.mode: off` runs everything.
- The router now sends any message that names one of the agent's tools ("use write_file to …") to the agent.

### Added: Connections panel
- `mcp_manager` keeps tools per server and can connect, reload and remove one server while the app runs; each tool is tagged with its server.
- `config/connections.json` (git-ignored, `CONNECTIONS_PATH`) holds servers added in the app, on/off for servers from `mcp_servers.yaml`, and per-tool settings (`auto`, `ask`, `off`; tools set to Off are hidden from the agent).
- `/api/connections`: list, test, add, edit, switch, remove, reconnect, and `PUT /api/connections/tools`. Header and env values are masked in responses and kept when sent back masked. Local (stdio) servers can be added from the app only in development or with `ALLOW_UI_STDIO=true`; commands with shell characters are refused.
- MCP servers appear in the sidebar's Connections list and `/api/meta`.

### Changed: the UI
- **Home** is now a departures board of your own work: greeting with your name (from long-term memory) and the local time, the composer with suggestions from your files and sheets, recent chats with the route each one took (`last_route` added to the conversation list), and a side column with what Reittiä knows about you, your library and your connections.
- **Answers** hang off their route's line (a station ring and a coloured rail), with larger, higher-contrast text; your messages are solid bubbles. Action buttons are visible without hovering.
- **Approval card** with a hazard-striped edge in a new signal colour used only for approvals; timeline stops gain waiting and declined states; the live line says "Waiting for your approval…".
- **Connections panel** slides over the chat: servers as lines coloured by status, tools with Reads/Acts badges and Always allow / Ask first / Off, an add/edit form with Test connection.
- Maths renders with KaTeX: `\[ … \]` and `\( … \)` are rewritten to `$$ … $$`; single `$` stays text so prices aren't mangled. New dependencies: katex, remark-math, rehype-katex.
- The backdrop's transit lines are gone and its glows dimmed, so nothing runs through the text.

### Tests
- `tests/test_approvals_and_connections.py` (26) plus updated integration and routing tests: pytest 128 passed. Frontend: 44 passed (approval mapping, names from memory, maths, waiting activity). tsc, ruff and the build are clean.
- Live check (liquid/lfm-3-1.7b:free): "Use the write_file tool to create hello.txt…" paused at the approval card; Approve wrote `workspace/hello.txt` and the answer continued in the same message.

## 2.1.0

### Added: optional integrations (all off by default, `config/integrations.yaml`)
- **External agents**: each configured OpenAI-compatible agent becomes an `ask_<name>` tool for the Research route, with ready presets for **OpenClaw** (gateway `/v1/chat/completions`, one OpenClaw session per Junction conversation) and **Hermes Agent**. The router and timeline know about them, and failures show as a red timeline stop instead of breaking the answer.
- **OpenAI-compatible API** (`/v1/models`, `/v1/chat/completions`, JSON and streaming) so OpenClaw, Hermes, Open WebUI, LibreChat or any OpenAI SDK can use Junction as their model. Stateless by default; with `user`, conversations are kept and appear in the sidebar. Separate API keys.
- **Webhooks**: `conversation.created`, `answer.completed`, `document.ingested`, `document.deleted`. Signed JSON (HMAC-SHA256) for n8n/Zapier/Make, plus an OpenClaw `/hooks/agent` format, delivered in the background with retries.
- **MCP server** at `/mcp` (stateless streamable HTTP, key auth) with `ask`, `search_documents` and `list_documents` tools.
- Sidebar "Connections" status, `GET /api/integrations`, startup reachability probes, and an invalid integrations file reported without taking the app down.
- 12 integration tests, including the official MCP client against a live server and the OpenAI SDK format.

### Changed
- Turn preparation moved into `services/chat_service.prepare_turn`, shared by the web UI, the OpenAI-compatible API and the MCP server.

## 2.0.0

### Fixed
- **Conflicting `chat_history` schemas.** `routes/chat_history.py` and `utils/chat_persistence.py` each created a `chat_history` table with a different primary key, so whichever ran second failed: either the sidebar broke or messages silently weren't saved. There is now one store (`chatbot_*` tables).
- **`/chat/stream` didn't stream.** It ran the whole graph, then replayed the steps. It now streams tokens and steps live from LangGraph (`messages` + `custom` + `updates` stream modes).
- **Router prompt vs. schema mismatch.** The prompt told the model to answer `tool`, but the `Router` schema only accepts `agent`, so structured output failed on research questions.
- **Python 3.11+ crash.** `asyncio.coroutine` (removed in 3.11) was used in the agent and tool nodes whenever the model requested an unknown tool.
- **Summariser lost history.** It summarised the most recent messages and deleted the older ones, which were never summarised.
- **Conversation windows started with an assistant turn** (`messages[-6:]`), which Anthropic rejects.
- **Stale dates.** The web-search prompt baked `date.today()` in at import, so a long-running server used its start date. Dates are now injected per request.
- **Path traversal on upload.** `UPLOAD_DIR / file.filename` let a crafted name write outside the upload folder.
- **`read_pdf` could read any file on the server.** It's now confined to `workspace/`.
- **Startup was fragile.** LLMs, the vector store (Ollama + Postgres) and MCP servers were all created at import time, so one missing piece stopped the API from booting. Everything is now lazy, and failures are reported by `/ready` instead.
- **"Clear knowledge base" didn't delete vectors**, only a JSON tracker. Documents can now be removed one at a time, along with their vectors.
- **Deployment files.** The Dockerfile copied files that don't exist and never served the UI. `requirements.txt` was missing about 10 packages and listed the PyPI `asyncio` package, which breaks modern Python. `render.yaml` used syntax Render doesn't support. `init.sql` created tables that clashed with the app's.
- Router and summariser used blocking `invoke` inside the async graph.
- Correlation IDs were regenerated on every call, so they never matched across log lines.

### Added
- Modern parallax UI with a live routing map, reasoning timeline, sources, Markdown with code highlighting, stop/regenerate/copy/export, search/rename/delete history, a document library panel, themes and keyboard shortcuts
- Regenerate via LangGraph checkpoint forking
- Auto-generated conversation titles
- Calculator, date/time and library-search tools for the agent. Web results become clickable sources
- `demo` provider for running without an API key
- API-key auth, rate limiting, request IDs, JSON logs, `/ready`, structured errors
- pytest suite (30 tests), ruff, GitHub Actions CI, multi-stage Docker image serving UI + API
