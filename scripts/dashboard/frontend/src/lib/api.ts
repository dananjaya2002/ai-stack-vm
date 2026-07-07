import type {
  AuthStatus,
  DashboardStatus,
  DashboardSettingsResponse,
  FilesResponse,
  JobsResponse,
  LogSource,
  LogsResponse,
  QdrantCollectionsResponse,
  Scope,
  UploadResponse,
  WatchersResponse,
} from "../types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { credentials: "same-origin", ...init });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const message = data.detail || data.error || `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return data as T;
}

export const dashboardApi = {
  authStatus: () => request<AuthStatus>("/api/dashboard/auth/status"),
  login: (payload: { username: string; password: string }) =>
    request<AuthStatus>("/api/dashboard/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  logout: () => request<AuthStatus>("/api/dashboard/auth/logout", { method: "POST" }),
  status: () => request<DashboardStatus>("/api/dashboard/status"),
  files: (scope: Scope, path = "") =>
    request<FilesResponse>(
      `/api/dashboard/files?scope=${encodeURIComponent(scope)}&path=${encodeURIComponent(path)}`,
    ),
  deleteFile: (scope: Scope, path: string) =>
    request<{ ok: boolean }>("/api/dashboard/files", {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scope, path }),
    }),
  logs: (source: LogSource) =>
    request<LogsResponse>(`/api/dashboard/logs?source=${encodeURIComponent(source)}`),
  setLogCapture: (enabled: boolean) =>
    request<{ ok: boolean; enabled: boolean }>("/api/dashboard/log-capture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }),
  upload: (scope: Scope, files: FileList) => {
    const body = new FormData();
    body.append("scope", scope);
    Array.from(files).forEach((file) => body.append("files", file));
    return request<UploadResponse>("/api/dashboard/upload", { method: "POST", body });
  },
  cloneRepo: (payload: { repo_url: string; repo_name?: string; token?: string; update_existing: boolean }) =>
    request<{ ok: boolean; job: unknown }>("/api/dashboard/repos/clone", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  startIndex: (payload: { scope: Scope; target?: string }) =>
    request<{ ok: boolean; job: unknown }>("/api/dashboard/index", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  jobs: () => request<JobsResponse>("/api/dashboard/jobs"),
  watchers: () => request<WatchersResponse>("/api/dashboard/watchers"),
  watcherAction: (scope: Scope, action: "start" | "stop") =>
    request<{ ok: boolean; watcher: unknown }>(`/api/dashboard/watchers/${scope}/${action}`, { method: "POST" }),
  settings: () => request<DashboardSettingsResponse>("/api/dashboard/settings"),
  qdrantCollections: () => request<QdrantCollectionsResponse>("/api/dashboard/qdrant/collections"),
  qdrantReset: (target: "memory" | "code" | "demo", confirmation: string) =>
    request<{ ok: boolean; target: string; warnings?: string[] }>("/api/dashboard/qdrant/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target, confirmation }),
    }),
};
