import {
  FormEvent,
  ButtonHTMLAttributes,
  ReactElement,
  ReactNode,
  RefObject,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { dashboardApi } from "./lib/api";
import type {
  AuthStatus,
  DashboardStatus,
  DashboardSettingsResponse,
  HistoryPoint,
  Job,
  LogSource,
  LogsResponse,
  MemoryFile,
  QdrantCollectionsResponse,
  Scope,
  TabId,
  WatcherStatus,
} from "./types";

const tabs: Array<{ id: TabId; label: string; title: string; subtitle: string }> = [
  { id: "overview", label: "Overview", title: "Overview", subtitle: "Service health, storage, and system load." },
  { id: "logs", label: "Logs", title: "Logs", subtitle: "Proxy logs plus dashboard job and watcher output." },
  { id: "files", label: "Files", title: "File Browser", subtitle: "Browse memory files and code repository folders." },
  { id: "upload", label: "Upload", title: "Upload", subtitle: "Add files to engineering or code memory." },
  { id: "repos", label: "Repositories", title: "Repositories", subtitle: "Clone, update, and browse code repositories." },
  { id: "indexing", label: "Indexing", title: "Indexing", subtitle: "Run full or targeted indexing jobs." },
  { id: "watchers", label: "Watchers", title: "Watchers", subtitle: "Start and stop automatic reindex watchers." },
  { id: "qdrant", label: "Qdrant", title: "Qdrant", subtitle: "Inspect collections and reset vector data." },
  { id: "settings", label: "Settings", title: "Settings", subtitle: "Review non-secret runtime configuration." },
];

const logSources: Array<{ value: LogSource; label: string }> = [
  { value: "dashboard", label: "Dashboard jobs" },
  { value: "watchers", label: "Watchers" },
  { value: "memory", label: "Memory proxy" },
  { value: "code", label: "Code proxy" },
  { value: "agentic-rag", label: "Agentic RAG" },
];

function formatBytes(value?: number | null) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function formatTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function statusTone(ok?: boolean, warning?: boolean) {
  if (ok) return "bg-emerald-50 text-good ring-emerald-200";
  if (warning) return "bg-amber-50 text-warn ring-amber-200";
  return "bg-rose-50 text-bad ring-rose-200";
}

function StatusBadge({ ok, warning = false, label }: { ok?: boolean; warning?: boolean; label?: string }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-bold ring-1 ${statusTone(ok, warning)}`}>
      {label ?? (ok ? "OK" : warning ? "WARN" : "FAIL")}
    </span>
  );
}

function Panel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`rounded-xl border border-line bg-panel p-5 shadow-soft ${className}`}>{children}</section>;
}

function Button({
  children,
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const styles = {
    primary: "bg-ocean text-white hover:bg-blue-700",
    secondary: "border border-line bg-white text-ink hover:bg-slate-50",
    danger: "bg-bad text-white hover:bg-red-700",
  };
  return (
    <button
      {...props}
      className={`rounded-lg px-3.5 py-2 text-sm font-bold transition disabled:cursor-not-allowed disabled:opacity-50 ${styles[variant]} ${props.className ?? ""}`}
    >
      {children}
    </button>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="grid gap-2 text-sm font-bold text-ink">
      <span>{label}</span>
      {children}
    </label>
  );
}

function App() {
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [authError, setAuthError] = useState("");
  const [activeTab, setActiveTab] = useState<TabId>("overview");
  const [status, setStatus] = useState<DashboardStatus | null>(null);
  const [history, setHistory] = useState<HistoryPoint[]>([]);
  const [lastUpdated, setLastUpdated] = useState<string>("Waiting for data");
  const [notice, setNotice] = useState<{ message: string; type: "info" | "bad" } | null>(null);
  const [logSource, setLogSource] = useState<LogSource>("dashboard");
  const [logs, setLogs] = useState<LogsResponse | null>(null);
  const [logCapture, setLogCapture] = useState(true);
  const [fileScope, setFileScope] = useState<Scope>("engineering");
  const [files, setFiles] = useState<MemoryFile[]>([]);
  const [filePath, setFilePath] = useState("");
  const [fileFilter, setFileFilter] = useState("");
  const [repoPath, setRepoPath] = useState("");
  const [repoEntries, setRepoEntries] = useState<MemoryFile[]>([]);
  const [repoFilter, setRepoFilter] = useState("");
  const [jobs, setJobs] = useState<Job[]>([]);
  const [watchers, setWatchers] = useState<Record<Scope, WatcherStatus> | null>(null);
  const [settings, setSettings] = useState<DashboardSettingsResponse | null>(null);
  const [qdrant, setQdrant] = useState<QdrantCollectionsResponse | null>(null);
  const [uploadResult, setUploadResult] = useState<string>("");
  const [cloneResult, setCloneResult] = useState<string>("");
  const [busy, setBusy] = useState<string | null>(null);
  const logRef = useRef<HTMLPreElement | null>(null);

  const currentTab = tabs.find((tab) => tab.id === activeTab) ?? tabs[0];
  const dashboardUnlocked = Boolean(auth && (!auth.required || auth.authenticated));

  function showNotice(message: string, type: "info" | "bad" = "info") {
    setNotice({ message, type });
    window.setTimeout(() => setNotice(null), 4500);
  }

  function markUpdated() {
    setLastUpdated(`Updated ${new Date().toLocaleTimeString()}`);
  }

  async function run<T>(key: string, action: () => Promise<T>, success?: string) {
    setBusy(key);
    try {
      const result = await action();
      if (success) showNotice(success);
      return result;
    } catch (error) {
      showNotice(error instanceof Error ? error.message : String(error), "bad");
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function loadDashboardData() {
    await Promise.all([refreshStatus(), refreshLogs(), refreshFiles(), refreshRepoEntries(), refreshJobs(), refreshWatchers()]);
  }

  async function refreshAuthStatus() {
    const data = await dashboardApi.authStatus();
    setAuth(data);
    return data;
  }

  async function login(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAuthError("");
    const data = new FormData(event.currentTarget);
    const username = String(data.get("username") || "");
    const password = String(data.get("password") || "");
    const result = await run("login", () => dashboardApi.login({ username, password }));
    if (result?.authenticated) {
      setAuth(result);
      await run("initial", loadDashboardData);
    } else if (result) {
      setAuthError("Login did not unlock the dashboard.");
    }
  }

  async function logout() {
    const result = await run("logout", () => dashboardApi.logout());
    if (result) {
      setAuth(result);
      setStatus(null);
      setLogs(null);
      setFiles([]);
      setRepoEntries([]);
      setJobs([]);
      setWatchers(null);
    }
  }

  async function refreshStatus() {
    const data = await dashboardApi.status();
    setStatus(data);
    setLogCapture(Boolean(data.log_capture?.enabled));
    setHistory((items) => {
      const point: HistoryPoint = {
        time: new Date().toLocaleTimeString(),
        cpu: data.system.cpu?.usage_percent ?? 0,
        ram: data.system.ram?.usage_percent ?? 0,
        disk: data.system.disk?.usage_percent ?? 0,
        llamaLatency: data.llama.latency_ms ?? 0,
        tokenSpeed: data.llama.approximate_token_speed?.tokens_per_second ?? 0,
        engineeringFiles: data.memories.engineering.file_count,
        codeFiles: data.memories.code.file_count,
      };
      return [...items, point].slice(-30);
    });
    markUpdated();
  }

  async function refreshLogs() {
    const data = await dashboardApi.logs(logSource);
    setLogs(data);
    markUpdated();
  }

  async function refreshFiles(scope = fileScope, path = filePath) {
    const data = await dashboardApi.files(scope, path);
    setFiles(data.entries || data.files || []);
    setFilePath(data.path || "");
    markUpdated();
  }

  async function refreshRepoEntries(path = repoPath) {
    const data = await dashboardApi.files("code", path);
    setRepoEntries(data.entries || data.files || []);
    setRepoPath(data.path || "");
    markUpdated();
  }

  async function refreshJobs() {
    const data = await dashboardApi.jobs();
    setJobs(data.jobs || []);
    markUpdated();
  }

  async function refreshWatchers() {
    const data = await dashboardApi.watchers();
    setWatchers(data.watchers);
    markUpdated();
  }

  async function refreshSettings() {
    const data = await dashboardApi.settings();
    setSettings(data);
    markUpdated();
  }

  async function refreshQdrant() {
    const data = await dashboardApi.qdrantCollections();
    setQdrant(data);
    markUpdated();
  }

  async function refreshCurrentTab(tab = activeTab) {
    if (tab === "overview") await refreshStatus();
    if (tab === "logs") await refreshLogs();
    if (tab === "files") await refreshFiles();
    if (tab === "upload") await refreshLogs();
    if (tab === "repos") await Promise.all([refreshJobs(), refreshRepoEntries()]);
    if (tab === "indexing") await refreshJobs();
    if (tab === "watchers") await refreshWatchers();
    if (tab === "qdrant") await refreshQdrant();
    if (tab === "settings") await refreshSettings();
  }

  useEffect(() => {
    void run("initial", async () => {
      const authStatus = await refreshAuthStatus();
      if (!authStatus.required || authStatus.authenticated) {
        await loadDashboardData();
      }
    });
  }, []);

  useEffect(() => {
    if (!dashboardUnlocked) return;
    const poller = window.setInterval(() => {
      if (document.hidden) return;
      void run("poll", () => refreshCurrentTab(), undefined);
    }, 2000);
    return () => window.clearInterval(poller);
  }, [activeTab, logSource, fileScope, dashboardUnlocked]);

  useEffect(() => {
    const output = logRef.current;
    if (!output) return;
    output.scrollTop = output.scrollHeight;
  }, [logs]);

  const filteredFiles = useMemo(
    () => files.filter((file) => file.path.toLowerCase().includes(fileFilter.toLowerCase())),
    [files, fileFilter],
  );

  const filteredRepoEntries = useMemo(
    () => repoEntries.filter((entry) => entry.path.toLowerCase().includes(repoFilter.toLowerCase())),
    [repoEntries, repoFilter],
  );

  if (!auth) {
    return (
      <div className="grid min-h-screen place-items-center bg-[#eef4f8] px-4 text-ink">
        <Panel className="w-full max-w-md">
          <div className="flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-ocean text-sm font-black text-white">AI</div>
            <div>
              <h1 className="text-lg font-black">AI Stack</h1>
              <p className="text-sm text-muted">Loading dashboard</p>
            </div>
          </div>
        </Panel>
      </div>
    );
  }

  if (auth.required && !auth.authenticated) {
    return (
      <LoginScreen
        configured={auth.configured}
        error={authError || notice?.message || ""}
        busy={busy === "login"}
        onSubmit={login}
      />
    );
  }

  async function changeLogCapture(enabled: boolean) {
    setLogCapture(enabled);
    await run("log-capture", () => dashboardApi.setLogCapture(enabled), `Temporary log capture ${enabled ? "enabled" : "disabled"}.`);
  }

  async function deleteEntry(scope: Scope, entry: MemoryFile, afterDelete: () => Promise<void>) {
    const isDirectory = entry.kind === "directory";
    const kind = isDirectory ? "folder and everything inside it" : "file";
    const confirmed = window.confirm(`Delete ${kind} ${entry.path} from ${scope} memory?`);
    if (!confirmed) return;
    await run("delete-file", async () => {
      await dashboardApi.deleteFile(scope, entry.path);
      await afterDelete();
      await refreshStatus();
      await refreshLogs();
    }, `${entry.kind === "directory" ? "Directory" : "File"} deleted.`);
  }

  async function uploadFiles(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const input = form.elements.namedItem("files") as HTMLInputElement;
    const scope = (form.elements.namedItem("scope") as HTMLSelectElement).value as Scope;
    if (!input.files || input.files.length === 0) {
      showNotice("Choose at least one file to upload.", "bad");
      return;
    }
    await run("upload", async () => {
      const data = await dashboardApi.upload(scope, input.files as FileList);
      setUploadResult(JSON.stringify(data, null, 2));
      setFileScope(scope);
      await refreshFiles(scope, "");
      await refreshStatus();
      await refreshLogs();
      form.reset();
    }, "Upload complete.");
  }

  async function cloneRepo(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const payload = {
      repo_url: String(data.get("repo_url") || ""),
      repo_name: String(data.get("repo_name") || "") || undefined,
      token: String(data.get("token") || "") || undefined,
      update_existing: data.get("update_existing") === "on",
    };
    await run("clone", async () => {
      const result = await dashboardApi.cloneRepo(payload);
      setCloneResult(JSON.stringify(result, null, 2));
      form.reset();
      await Promise.all([refreshJobs(), refreshRepoEntries()]);
      await refreshLogs();
    }, "Repository job started.");
  }

  async function startIndex(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload = {
      scope: String(data.get("scope")) as Scope,
      target: String(data.get("target") || "") || undefined,
    };
    await run("index", async () => {
      await dashboardApi.startIndex(payload);
      await refreshJobs();
      await refreshLogs();
    }, "Indexing job started.");
  }

  async function watcherAction(scope: Scope, action: "start" | "stop") {
    await run(`${scope}-${action}`, async () => {
      await dashboardApi.watcherAction(scope, action);
      await refreshWatchers();
      await refreshLogs();
    }, `${scope} watcher ${action === "start" ? "started" : "stopped"}.`);
  }

  async function resetQdrant(target: "memory" | "code" | "demo") {
    const confirmation = window.prompt(`Type "reset ${target}" to reset ${target} vectors.`);
    if (!confirmation) return;
    let warnings: string[] = [];
    const result = await run(`qdrant-${target}`, async () => {
      const response = await dashboardApi.qdrantReset(target, confirmation);
      warnings = response.warnings || [];
      await refreshQdrant();
      await refreshStatus();
      return response;
    });
    if (result) {
      showNotice(warnings.length ? `Qdrant ${target} reset complete with warnings: ${warnings.join("; ")}` : `Qdrant ${target} reset complete.`);
    }
  }

  return (
    <div className="min-h-screen bg-[#eef4f8] text-ink">
      <div className="grid min-h-screen lg:grid-cols-[280px_1fr]">
        <aside className="border-r border-line bg-white px-5 py-6">
          <div className="mb-8 flex items-center gap-3">
            <div className="grid h-11 w-11 place-items-center rounded-xl bg-ocean text-sm font-black text-white">AI</div>
            <div>
              <h1 className="text-lg font-black">AI Stack</h1>
              <p className="text-sm text-muted">Local RAG control</p>
            </div>
          </div>

          <nav className="grid gap-2" aria-label="Dashboard sections">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => {
                  setActiveTab(tab.id);
                  void run("tab", () => refreshCurrentTab(tab.id));
                }}
                className={`rounded-lg px-3 py-2 text-left text-sm font-bold transition ${
                  activeTab === tab.id ? "bg-ocean text-white shadow-soft" : "text-slate-700 hover:bg-slate-100"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </nav>
        </aside>

        <main className="min-w-0 px-4 py-5 sm:px-6 lg:px-8">
          <header className="mb-5 flex flex-col gap-4 rounded-xl border border-line bg-white p-5 shadow-soft md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-2xl font-black tracking-normal">{currentTab.title}</h2>
              <p className="mt-1 text-sm text-muted">{currentTab.subtitle}</p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <span className="inline-flex items-center gap-2 rounded-full bg-emerald-50 px-3 py-1.5 text-sm font-bold text-good ring-1 ring-emerald-200">
                <span className="h-2 w-2 rounded-full bg-good" />
                Live
              </span>
              <span className="text-sm text-muted">{lastUpdated}</span>
              {auth.required && auth.username && <span className="text-sm font-bold text-muted">{auth.username}</span>}
              {auth.required && (
                <Button variant="secondary" disabled={busy === "logout"} onClick={() => void logout()}>
                  Logout
                </Button>
              )}
              <Button variant="secondary" disabled={busy === "tab"} onClick={() => void run("refresh", () => refreshCurrentTab())}>
                Refresh
              </Button>
            </div>
          </header>

          {notice && (
            <div className={`mb-5 rounded-lg px-4 py-3 text-sm font-bold ${notice.type === "bad" ? "bg-rose-50 text-bad" : "bg-blue-50 text-ocean"}`}>
              {notice.message}
            </div>
          )}

          {activeTab === "overview" && <Overview status={status} history={history} refresh={() => run("status", refreshStatus)} />}
          {activeTab === "logs" && (
            <LogsTab
              source={logSource}
              setSource={setLogSource}
              logs={logs}
              logRef={logRef}
              logCapture={logCapture}
              setLogCapture={changeLogCapture}
              refresh={() => run("logs", refreshLogs)}
            />
          )}
          {activeTab === "files" && (
            <FilesTab
              scope={fileScope}
              setScope={(scope) => {
                setFileScope(scope);
                setFilePath("");
                void run("files", () => refreshFiles(scope, ""));
              }}
              files={filteredFiles}
              path={filePath}
              setPath={(path) => void run("files", () => refreshFiles(fileScope, path))}
              filter={fileFilter}
              setFilter={setFileFilter}
              refresh={() => run("files", () => refreshFiles())}
              deleteEntry={(entry) => deleteEntry(fileScope, entry, () => refreshFiles(fileScope, filePath))}
            />
          )}
          {activeTab === "upload" && <UploadTab onSubmit={uploadFiles} result={uploadResult} busy={busy === "upload"} />}
          {activeTab === "repos" && (
            <RepositoriesTab
              onSubmit={cloneRepo}
              result={cloneResult}
              busy={busy === "clone"}
              entries={filteredRepoEntries}
              path={repoPath}
              setPath={(path) => void run("repo-files", () => refreshRepoEntries(path))}
              filter={repoFilter}
              setFilter={setRepoFilter}
              refresh={() => run("repo-files", () => refreshRepoEntries())}
              deleteEntry={(entry) => deleteEntry("code", entry, () => refreshRepoEntries(repoPath))}
            />
          )}
          {activeTab === "indexing" && <IndexingTab onSubmit={startIndex} jobs={jobs} refresh={() => run("jobs", refreshJobs)} busy={busy === "index"} />}
          {activeTab === "watchers" && <WatchersTab watchers={watchers} action={watcherAction} />}
          {activeTab === "qdrant" && <QdrantTab qdrant={qdrant} refresh={() => run("qdrant", refreshQdrant)} reset={resetQdrant} />}
          {activeTab === "settings" && <SettingsTab settings={settings} refresh={() => run("settings", refreshSettings)} />}
        </main>
      </div>
    </div>
  );
}

function LoginScreen({
  configured,
  error,
  busy,
  onSubmit,
}: {
  configured: boolean;
  error: string;
  busy: boolean;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
}) {
  return (
    <div className="grid min-h-screen place-items-center bg-[#eef4f8] px-4 text-ink">
      <Panel className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-ocean text-sm font-black text-white">AI</div>
          <div>
            <h1 className="text-lg font-black">AI Stack</h1>
            <p className="text-sm text-muted">Dashboard login</p>
          </div>
        </div>
        {!configured ? (
          <div className="rounded-lg bg-rose-50 px-4 py-3 text-sm font-bold text-bad">
            Dashboard authentication is required but not configured.
          </div>
        ) : (
          <form className="grid gap-4" onSubmit={onSubmit}>
            <Field label="Username">
              <input name="username" type="text" autoComplete="username" required className="control" />
            </Field>
            <Field label="Password">
              <input name="password" type="password" autoComplete="current-password" required className="control" />
            </Field>
            {error && <div className="rounded-lg bg-rose-50 px-4 py-3 text-sm font-bold text-bad">{error}</div>}
            <Button disabled={busy} type="submit">
              Login
            </Button>
          </form>
        )}
      </Panel>
    </div>
  );
}

function Overview({ status, history, refresh }: { status: DashboardStatus | null; history: HistoryPoint[]; refresh: () => void }) {
  const speed = status?.llama.approximate_token_speed?.tokens_per_second;
  const cards = [
    {
      title: "Llama",
      ok: status?.llama.ok,
      rows: [
        ["Latency", `${status?.llama.latency_ms ?? "-"} ms`],
        ["Token speed", `${speed ?? "-"} tok/s`],
        ["Model", status?.llama.model ?? "-"],
      ],
    },
    {
      title: "Qdrant",
      ok: status?.qdrant.ok,
      rows: [
        ["Latency", `${status?.qdrant.latency_ms ?? "-"} ms`],
        ["Endpoint", status?.qdrant.url ?? "-"],
      ],
    },
    {
      title: "Engineering Memory",
      ok: status?.memories.engineering.ok,
      rows: [
        ["Files", status?.memories.engineering.file_count ?? "-"],
        ["Latest", formatTime(status?.memories.engineering.latest_modified_time)],
      ],
    },
    {
      title: "Code Memory",
      ok: status?.memories.code.ok,
      rows: [
        ["Files", status?.memories.code.file_count ?? "-"],
        ["Latest", formatTime(status?.memories.code.latest_modified_time)],
      ],
    },
    {
      title: "System",
      ok: status?.system.ok,
      rows: [
        ["CPU", `${status?.system.cpu?.usage_percent ?? "-"}%`],
        ["RAM", `${status?.system.ram?.usage_percent ?? "-"}%`],
        ["Disk", `${status?.system.disk?.usage_percent ?? "-"}%`],
      ],
    },
    {
      title: "Logs",
      ok: Boolean(status?.logs.memory.ok && status?.logs.code.ok && status?.logs["agentic-rag"]?.ok),
      warning: true,
      rows: [
        ["Memory log", formatLogState(status?.logs.memory.state)],
        ["Code log", formatLogState(status?.logs.code.state)],
        ["Agentic RAG", formatLogState(status?.logs["agentic-rag"]?.state)],
      ],
    },
  ];

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <Button onClick={refresh}>Refresh</Button>
        <span className="text-sm text-muted">Live charts use browser-local rolling history.</span>
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {cards.map((card) => (
          <Panel key={card.title}>
            <div className="mb-4 flex items-center justify-between gap-3">
              <h3 className="text-base font-black">{card.title}</h3>
              <StatusBadge ok={card.ok} warning={card.warning} />
            </div>
            <div className="grid gap-3 text-sm">
              {card.rows.map(([label, value]) => (
                <div key={String(label)} className="grid grid-cols-[110px_1fr] gap-3">
                  <span className="text-muted">{label}</span>
                  <span className="min-w-0 break-words font-bold">{value}</span>
                </div>
              ))}
            </div>
          </Panel>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <ChartPanel title="System Usage">
          <AreaChart data={history}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" hide />
            <YAxis width={34} domain={[0, 100]} />
            <Tooltip />
            <Area type="monotone" dataKey="cpu" name="CPU %" stroke="#2563eb" fill="#bfdbfe" />
            <Area type="monotone" dataKey="ram" name="RAM %" stroke="#138a54" fill="#bbf7d0" />
            <Area type="monotone" dataKey="disk" name="Disk %" stroke="#b7791f" fill="#fde68a" />
          </AreaChart>
        </ChartPanel>
        <ChartPanel title="Llama">
          <AreaChart data={history}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" hide />
            <YAxis width={42} />
            <Tooltip />
            <Area type="monotone" dataKey="llamaLatency" name="Latency ms" stroke="#7c3aed" fill="#ddd6fe" />
            <Area type="monotone" dataKey="tokenSpeed" name="tok/s" stroke="#0f766e" fill="#99f6e4" />
          </AreaChart>
        </ChartPanel>
        <ChartPanel title="Memory Files">
          <BarChart data={history.slice(-1)}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="time" hide />
            <YAxis width={42} />
            <Tooltip />
            <Bar dataKey="engineeringFiles" name="Engineering" fill="#2563eb" radius={[6, 6, 0, 0]} />
            <Bar dataKey="codeFiles" name="Code" fill="#138a54" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ChartPanel>
      </div>
    </div>
  );
}

function ChartPanel({ title, children }: { title: string; children: ReactElement }) {
  return (
    <Panel>
      <h3 className="mb-4 text-base font-black">{title}</h3>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          {children}
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

function LogsTab({
  source,
  setSource,
  logs,
  logRef,
  logCapture,
  setLogCapture,
  refresh,
}: {
  source: LogSource;
  setSource: (source: LogSource) => void;
  logs: LogsResponse | null;
  logRef: RefObject<HTMLPreElement | null>;
  logCapture: boolean;
  setLogCapture: (enabled: boolean) => void;
  refresh: () => void;
}) {
  return (
    <Panel>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <select value={source} onChange={(event) => setSource(event.target.value as LogSource)} className="control">
          {logSources.map((item) => (
            <option key={item.value} value={item.value}>
              {item.label}
            </option>
          ))}
        </select>
        <Button onClick={refresh}>Refresh</Button>
        <label className="flex items-center gap-2 text-sm font-bold">
          <input type="checkbox" checked={logCapture} onChange={(event) => setLogCapture(event.target.checked)} />
          Temporary log capture
        </label>
        <span className="text-sm text-muted">Auto-refreshes every 2 seconds.</span>
      </div>
      <pre ref={logRef} className="log-box">
        {(logs?.lines || []).join("\n") || logs?.error || logs?.message || logEmptyMessage(logs)}
      </pre>
    </Panel>
  );
}

function formatLogState(state?: LogsResponse["state"]): string {
  if (state === "available") return "available";
  if (state === "disabled") return "logging disabled";
  if (state === "empty") return "no events yet";
  if (state === "unavailable") return "log unavailable";
  return "unknown";
}

function logEmptyMessage(logs: LogsResponse | null): string {
  if (!logs) return "Loading logs…";
  if (logs.state === "disabled") return "Logging is disabled for this source.";
  if (logs.state === "empty") return "No events have been logged yet.";
  if (logs.state === "unavailable") return "The configured log file is unavailable.";
  return "";
}

function parentPath(path: string) {
  const parts = path.split("/").filter(Boolean);
  parts.pop();
  return parts.join("/");
}

function Breadcrumbs({ path, setPath }: { path: string; setPath: (path: string) => void }) {
  const parts = path.split("/").filter(Boolean);
  let current = "";
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <button type="button" onClick={() => setPath("")} className="font-bold text-ocean hover:underline">
        Root
      </button>
      {parts.map((part) => {
        current = current ? `${current}/${part}` : part;
        const target = current;
        return (
          <span key={target} className="inline-flex items-center gap-2">
            <span className="text-muted">/</span>
            <button type="button" onClick={() => setPath(target)} className="font-bold text-ocean hover:underline">
              {part}
            </button>
          </span>
        );
      })}
    </div>
  );
}

function DirectoryTable({
  entries,
  path,
  setPath,
  deleteEntry,
}: {
  entries: MemoryFile[];
  path: string;
  setPath: (path: string) => void;
  deleteEntry: (entry: MemoryFile) => void;
}) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="min-w-full divide-y divide-line text-sm">
        <thead className="bg-slate-50 text-left text-xs uppercase text-muted">
          <tr>
            <th className="px-4 py-3">Name</th>
            <th className="px-4 py-3">Type</th>
            <th className="px-4 py-3">Size</th>
            <th className="px-4 py-3">Modified</th>
            <th className="px-4 py-3">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line bg-white">
          {path && (
            <tr>
              <td className="max-w-[520px] break-words px-4 py-3 font-mono text-xs">
                <button type="button" className="font-bold text-ocean hover:underline" onClick={() => setPath(parentPath(path))}>
                  ../
                </button>
              </td>
              <td className="px-4 py-3">parent</td>
              <td className="px-4 py-3">-</td>
              <td className="px-4 py-3">-</td>
              <td className="px-4 py-3">-</td>
            </tr>
          )}
          {entries.length === 0 ? (
            <tr>
              <td className="px-4 py-8 text-center text-muted" colSpan={5}>
                No entries found.
              </td>
            </tr>
          ) : (
            entries.map((entry) => {
              const isDirectory = entry.kind === "directory";
              return (
                <tr key={entry.path}>
                  <td className="max-w-[520px] break-words px-4 py-3 font-mono text-xs">
                    {isDirectory ? (
                      <button type="button" onClick={() => setPath(entry.path)} className="font-bold text-ocean hover:underline">
                        {entry.name || entry.path}/
                      </button>
                    ) : (
                      entry.name || entry.path
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {isDirectory ? `directory (${entry.child_count ?? 0})` : entry.extension || "file"}
                  </td>
                  <td className="px-4 py-3">{isDirectory ? "-" : formatBytes(entry.size_bytes)}</td>
                  <td className="px-4 py-3">{formatTime(entry.modified_time)}</td>
                  <td className="px-4 py-3">
                    <Button variant="danger" onClick={() => deleteEntry(entry)}>
                      Delete
                    </Button>
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

function FilesTab({
  scope,
  setScope,
  files,
  path,
  setPath,
  filter,
  setFilter,
  refresh,
  deleteEntry,
}: {
  scope: Scope;
  setScope: (scope: Scope) => void;
  files: MemoryFile[];
  path: string;
  setPath: (path: string) => void;
  filter: string;
  setFilter: (filter: string) => void;
  refresh: () => void;
  deleteEntry: (entry: MemoryFile) => void;
}) {
  return (
    <Panel>
      <div className="mb-4 grid gap-3">
        <div className="flex flex-wrap items-center gap-3">
          <select value={scope} onChange={(event) => setScope(event.target.value as Scope)} className="control max-w-xs">
            <option value="engineering">Engineering memory</option>
            <option value="code">Code repositories</option>
          </select>
          <input value={filter} onChange={(event) => setFilter(event.target.value)} className="control min-w-[220px] max-w-sm" type="search" placeholder="Filter current directory" />
          <Button onClick={refresh}>Refresh</Button>
        </div>
        <Breadcrumbs path={path} setPath={setPath} />
      </div>
      <DirectoryTable entries={files} path={path} setPath={setPath} deleteEntry={deleteEntry} />
    </Panel>
  );
}

function UploadTab({ onSubmit, result, busy }: { onSubmit: (event: FormEvent<HTMLFormElement>) => void; result: string; busy: boolean }) {
  return (
    <div className="grid gap-5 xl:grid-cols-[460px_1fr]">
      <Panel>
        <form className="grid gap-4" onSubmit={onSubmit}>
          <Field label="Destination">
            <select name="scope" className="control">
              <option value="engineering">Engineering memory</option>
              <option value="code">Code memory</option>
            </select>
          </Field>
          <Field label="Files">
            <input name="files" type="file" multiple className="control" />
          </Field>
          <Button disabled={busy} type="submit">Upload</Button>
        </form>
      </Panel>
      <pre className="result-box">{result}</pre>
    </div>
  );
}

function RepositoriesTab({
  onSubmit,
  result,
  busy,
  entries,
  path,
  setPath,
  filter,
  setFilter,
  refresh,
  deleteEntry,
}: {
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  result: string;
  busy: boolean;
  entries: MemoryFile[];
  path: string;
  setPath: (path: string) => void;
  filter: string;
  setFilter: (filter: string) => void;
  refresh: () => void;
  deleteEntry: (entry: MemoryFile) => void;
}) {
  return (
    <div className="grid gap-5">
      <Panel>
        <form className="grid gap-4" onSubmit={onSubmit}>
          <Field label="Repository HTTPS URL">
            <input name="repo_url" type="url" required placeholder="https://github.com/user/repo.git" className="control" />
          </Field>
          <Field label="Folder name">
            <input name="repo_name" type="text" placeholder="optional" className="control" />
          </Field>
          <Field label="One-time token">
            <input name="token" type="password" placeholder="only for private repos" autoComplete="off" className="control" />
          </Field>
          <label className="flex items-center gap-2 text-sm font-bold">
            <input name="update_existing" type="checkbox" />
            Update existing repo with git pull
          </label>
          <Button disabled={busy} type="submit">Clone or Update</Button>
        </form>
      </Panel>
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
        <Panel>
          <div className="mb-4 grid gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <input value={filter} onChange={(event) => setFilter(event.target.value)} className="control min-w-[220px] max-w-sm" type="search" placeholder="Filter repository directory" />
              <Button onClick={refresh}>Refresh repository view</Button>
            </div>
            <Breadcrumbs path={path} setPath={setPath} />
          </div>
          <DirectoryTable entries={entries} path={path} setPath={setPath} deleteEntry={deleteEntry} />
        </Panel>
        <pre className="result-box">{result}</pre>
      </div>
    </div>
  );
}

function IndexingTab({
  onSubmit,
  jobs,
  refresh,
  busy,
}: {
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  jobs: Job[];
  refresh: () => void;
  busy: boolean;
}) {
  return (
    <div className="grid gap-5">
      <Panel>
        <form className="grid gap-4 md:grid-cols-[220px_1fr_auto]" onSubmit={onSubmit}>
          <Field label="Scope">
            <select name="scope" className="control">
              <option value="engineering">Engineering memory</option>
              <option value="code">Code memory</option>
            </select>
          </Field>
          <Field label="Target path">
            <input name="target" type="text" placeholder="blank = full scope" className="control" />
          </Field>
          <div className="flex items-end">
            <Button disabled={busy} type="submit">Start Indexing</Button>
          </div>
        </form>
      </Panel>
      <div className="flex items-center gap-3">
        <Button onClick={refresh}>Refresh jobs</Button>
        <span className="text-sm text-muted">Running jobs update automatically.</span>
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        {jobs.length === 0 ? (
          <Panel>
            <p className="text-sm text-muted">No jobs yet.</p>
          </Panel>
        ) : (
          jobs.map((job) => <JobCard key={job.id} job={job} />)
        )}
      </div>
    </div>
  );
}

function JobCard({ job }: { job: Job }) {
  return (
    <Panel>
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <h3 className="font-black">{job.name}</h3>
          <p className="text-xs text-muted">{job.id}</p>
        </div>
        <StatusBadge ok={job.status === "succeeded"} warning={job.status === "running" || job.status === "queued"} label={job.status.toUpperCase()} />
      </div>
      <div className="mb-3 grid gap-2 text-sm sm:grid-cols-3">
        <span>Started: <b>{formatTime(job.started_at)}</b></span>
        <span>Finished: <b>{formatTime(job.finished_at)}</b></span>
        <span>Exit: <b>{job.exit_code ?? "-"}</b></span>
      </div>
      <pre className="result-box max-h-64">{(job.output || []).join("\n")}</pre>
    </Panel>
  );
}

function WatchersTab({
  watchers,
  action,
}: {
  watchers: Record<Scope, WatcherStatus> | null;
  action: (scope: Scope, action: "start" | "stop") => void;
}) {
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      {(["engineering", "code"] as Scope[]).map((scope) => {
        const watcher = watchers?.[scope] ?? { scope, running: false };
        return (
          <Panel key={scope}>
            <div className="mb-4 flex items-center justify-between gap-3">
              <h3 className="text-lg font-black capitalize">{scope} watcher</h3>
              <StatusBadge ok={watcher.running} warning={!watcher.running} label={watcher.running ? "RUNNING" : "STOPPED"} />
            </div>
            <div className="mb-4 flex gap-3">
              <Button onClick={() => action(scope, "start")}>Start</Button>
              <Button variant="secondary" onClick={() => action(scope, "stop")}>Stop</Button>
            </div>
            <pre className="result-box">{JSON.stringify(watcher, null, 2)}</pre>
          </Panel>
        );
      })}
    </div>
  );
}

function QdrantTab({
  qdrant,
  refresh,
  reset,
}: {
  qdrant: QdrantCollectionsResponse | null;
  refresh: () => void;
  reset: (target: "memory" | "code" | "demo") => void;
}) {
  return (
    <div className="grid gap-5">
      <Panel>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <Button onClick={refresh}>Refresh collections</Button>
          <Button variant="secondary" onClick={() => reset("demo")}>Reset demo vectors</Button>
          <Button variant="danger" onClick={() => reset("memory")}>Reset memory collection</Button>
          <Button variant="danger" onClick={() => reset("code")}>Reset code collection</Button>
        </div>
        {qdrant?.error && <div className="mb-4 rounded-lg bg-rose-50 px-4 py-3 text-sm font-bold text-bad">{qdrant.error}</div>}
        <div className="overflow-x-auto rounded-lg border border-line">
          <table className="min-w-full divide-y divide-line text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-muted">
              <tr>
                <th className="px-4 py-3">Collection</th>
                <th className="px-4 py-3">Points</th>
                <th className="px-4 py-3">Vectors</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line bg-white">
              {(qdrant?.collections || []).length === 0 ? (
                <tr>
                  <td className="px-4 py-8 text-center text-muted" colSpan={4}>No collections found.</td>
                </tr>
              ) : (
                (qdrant?.collections || []).map((collection) => (
                  <tr key={collection.name}>
                    <td className="px-4 py-3 font-mono text-xs">{collection.name}</td>
                    <td className="px-4 py-3">{collection.points_count ?? "-"}</td>
                    <td className="px-4 py-3">{collection.vectors_count ?? "-"}</td>
                    <td className="px-4 py-3">{collection.error || collection.status || "-"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}

function SettingsTab({ settings, refresh }: { settings: DashboardSettingsResponse | null; refresh: () => void }) {
  const rows = Object.entries(settings?.settings || {}).filter(([, value]) => value !== "");
  const paths = Object.entries(settings?.paths || {});
  return (
    <div className="grid gap-5 xl:grid-cols-2">
      <Panel>
        <div className="mb-4 flex items-center justify-between gap-3">
          <h3 className="text-base font-black">Runtime Settings</h3>
          <Button onClick={refresh}>Refresh</Button>
        </div>
        <KeyValueTable rows={rows} />
      </Panel>
      <Panel>
        <h3 className="mb-4 text-base font-black">Mounted Paths</h3>
        <KeyValueTable rows={paths} />
      </Panel>
    </div>
  );
}

function KeyValueTable({ rows }: { rows: Array<[string, string]> }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="min-w-full divide-y divide-line text-sm">
        <tbody className="divide-y divide-line bg-white">
          {rows.length === 0 ? (
            <tr>
              <td className="px-4 py-8 text-center text-muted">No values loaded.</td>
            </tr>
          ) : (
            rows.map(([key, value]) => (
              <tr key={key}>
                <td className="w-56 px-4 py-3 font-mono text-xs text-muted">{key}</td>
                <td className="break-words px-4 py-3 font-bold">{value || "-"}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export default App;
