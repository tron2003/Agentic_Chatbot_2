# Changelog

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
