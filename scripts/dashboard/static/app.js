const state = {
  currentTab: "overview",
  files: [],
  poller: null,
  lastUpdatedAt: null,
};

const titles = {
  overview: ["Overview", "Service health, storage, and system load."],
  logs: ["Logs", "Proxy logs plus dashboard job and watcher output."],
  files: ["Memory Files", "Browse engineering and code memory folders."],
  upload: ["Upload", "Add files to engineering or code memory."],
  repos: ["Repositories", "Clone public or private HTTPS repositories."],
  indexing: ["Indexing", "Run full or targeted indexing jobs."],
  watchers: ["Watchers", "Start and stop automatic reindex watchers."],
};

function headers(json = true) {
  const result = {};
  if (json) result["Content-Type"] = "application/json";
  return result;
}

function showNotice(message, type = "info") {
  const notice = document.querySelector("#notice");
  notice.textContent = message;
  notice.className = `notice ${type}`;
  window.setTimeout(() => notice.classList.add("hidden"), 4500);
}

function markUpdated() {
  state.lastUpdatedAt = new Date();
  document.querySelector("#last-updated").textContent = `Updated ${state.lastUpdatedAt.toLocaleTimeString()}`;
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || data.error || `Request failed: ${response.status}`);
  }
  return data;
}

async function runAction(action, successMessage = "") {
  try {
    await action();
    if (successMessage) showNotice(successMessage);
  } catch (error) {
    showNotice(error.message, "bad");
  }
}

function formatBytes(value) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let size = Number(value);
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function badge(ok, warning = false) {
  const cls = ok ? "ok" : warning ? "warn" : "bad";
  const label = ok ? "OK" : warning ? "WARN" : "FAIL";
  return `<span class="badge ${cls}">${label}</span>`;
}

function renderStatusCard(title, ok, lines, warning = false) {
  return `
    <article class="status-card">
      <h3>${title} ${badge(ok, warning)}</h3>
      ${lines.map(([label, value]) => `<div class="metric"><span>${label}</span><span>${value}</span></div>`).join("")}
    </article>
  `;
}

async function refreshStatus() {
  const data = await api("/api/dashboard/status");
  const grid = document.querySelector("#status-grid");
  const speed = data.llama?.approximate_token_speed?.tokens_per_second;
  grid.innerHTML = [
    renderStatusCard("Llama", data.llama.ok, [
      ["Latency", `${data.llama.latency_ms ?? "-"} ms`],
      ["Token speed", `${speed ?? "-"} tok/s`],
      ["Model", data.llama.model ?? "-"],
    ]),
    renderStatusCard("Qdrant", data.qdrant.ok, [
      ["Latency", `${data.qdrant.latency_ms ?? "-"} ms`],
      ["Endpoint", data.qdrant.url ?? "-"],
    ]),
    renderStatusCard("Engineering Memory", data.memories.engineering.ok, [
      ["Files", data.memories.engineering.file_count],
      ["Latest", data.memories.engineering.latest_modified_time ?? "-"],
    ]),
    renderStatusCard("Code Memory", data.memories.code.ok, [
      ["Files", data.memories.code.file_count],
      ["Latest", data.memories.code.latest_modified_time ?? "-"],
    ]),
    renderStatusCard("System", data.system.ok, [
      ["CPU", `${data.system.cpu?.usage_percent ?? "-"}%`],
      ["RAM", `${data.system.ram?.usage_percent ?? "-"}%`],
      ["Disk", `${data.system.disk?.usage_percent ?? "-"}%`],
    ]),
    renderStatusCard("Logs", data.logs.memory.ok && data.logs.code.ok, [
      ["Memory log", data.logs.memory.exists ? "present" : "missing"],
      ["Code log", data.logs.code.exists ? "present" : "missing"],
    ], true),
  ].join("");
  document.querySelector("#log-capture").checked = Boolean(data.log_capture?.enabled);
  markUpdated();
}

async function refreshLogs() {
  const source = document.querySelector("#log-source").value;
  const data = await api(`/api/dashboard/logs?source=${encodeURIComponent(source)}`);
  const output = document.querySelector("#log-output");
  const nearBottom = output.scrollHeight - output.scrollTop - output.clientHeight < 80;
  output.textContent = (data.lines || []).join("\n") || data.error || "";
  if (nearBottom) output.scrollTop = output.scrollHeight;
  markUpdated();
}

async function setLogCapture() {
  const enabled = document.querySelector("#log-capture").checked;
  await api("/api/dashboard/log-capture", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify({ enabled }),
  });
  showNotice(`Temporary log capture ${enabled ? "enabled" : "disabled"}.`);
}

function renderFiles() {
  const filter = document.querySelector("#files-filter").value.toLowerCase();
  const rows = state.files
    .filter((file) => file.path.toLowerCase().includes(filter))
    .map((file) => `
      <tr>
        <td class="path-cell">${file.path}</td>
        <td>${file.extension || "file"}</td>
        <td>${formatBytes(file.size_bytes)}</td>
        <td>${file.modified_time}</td>
        <td>
          <button class="danger small" data-delete-file="${encodeURIComponent(file.path)}">Delete</button>
        </td>
      </tr>
    `);
  document.querySelector("#files-table").innerHTML =
    rows.join("") || `<tr><td colspan="5" class="empty-cell">No files found.</td></tr>`;
  document.querySelectorAll("[data-delete-file]").forEach((button) => {
    button.addEventListener("click", () => {
      const path = decodeURIComponent(button.dataset.deleteFile);
      runAction(() => deleteFile(path), "File deleted.");
    });
  });
}

async function refreshFiles() {
  const scope = document.querySelector("#files-scope").value;
  const data = await api(`/api/dashboard/files?scope=${scope}`);
  state.files = data.files || [];
  renderFiles();
  markUpdated();
}

async function deleteFile(path) {
  const scope = document.querySelector("#files-scope").value;
  const confirmed = window.confirm(`Delete ${path} from ${scope} memory?`);
  if (!confirmed) return;
  await api("/api/dashboard/files", {
    method: "DELETE",
    headers: headers(),
    body: JSON.stringify({ scope, path }),
  });
  await refreshFiles();
  await refreshStatus();
  await refreshLogs();
}

async function uploadFiles(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const formData = new FormData(form);
  const scope = formData.get("scope");
  if (!formData.getAll("files").some((file) => file && file.name)) {
    throw new Error("Choose at least one file to upload.");
  }
  const response = await fetch(`/api/dashboard/upload?scope=${encodeURIComponent(scope)}`, {
    method: "POST",
    body: formData,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Upload failed");
  document.querySelector("#upload-result").textContent = JSON.stringify(data, null, 2);
  document.querySelector("#files-scope").value = scope;
  await refreshFiles();
  await refreshStatus();
  form.reset();
}

async function cloneRepo(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form).entries());
  data.update_existing = form.update_existing.checked;
  if (!data.token) delete data.token;
  if (!data.repo_name) delete data.repo_name;
  const result = await api("/api/dashboard/repos/clone", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(data),
  });
  document.querySelector("#clone-result").textContent = JSON.stringify(result, null, 2);
  await refreshJobs();
}

async function startIndex(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form).entries());
  if (!data.target) delete data.target;
  const result = await api("/api/dashboard/index", {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(data),
  });
  document.querySelector("#jobs-list").prepend(jobCard(result.job));
}

function jobCard(job) {
  const article = document.createElement("article");
  article.className = "status-card";
  article.innerHTML = `
    <h3>${job.name} ${badge(job.status === "succeeded", job.status === "running")}</h3>
    <p>Status: ${job.status}</p>
    <p>Started: ${job.started_at}</p>
    <p>Exit: ${job.exit_code ?? "-"}</p>
    <pre class="result-box">${(job.output || []).join("\n")}</pre>
  `;
  return article;
}

async function refreshJobs() {
  const data = await api("/api/dashboard/jobs");
  const list = document.querySelector("#jobs-list");
  list.innerHTML = "";
  (data.jobs || []).forEach((job) => list.appendChild(jobCard(job)));
  markUpdated();
}

async function refreshWatchers() {
  const data = await api("/api/dashboard/watchers");
  for (const scope of ["engineering", "code"]) {
    const watcher = data.watchers?.[scope] || { running: false };
    const panel = document.querySelector(`#watcher-${scope}`);
    const nearBottom = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 80;
    panel.textContent = JSON.stringify(watcher, null, 2);
    if (nearBottom) panel.scrollTop = panel.scrollHeight;
  }
  markUpdated();
}

async function watcherAction(scope, action) {
  const data = await api(`/api/dashboard/watchers/${scope}/${action}`, {
    method: "POST",
    headers: headers(),
  });
  document.querySelector(`#watcher-${scope}`).textContent = JSON.stringify(data.watcher, null, 2);
}

function switchTab(tab) {
  state.currentTab = tab;
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.classList.toggle("active", button.dataset.tab === tab);
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `tab-${tab}`);
  });
  document.querySelector("#page-title").textContent = titles[tab][0];
  document.querySelector("#page-subtitle").textContent = titles[tab][1];
  runAction(refreshCurrentTab);
}

function bind() {
  document.querySelectorAll(".tab-button").forEach((button) => {
    button.addEventListener("click", () => switchTab(button.dataset.tab));
  });
  document.querySelector("#refresh-current").addEventListener("click", () => runAction(refreshCurrentTab));
  document.querySelector("#refresh-status").addEventListener("click", () => runAction(refreshStatus));
  document.querySelector("#refresh-logs").addEventListener("click", () => runAction(refreshLogs));
  document.querySelector("#log-source").addEventListener("change", () => runAction(refreshLogs));
  document.querySelector("#log-capture").addEventListener("change", () => runAction(setLogCapture));
  document.querySelector("#refresh-files").addEventListener("click", () => runAction(refreshFiles));
  document.querySelector("#files-scope").addEventListener("change", () => runAction(refreshFiles));
  document.querySelector("#files-filter").addEventListener("input", renderFiles);
  document.querySelector("#upload-form").addEventListener("submit", (event) => {
    runAction(() => uploadFiles(event), "Upload complete.");
  });
  document.querySelector("#clone-form").addEventListener("submit", (event) => {
    runAction(() => cloneRepo(event), "Repository job started.");
  });
  document.querySelector("#index-form").addEventListener("submit", (event) => {
    runAction(() => startIndex(event), "Indexing job started.");
  });
  document.querySelector("#refresh-jobs").addEventListener("click", () => runAction(refreshJobs));
  document.querySelectorAll("[data-watch-start]").forEach((button) => {
    button.addEventListener("click", () => {
      runAction(() => watcherAction(button.dataset.watchStart, "start"), `${button.dataset.watchStart} watcher started.`);
    });
  });
  document.querySelectorAll("[data-watch-stop]").forEach((button) => {
    button.addEventListener("click", () => {
      runAction(() => watcherAction(button.dataset.watchStop, "stop"), `${button.dataset.watchStop} watcher stopped.`);
    });
  });
}

async function refreshCurrentTab() {
  if (state.currentTab === "overview") await refreshStatus();
  if (state.currentTab === "logs") await refreshLogs();
  if (state.currentTab === "files") await refreshFiles();
  if (state.currentTab === "upload") await refreshLogs();
  if (state.currentTab === "repos") await refreshJobs();
  if (state.currentTab === "indexing") await refreshJobs();
  if (state.currentTab === "watchers") await refreshWatchers();
}

function startPolling() {
  window.clearInterval(state.poller);
  state.poller = window.setInterval(() => {
    runAction(async () => {
      if (document.hidden) return;
      if (state.currentTab === "overview") await refreshStatus();
      if (state.currentTab === "logs") await refreshLogs();
      if (state.currentTab === "upload") await refreshLogs();
      if (state.currentTab === "repos") await refreshJobs();
      if (state.currentTab === "indexing") await refreshJobs();
      if (state.currentTab === "watchers") await refreshWatchers();
    });
  }, 2000);
}

window.addEventListener("DOMContentLoaded", async () => {
  bind();
  try {
    await refreshStatus();
    await refreshLogs();
    await refreshFiles();
    await refreshJobs();
    await refreshWatchers();
    startPolling();
  } catch (error) {
    showNotice(error.message, "bad");
  }
});
