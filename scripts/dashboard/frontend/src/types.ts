export type Scope = "engineering" | "code";
export type TabId = "overview" | "logs" | "files" | "upload" | "repos" | "indexing" | "watchers";
export type LogSource = "dashboard" | "watchers" | "memory" | "code";

export interface TokenSpeed {
  tokens_per_second: number | null;
  source: string | null;
  note: string | null;
}

export interface DashboardStatus {
  ok: boolean;
  timestamp: string;
  llama: {
    ok: boolean;
    error?: string | null;
    base_url?: string;
    latency_ms?: number | null;
    model?: string | null;
    chat_latency_ms?: number | null;
    approximate_token_speed?: TokenSpeed | null;
  };
  qdrant: {
    ok: boolean;
    error?: string | null;
    url?: string;
    latency_ms?: number | null;
    status_code?: number | null;
  };
  memories: Record<Scope, {
    ok: boolean;
    error?: string | null;
    path: string;
    file_count: number;
    latest_modified_time: string | null;
  }>;
  system: {
    ok: boolean;
    error?: string | null;
    cpu?: { usage_percent: number; count: number };
    ram?: { usage_percent: number; total_bytes: number; available_bytes: number; used_bytes: number };
    disk?: { path: string; usage_percent: number; total_bytes: number; free_bytes: number; used_bytes: number };
  };
  logs: Record<"memory" | "code", {
    ok: boolean;
    warning?: boolean;
    error?: string | null;
    path: string;
    exists: boolean;
    size_bytes: number;
    latest_modified_time: string | null;
  }>;
  log_capture?: { enabled: boolean };
  watchers?: { ok: boolean; watchers: Record<Scope, WatcherStatus> };
}

export interface MemoryFile {
  scope: Scope;
  name?: string;
  path: string;
  kind?: "file" | "directory";
  size_bytes: number | null;
  modified_time: string;
  extension: string;
  child_count?: number | null;
  can_delete?: boolean;
}

export interface FilesResponse {
  ok: boolean;
  scope: Scope;
  path?: string;
  root?: string;
  entries?: MemoryFile[];
  files: MemoryFile[];
}

export interface LogsResponse {
  ok: boolean;
  source: LogSource;
  lines: string[];
  error?: string | null;
}

export interface Job {
  id: string;
  name: string;
  status: "queued" | "running" | "succeeded" | "failed";
  started_at: string;
  finished_at?: string | null;
  exit_code?: number | null;
  output?: string[];
}

export interface JobsResponse {
  ok: boolean;
  jobs: Job[];
}

export interface WatcherStatus {
  scope: Scope;
  running: boolean;
  pid?: number;
  started_at?: string;
  uptime_seconds?: number;
  watched_folder?: string;
  last_event?: string | null;
  output?: string[];
  error?: string | null;
}

export interface WatchersResponse {
  ok: boolean;
  watchers: Record<Scope, WatcherStatus>;
}

export interface UploadResponse {
  ok: boolean;
  scope: Scope;
  files?: Array<{ filename: string; path: string; size_bytes: number }>;
  uploaded?: Array<{ filename: string; path: string; size_bytes: number }>;
}

export interface HistoryPoint {
  time: string;
  cpu: number;
  ram: number;
  disk: number;
  llamaLatency: number;
  tokenSpeed: number;
  engineeringFiles: number;
  codeFiles: number;
}
