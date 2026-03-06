const state = {
  bootstrap: null,
  last: null,
  pollHandle: null,
};

const els = {
  versionText: document.querySelector("#versionText"),
  heroStatus: document.querySelector("#heroStatus"),
  sessionBadge: document.querySelector("#sessionBadge"),
  backendSelect: document.querySelector("#backendSelect"),
  modelSelect: document.querySelector("#modelSelect"),
  customModelInput: document.querySelector("#customModelInput"),
  customModelField: document.querySelector("#customModelField"),
  modeSelect: document.querySelector("#modeSelect"),
  expectedNodesField: document.querySelector("#expectedNodesField"),
  expectedNodesInput: document.querySelector("#expectedNodesInput"),
  refreshModelsBtn: document.querySelector("#refreshModelsBtn"),
  selfCheckBtn: document.querySelector("#selfCheckBtn"),
  stopBtn: document.querySelector("#stopBtn"),
  controlForm: document.querySelector("#controlForm"),
  summaryGrid: document.querySelector("#summaryGrid"),
  checkGrid: document.querySelector("#checkGrid"),
  streamGrid: document.querySelector("#streamGrid"),
  logList: document.querySelector("#logList"),
};

init().catch((error) => {
  els.heroStatus.textContent = `初始化失败: ${error.message}`;
});

async function init() {
  bindEvents();
  const bootstrap = await api("/api/bootstrap");
  state.bootstrap = bootstrap;
  renderOptions(bootstrap.controls);
  renderState(bootstrap.state);
  if (!bootstrap.state.self_check.length) {
    await runSelfCheck();
  }
  state.pollHandle = window.setInterval(refreshState, 1500);
}

function bindEvents() {
  els.modeSelect.addEventListener("change", syncFieldVisibility);
  els.backendSelect.addEventListener("change", () => {
    syncModelOptions();
    syncFieldVisibility();
  });
  els.controlForm.addEventListener("submit", onStartSession);
  els.stopBtn.addEventListener("click", onStopSession);
  els.selfCheckBtn.addEventListener("click", runSelfCheck);
  els.refreshModelsBtn.addEventListener("click", refreshModels);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

function renderOptions(controls) {
  fillSelect(els.backendSelect, controls.backends, controls.defaults.ai_backend);
  fillSelect(els.modeSelect, controls.modes, controls.defaults.mode);
  syncModelOptions(controls.models, controls.defaults.selected_model);
  els.expectedNodesInput.value = controls.defaults.expected_nodes;
  els.versionText.textContent = state.bootstrap.version;
  syncFieldVisibility();
}

function fillSelect(select, options, selectedValue) {
  select.innerHTML = options
    .map((item) => `<option value="${item.value}">${item.label}</option>`)
    .join("");
  select.value = selectedValue;
}

function syncModelOptions(models = state.bootstrap.controls.models, selectedValue = state.last?.session?.selected_model) {
  const backend = els.backendSelect.value || state.bootstrap.controls.defaults.ai_backend;
  const options = (models[backend] || []).map((value) => ({ value, label: value }));
  options.push({ value: "__custom__", label: "自定义模型" });
  els.modelSelect.innerHTML = options.map((item) => `<option value="${item.value}">${item.label}</option>`).join("");
  const preset = options.find((item) => item.value === selectedValue) ? selectedValue : options[0]?.value;
  els.modelSelect.value = preset || "__custom__";
  if (selectedValue && !options.find((item) => item.value === selectedValue)) {
    els.modelSelect.value = "__custom__";
    els.customModelInput.value = selectedValue;
  }
  syncFieldVisibility();
}

function syncFieldVisibility() {
  const customVisible = els.modelSelect.value === "__custom__";
  const websocketVisible = els.modeSelect.value === "websocket";
  els.customModelField.style.display = customVisible ? "flex" : "none";
  els.expectedNodesField.style.display = websocketVisible ? "flex" : "none";
}

async function refreshState() {
  const payload = await api("/api/state");
  renderState(payload);
}

async function refreshModels() {
  const payload = await api("/api/models/refresh", { method: "POST", body: "{}" });
  state.bootstrap.controls.models = payload.models;
  syncModelOptions(payload.models, state.last?.session?.selected_model);
}

async function runSelfCheck() {
  els.selfCheckBtn.disabled = true;
  try {
    const payload = await api("/api/self-check", { method: "POST", body: "{}" });
    renderState(payload.state);
  } finally {
    els.selfCheckBtn.disabled = false;
  }
}

async function onStartSession(event) {
  event.preventDefault();
  const selectedModel = els.modelSelect.value === "__custom__" ? "" : els.modelSelect.value;
  const customModel = els.modelSelect.value === "__custom__" ? els.customModelInput.value.trim() : "";
  const payload = {
    ai_backend: els.backendSelect.value,
    selected_model: selectedModel,
    custom_model: customModel,
    mode: els.modeSelect.value,
    expected_nodes: Number(els.expectedNodesInput.value || 1),
  };

  try {
    const response = await api("/api/session/start", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderState(response.state);
  } catch (error) {
    els.heroStatus.textContent = error.message;
  }
}

async function onStopSession() {
  const response = await api("/api/session/stop", { method: "POST", body: "{}" });
  renderState(response.state);
}

function renderState(payload) {
  state.last = payload;
  els.versionText.textContent = payload.version;
  const active = payload.session.active;
  els.sessionBadge.textContent = active ? "运行中" : "待机";
  els.sessionBadge.className = `hero-chip hero-chip-accent ${active ? "status-online" : "status-offline"}`;
  els.heroStatus.textContent = payload.session.status_message || "等待配置";
  renderSummary(payload.summary, payload.session);
  renderChecks(payload.self_check);
  renderStreams(payload.streams, active);
  renderLogs(payload.logs);
}

function renderSummary(summary, session) {
  const items = [
    { label: "当前模式", value: session.mode === "idle" ? "-" : session.mode, meta: `后端 ${session.ai_backend}` },
    { label: "在线节点", value: summary.online_nodes, meta: `总流数 ${summary.stream_count}` },
    { label: "离线节点", value: summary.offline_nodes, meta: session.selected_model || "未选择模型" },
    { label: "语音助手", value: summary.voice_running ? "ON" : "OFF", meta: session.active ? "会话已启动" : "会话未启动" },
  ];
  els.summaryGrid.innerHTML = items.map((item) => `
    <article class="summary-card">
      <span>${item.label}</span>
      <strong>${item.value}</strong>
      <span>${item.meta}</span>
    </article>
  `).join("");
}

function renderChecks(checks) {
  els.checkGrid.innerHTML = checks.map((item) => `
    <article class="check-card">
      <div class="status-pill status-${item.status}">${item.title}</div>
      <p>${item.summary}</p>
      <div class="check-meta">${escapeHtml(item.detail || "")}</div>
    </article>
  `).join("");
}

function renderStreams(streams, active) {
  if (!streams.length) {
    els.streamGrid.className = "stream-grid empty-state";
    els.streamGrid.innerHTML = "";
    return;
  }

  els.streamGrid.className = "stream-grid";
  els.streamGrid.innerHTML = streams.map((stream) => `
    <article class="stream-card">
      <img src="/api/frame/${encodeURIComponent(stream.id)}?t=${Date.now()}" alt="${stream.title}">
      <div class="stream-body">
        <div class="stream-top">
          <div>
            <h3>${stream.title}</h3>
            <div class="stream-meta">${stream.subtitle} · ${stream.address}</div>
          </div>
          <div class="status-pill status-${stream.status}">${stream.status}</div>
        </div>
        <p class="stream-copy">${escapeHtml(stream.hint)}</p>
        <div class="stream-meta">Mic ${stream.caps.has_mic ? "Yes" : "No"} · Speaker ${stream.caps.has_speaker ? "Yes" : "No"} · ${active ? "实时轮询" : "待机快照"}</div>
      </div>
    </article>
  `).join("");
}

function renderLogs(logs) {
  const recent = logs.slice(-24).reverse();
  els.logList.innerHTML = recent.map((item) => `
    <article class="log-item">
      <div class="log-meta">
        <span class="status-${item.level.toLowerCase()}">${item.level}</span>
        <span>${item.timestamp}</span>
      </div>
      <p class="log-copy">${escapeHtml(item.text)}</p>
    </article>
  `).join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
