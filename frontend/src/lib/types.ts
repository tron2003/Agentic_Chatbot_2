export type Route = 'chat' | 'rag' | 'agent';

export interface Step {
  id: string;
  kind: 'route' | 'retrieval' | 'thinking' | 'tool';
  title: string;
  detail?: string;
  status: 'running' | 'done' | 'error';
  tool?: string | null;
  result?: string;
  ts: string;
}

export interface Source {
  kind: 'web' | 'doc';
  title: string;
  url?: string | null;
  page?: number | null;
  snippet?: string | null;
  index?: number | null;
}

export interface Attachment {
  id: string;
  name: string;
}

export interface UIMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
  route?: Route;
  routeReason?: string;
  steps: Step[];
  sources: Source[];
  attachments?: Attachment[];
  status: 'streaming' | 'done' | 'error' | 'stopped';
  error?: string;
  elapsedMs?: number;
  model?: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface StoredMessage {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  metadata: {
    route?: Route;
    route_reason?: string;
    steps?: Step[];
    sources?: Source[];
    attachments?: Attachment[];
    elapsed_ms?: number;
    model?: string;
    stopped?: boolean;
    failed?: boolean;
  };
  created_at: string;
}

export interface DocumentInfo {
  id: string;
  name: string;
  file_type: string;
  size_bytes: number;
  chunks: number;
  created_at: string;
}

export interface UploadResponse {
  results: { name: string; status: 'ok' | 'error'; document?: DocumentInfo | null; error?: string | null }[];
  documents_added: number;
  chunks_added: number;
}

export interface Meta {
  app_name: string;
  version: string;
  model: { provider: string; model: string };
  router_model: { provider: string; model: string };
  /** "ui" when chosen in the model picker, "env" when it comes from .env / config.yaml. */
  model_source?: 'ui' | 'env';
  llm_ready: boolean;
  llm_error: string | null;
  auth_required: boolean;
  web_search: boolean;
  web_search_provider?: string | null;
  tools: string[];
  knowledge_base: { backend: string; documents: number };
  persistence: string;
  limits: { max_upload_mb: number; max_message_chars: number };
  integrations?: { items: Integration[]; error: string | null };
}

export interface ModelChoice {
  provider: string;
  model: string;
}

export interface ModelOption {
  id: string;
  label?: string;
  free?: boolean;
  /** false when the provider says this model can't call tools (Research needs them). */
  tools?: boolean | null;
}

export interface ProviderInfo {
  id: string;
  label: string;
  configured: boolean;
  needs: string | null;
  default_model: string;
  models: ModelOption[];
  error: string | null;
}

export interface ModelCurrent {
  main: ModelChoice;
  router: ModelChoice;
  source: 'ui' | 'env';
  ready: boolean;
  error: string | null;
}

export interface ModelCatalog {
  current: ModelCurrent;
  providers: ProviderInfo[];
}

export interface Integration {
  name: string;
  label: string;
  kind: 'agent' | 'inbound' | 'webhook';
  status: string;
  detail: string;
}

export type StreamEvent =
  | { type: 'meta'; conversation_id: string; message_id: string; user_message_id: string | null; is_new: boolean }
  | { type: 'route'; route: Route; label: string; reason: string }
  | { type: 'step'; step: Step }
  | { type: 'token'; text: string }
  | { type: 'draft_reset' }
  | { type: 'sources'; items: Source[] }
  | { type: 'title'; conversation_id: string; title: string }
  | { type: 'done'; message: StoredMessage }
  | { type: 'error'; code: string; message: string; request_id?: string };

export const ROUTE_LABEL: Record<Route, string> = {
  chat: 'Chat',
  rag: 'Documents',
  agent: 'Research',
};
