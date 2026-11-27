export type Route = 'chat' | 'rag' | 'agent';

/** "deep_research" forces the Deep research route and a researched, cited report. */
export type ChatMode = 'auto' | 'deep_research';

export interface Step {
  id: string;
  /** memory = long-term memory recalled or saved, or the conversation summarised. */
  kind: 'route' | 'retrieval' | 'thinking' | 'tool' | 'memory';
  title: string;
  detail?: string;
  /** waiting = an action held for the user's approval; declined = not run (declined or never approved). */
  status: 'running' | 'done' | 'error' | 'waiting' | 'declined';
  tool?: string | null;
  result?: string;
  /** What a search turned up (title and link), shown as it arrives. */
  items?: { title: string; url?: string | null }[];
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

/** An action the agent wants to run that waits for the user's approval (see the approval card). */
export interface PendingAction {
  id: string;
  tool: string;
  /** server/tool, used by "Always allow". */
  key: string;
  server: string;
  title: string;
  args: Record<string, unknown>;
  description?: string;
}

export interface ApprovalRecord {
  id: string;
  tool: string;
  title?: string;
  server?: string;
  args?: Record<string, unknown>;
  /** dropped = a new message was sent before it was approved. */
  decision: 'approve' | 'decline' | 'dropped';
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
  mode?: ChatMode;
  status: 'streaming' | 'done' | 'error' | 'stopped';
  error?: string;
  elapsedMs?: number;
  model?: string;
  /** Set while the answer is paused, waiting for the user to approve these actions. */
  pendingApproval?: PendingAction[];
  approvals?: ApprovalRecord[];
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  message_count: number;
  /** Route of the latest answer, for the home board. */
  last_route?: Route | null;
  /** The project this chat belongs to, or null. */
  project_id?: string | null;
}

/** A workspace with its own chats, files and instructions. */
export interface Project {
  id: string;
  name: string;
  instructions: string;
  created_at: string;
  updated_at: string;
  chat_count: number;
  document_count: number;
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
    mode?: ChatMode;
    pending_approval?: { actions: PendingAction[] };
    approvals?: ApprovalRecord[];
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
  project_id?: string | null;
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
  /** short_term: where conversation threads are kept; long_term: where facts about the user are kept. */
  memory?: { short_term: string; long_term: 'postgres' | 'memory' | 'off' | string };
  /** True when Deep research has something to search (web search or documents). */
  deep_research?: boolean;
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
  /** false when the provider says this model can't call tools (Deep research quick look-ups need them). */
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
  kind: 'agent' | 'inbound' | 'webhook' | 'mcp';
  status: string;
  detail: string;
}

export type ToolSetting = 'auto' | 'ask' | 'off';

export interface ConnectionTool {
  name: string;
  key: string;
  description: string;
  kind: 'read' | 'act';
  /** null = the default for its kind (read tools run, act tools ask). */
  setting: ToolSetting | null;
  decision: 'run' | 'ask' | 'off';
  title?: string | null;
}

export interface ConnectionServer {
  name: string;
  label: string;
  /** file = config/mcp_servers.yaml, ui = added in the app. */
  origin: 'file' | 'ui';
  editable: boolean;
  transport: 'http' | 'sse' | 'stdio';
  url?: string | null;
  command?: string | null;
  args: string[];
  headers: Record<string, string>;
  env: Record<string, string>;
  enabled: boolean;
  status: 'idle' | 'connecting' | 'connected' | 'failed' | 'skipped' | 'disabled';
  detail: string;
  checked_at?: string | null;
  tools: ConnectionTool[];
}

export interface ConnectionsInfo {
  mcp_enabled: boolean;
  stdio_allowed: boolean;
  approvals: boolean;
  servers: ConnectionServer[];
  builtin: ConnectionTool[];
}

export interface ServerDraft {
  name: string;
  label?: string;
  transport: 'http' | 'sse' | 'stdio';
  url?: string;
  headers?: Record<string, string>;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  enabled?: boolean;
}

export type StreamEvent =
  | { type: 'meta'; conversation_id: string; message_id: string; user_message_id: string | null; is_new: boolean; resumed?: boolean }
  | { type: 'approval_required'; actions: PendingAction[] }
  | { type: 'route'; route: Route; label: string; reason: string }
  | { type: 'step'; step: Step }
  | { type: 'token'; text: string }
  | { type: 'draft_reset' }
  | { type: 'sources'; items: Source[] }
  | { type: 'title'; conversation_id: string; title: string }
  | { type: 'done'; message: StoredMessage }
  | { type: 'error'; code: string; message: string; request_id?: string };

export interface MemoryItem {
  id: string;
  content: string;
  category: string;
  source?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface MemoryList {
  enabled: boolean;
  backend: string;
  user_id: string;
  items: MemoryItem[];
}

export const ROUTE_LABEL: Record<Route, string> = {
  chat: 'Chat',
  rag: 'Documents',
  agent: 'Deep research',
};
