-- Runs once when the Postgres container is first created.
-- The app creates its own tables on startup (chatbot_conversations,
-- chatbot_messages, chatbot_documents, LangGraph checkpoints and the
-- langchain_pg_* vector tables), so the only thing needed here is pgvector.
CREATE EXTENSION IF NOT EXISTS vector;
