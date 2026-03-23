/* RPy Extractor - 3-step workflow with workspace accordion panels */

const appState = {
  gamePath: "",
  extracting: false,
  extractionDone: false,
  detectedExtensions: [],
  selectedExtensions: new Set(),
  scanning: false,
  logs: [],
  seenLogs: new Set(),
  currentTab: "step1",
  sortingAssets: [],
  sortingOffset: 0,
  sortingLimit: 100,
  sortingTruncated: false,
  sortingTotalCount: 0,
  sortingSortBy: "nameAsc",
  selectedAssetPath: "",
  selectedAssetIndex: -1,
  currentPreviewType: "",
  currentPreviewElement: null,
  previewCache: new Map(),
  dependencyStatuses: [],
  mergerWorkingDir: "",
  mergerDir: "",
  mergerNamingPattern: "number-to-name",
  mergerTransitionType: "diapo",
  mergerDiapoDelay: 3,
  mergerFadeCrossTime: 0.7,
  mergerOverlaySound: "",
  mergerExtensions: [],
  mergerSelectedExts: new Set(),
  mergerExtensionsInitialized: false,
  mergerCandidates: [],
  mergerOffset: 0,
  mergerLimit: 120,
  mergerTruncated: false,
  mergerTotalCount: 0,
  mergerSelectedCandidateNames: new Set(),
  mergerAutoSelectedOnce: false,
  mergerConflictResolutions: new Map(),
  mergerConflictDrafts: new Map(),
  mergerCandidateLoops: new Map(),
};

const DOM = {
  step1Header: document.getElementById("step1Header"),
  step1Body: document.getElementById("step1Body"),
  step2Header: document.getElementById("step2Header"),
  step2Body: document.getElementById("step2Body"),
  step3Header: document.getElementById("step3Header"),
  step3Body: document.getElementById("step3Body"),

  gamePath: document.getElementById("gamePath"),
  choosePathBtn: document.getElementById("choosePathBtn"),
  extractBtn: document.getElementById("extractBtn"),
  refreshDepsBtn: document.getElementById("refreshDepsBtn"),
  dependencyStatus: document.getElementById("dependencyStatus"),
  step1Status: document.getElementById("step1Status"),

  step2Path: document.getElementById("step2Path"),
  step2BrowseBtn: document.getElementById("step2BrowseBtn"),
  scanBtn: document.getElementById("scanBtn"),
  selectAllBtn: document.getElementById("selectAllBtn"),
  selectNoneBtn: document.getElementById("selectNoneBtn"),
  keepSelectedBtn: document.getElementById("keepSelectedBtn"),
  extensionsList: document.getElementById("extensionsList"),
  extensionsPlaceholder: document.querySelector(".extensions-placeholder"),
  step2Status: document.getElementById("step2Status"),

  openSortingPanelBtn: document.getElementById("openSortingPanelBtn"),
  step3Status: document.getElementById("step3Status"),

  sortingWindowHeader: document.getElementById("sortingWindowHeader"),
  sortingWindowBody: document.getElementById("sortingWindowBody"),
  mediaMergerHeader: document.getElementById("mediaMergerHeader"),
  mediaMergerBody: document.getElementById("mediaMergerBody"),
  activityLogHeader: document.getElementById("activityLogHeader"),
  activityLogBody: document.getElementById("activityLogBody"),
  clearLogBtn: document.getElementById("clearLogBtn"),
  loadLogBtn: document.getElementById("loadLogBtn"),
  refreshSortingWindowBtn: document.getElementById("refreshSortingWindowBtn"),
  saveCurrentAssetsBtn: document.getElementById("saveCurrentAssetsBtn"),
  clearSortingTrashBtn: document.getElementById("clearSortingTrashBtn"),
  sortingPrevBtn: document.getElementById("sortingPrevBtn"),
  sortingNextBtn: document.getElementById("sortingNextBtn"),
  sortingSortBy: document.getElementById("sortingSortBy"),
  sortingPageInfo: document.getElementById("sortingPageInfo"),
  sortingAssetsList: document.getElementById("sortingAssetsList"),
  sortingPreviewMeta: document.getElementById("sortingPreviewMeta"),
  sortingPreview: document.getElementById("sortingPreview"),
  previewFullscreenBtn: document.getElementById("previewFullscreenBtn"),
  previewSpeedSelect: document.getElementById("previewSpeedSelect"),
  previewMoreBtn: document.getElementById("previewMoreBtn"),

  mergerWorkingDir: document.getElementById("mergerWorkingDir"),
  mergerBrowseBtn: document.getElementById("mergerBrowseBtn"),
  mergerNamingPattern: document.getElementById("mergerNamingPattern"),
  mergerTransitionType: document.getElementById("mergerTransitionType"),
  mergerDiapoDelayRow: document.getElementById("mergerDiapoDelayRow"),
  mergerFadeCrossRow: document.getElementById("mergerFadeCrossRow"),
  mergerDiapoDelay: document.getElementById("mergerDiapoDelay"),
  mergerFadeCross: document.getElementById("mergerFadeCross"),
  mergerOverlaySound: document.getElementById("mergerOverlaySound"),
  mergerSelectOverlayBtn: document.getElementById("mergerSelectOverlayBtn"),
  mergerRefreshListBtn: document.getElementById("mergerRefreshListBtn"),
  mergerSelectAllExtBtn: document.getElementById("mergerSelectAllExtBtn"),
  mergerSelectNoneExtBtn: document.getElementById("mergerSelectNoneExtBtn"),
  mergerExtensionsList: document.getElementById("mergerExtensionsList"),
  mergerCandidatesList: document.getElementById("mergerCandidatesList"),
  mergerCandidatesMeta: document.getElementById("mergerCandidatesMeta"),
  mergerPrevBtn: document.getElementById("mergerPrevBtn"),
  mergerNextBtn: document.getElementById("mergerNextBtn"),
  mergerPageInfo: document.getElementById("mergerPageInfo"),
  mergerSelectAllCandidatesBtn: document.getElementById("mergerSelectAllCandidatesBtn"),
  mergerSelectNoneCandidatesBtn: document.getElementById("mergerSelectNoneCandidatesBtn"),
  mergerOutputName: document.getElementById("mergerOutputName"),
  mergerTrashToggle: document.getElementById("mergerTrashToggle"),
  mergerBuildBtn: document.getElementById("mergerBuildBtn"),
  mediaMergerStatus: document.getElementById("mediaMergerStatus"),

  mainLog: document.getElementById("mainLog"),
  serverState: document.getElementById("serverState"),
};

function formatTime() {
  return new Date().toLocaleTimeString();
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function addLog(message) {
  if (appState.seenLogs.has(message)) {
    return;
  }
  appState.seenLogs.add(message);
  appState.logs.push(message);
  if (appState.logs.length > 1200) {
    const removed = appState.logs.shift();
    if (typeof removed === "string") {
      appState.seenLogs.delete(removed);
    }
  }

  const logLine = document.createElement("div");
  logLine.className = "log-line";
  logLine.innerHTML = `<span class="log-time">[${formatTime()}]</span> ${escapeHtml(message)}`;
  DOM.mainLog.appendChild(logLine);

  while (DOM.mainLog.childElementCount > 500) {
    DOM.mainLog.removeChild(DOM.mainLog.firstElementChild);
  }

  DOM.mainLog.scrollTop = DOM.mainLog.scrollHeight;
}

function setStatus(message, type = "info") {
  DOM.serverState.textContent = message;
  DOM.serverState.className = `chip chip--${type}`;
}

function setStepStatus(stepId, message, type = "info") {
  const statusEl = document.getElementById(`step${stepId}Status`);
  if (statusEl) {
    statusEl.innerHTML = `<span class="status-${type}">${escapeHtml(message)}</span>`;
  }
}

function renderDependencyStatuses() {
  if (!DOM.dependencyStatus) {
    return;
  }

  if (!Array.isArray(appState.dependencyStatuses) || appState.dependencyStatuses.length === 0) {
    DOM.dependencyStatus.innerHTML = "<div class=\"extensions-placeholder\">No dependency data available.</div>";
    return;
  }

  DOM.dependencyStatus.innerHTML = "";
  for (const item of appState.dependencyStatuses) {
    const card = document.createElement("div");
    const stateClass = item.available ? "ok" : (item.required ? "missing" : "warn");
    card.className = `dependency-card dependency-card--${stateClass}`;

    const name = document.createElement("div");
    name.className = "dependency-card__name";
    name.textContent = item.label || item.id || "dependency";

    const meta = document.createElement("div");
    meta.className = "dependency-card__meta";
    meta.textContent = item.available ? "available" : (item.required ? "required missing" : "optional missing");

    card.appendChild(name);
    card.appendChild(meta);
    DOM.dependencyStatus.appendChild(card);
  }
}

async function syncDependencyStatuses() {
  try {
    const payload = await api("/api/dependencies");
    if (!payload.success) {
      DOM.dependencyStatus.innerHTML = "<div class=\"extensions-placeholder\">Dependency status unavailable.</div>";
      return;
    }

    appState.dependencyStatuses = Array.isArray(payload.dependencies) ? payload.dependencies : [];
    renderDependencyStatuses();
    addLog(`[DEPS] Refreshed ${appState.dependencyStatuses.length} dependency checks`);
  } catch (_err) {
    DOM.dependencyStatus.innerHTML = "<div class=\"extensions-placeholder\">Dependency status unavailable.</div>";
  }
}

async function api(path, options = {}) {
  try {
    const response = await fetch(path, {
      method: options.method || "GET",
      headers: { "Content-Type": "application/json" },
      body: options.body ? JSON.stringify(options.body) : undefined,
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    return await response.json();
  } catch (err) {
    addLog(`ERROR: ${err.message}`);
    throw err;
  }
}

async function handleApiOperation(operationLabel, apiPath, apiOptions, onSuccess, fallbackMessage) {
  addLog(`[API] Starting: ${operationLabel}`);
  try {
    const result = await api(apiPath, apiOptions);
    addLog(`[API] Response: ${operationLabel} - ${result.success ? "success" : "error"}`);
    if (result.success) {
      if (onSuccess) onSuccess(result);
      return result;
    }
    const errorMsg = result.error || fallbackMessage || "Operation failed";
    addLog(`[API] Error: ${errorMsg}`);
    return result;
  } catch (err) {
    addLog(`[API] Exception: ${operationLabel} - ${err.message}`);
    throw err;
  }
}

async function syncLogs() {
  try {
    const payload = await api("/api/logs");
    const logs = Array.isArray(payload.logs) ? payload.logs : [];
    for (const entry of logs) {
      if (typeof entry === "string" && !appState.seenLogs.has(entry)) {
        addLog(entry);
      }
    }
  } catch (_err) {
    // Keep UI responsive on transient failures.
  }
}

function openAccordion(stepNum) {
  [1, 2, 3].forEach((num) => {
    const header = DOM[`step${num}Header`];
    const body = DOM[`step${num}Body`];
    if (header) header.setAttribute("aria-expanded", "false");
    if (body) body.setAttribute("aria-hidden", "true");
  });

  const header = DOM[`step${stepNum}Header`];
  const body = DOM[`step${stepNum}Body`];
  if (header) header.setAttribute("aria-expanded", "true");
  if (body) body.setAttribute("aria-hidden", "false");
  appState.currentTab = `step${stepNum}`;
}

function toggleAccordion(stepNum) {
  const header = DOM[`step${stepNum}Header`];
  const isOpen = header.getAttribute("aria-expanded") === "true";
  if (isOpen) {
    openAccordion(stepNum === 1 ? 2 : stepNum - 1);
  } else {
    openAccordion(stepNum);
  }
}

function setupAccordionHandlers() {
  [1, 2, 3].forEach((num) => {
    const header = DOM[`step${num}Header`];
    if (header) {
      header.addEventListener("click", () => toggleAccordion(num));
    }
  });
}

function openWorkspacePanel(panelName) {
  const openSorting = panelName === "sorting";
  const openMerger = panelName === "merger";
  const openLog = panelName === "log";

  DOM.sortingWindowHeader.setAttribute("aria-expanded", String(openSorting));
  DOM.sortingWindowBody.setAttribute("aria-hidden", String(!openSorting));

  DOM.mediaMergerHeader?.setAttribute("aria-expanded", String(openMerger));
  DOM.mediaMergerBody?.setAttribute("aria-hidden", String(!openMerger));

  DOM.activityLogHeader.setAttribute("aria-expanded", String(openLog));
  DOM.activityLogBody.setAttribute("aria-hidden", String(!openLog));
}

function setupWorkspaceAccordionHandlers() {
  DOM.sortingWindowHeader?.addEventListener("click", () => {
    const sortingOpen = DOM.sortingWindowHeader.getAttribute("aria-expanded") === "true";
    openWorkspacePanel(sortingOpen ? "merger" : "sorting");
  });

  DOM.mediaMergerHeader?.addEventListener("click", () => {
    const mergerOpen = DOM.mediaMergerHeader.getAttribute("aria-expanded") === "true";
    openWorkspacePanel(mergerOpen ? "log" : "merger");
  });

  DOM.activityLogHeader?.addEventListener("click", () => {
    const logOpen = DOM.activityLogHeader.getAttribute("aria-expanded") === "true";
    openWorkspacePanel(logOpen ? "sorting" : "log");
  });
}

function setMediaMergerStatus(message, type = "info") {
  if (!DOM.mediaMergerStatus) {
    return;
  }
  DOM.mediaMergerStatus.innerHTML = `<span class="status-${type}">${escapeHtml(message)}</span>`;
}

function conflictKey(candidateName, index) {
  return `${String(candidateName || "")}::${String(index || "")}`;
}

function getConflictOrder(candidateName, conflict) {
  const key = conflictKey(candidateName, conflict.index);
  const fallback = (Array.isArray(conflict.options) ? conflict.options : [])
    .map((option) => String(option?.path || ""))
    .filter(Boolean);
  return appState.mergerConflictDrafts.get(key)
    || appState.mergerConflictResolutions.get(key)
    || fallback;
}

function moveConflictItem(candidateName, index, fromIdx, toIdx) {
  const key = conflictKey(candidateName, index);
  const current = Array.from(appState.mergerConflictDrafts.get(key) || appState.mergerConflictResolutions.get(key) || []);
  if (!current.length || fromIdx < 0 || fromIdx >= current.length || toIdx < 0 || toIdx >= current.length) {
    return;
  }
  const [item] = current.splice(fromIdx, 1);
  current.splice(toIdx, 0, item);
  appState.mergerConflictDrafts.set(key, current);
  appState.mergerConflictResolutions.set(key, Array.from(current));
  renderMergerCandidates();
}

function ensureCandidateLoopConfig(candidateName) {
  const key = String(candidateName || "");
  const existing = appState.mergerCandidateLoops.get(key);
  if (existing) {
    return existing;
  }

  const created = {
    entiretyTimes: 1,
    partLoops: [{ indexes: "", times: "" }],
  };
  appState.mergerCandidateLoops.set(key, created);
  return created;
}

function sanitizeLoopTimes(rawValue) {
  const parsed = Number.parseInt(String(rawValue || "").trim(), 10);
  if (!Number.isFinite(parsed) || parsed < 1) {
    return 1;
  }
  return parsed;
}

function parseLoopIndexes(rawIndexes) {
  const parts = String(rawIndexes || "")
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  return new Set(parts);
}

function ensurePartLoopTrailingBlank(loopConfig) {
  if (!loopConfig || !Array.isArray(loopConfig.partLoops)) {
    return;
  }
  if (loopConfig.partLoops.length === 0) {
    loopConfig.partLoops.push({ indexes: "", times: "" });
    return;
  }

  const last = loopConfig.partLoops[loopConfig.partLoops.length - 1];
  const hasIndexes = String(last.indexes || "").trim().length > 0;
  const hasTimes = String(last.times || "").trim().length > 0;
  if (hasIndexes && hasTimes) {
    loopConfig.partLoops.push({ indexes: "", times: "" });
  }
}

function syncMergerTransitionFields() {
  const transition = String(DOM.mergerTransitionType?.value || "diapo");
  const isFade = transition === "fade";
  if (DOM.mergerDiapoDelayRow) {
    DOM.mergerDiapoDelayRow.style.display = isFade ? "none" : "grid";
  }
  if (DOM.mergerFadeCrossRow) {
    DOM.mergerFadeCrossRow.style.display = isFade ? "grid" : "none";
  }
}

function renderMergerExtensions() {
  if (!DOM.mergerExtensionsList) {
    return;
  }
  DOM.mergerExtensionsList.innerHTML = "";

  for (const item of appState.mergerExtensions) {
    const ext = String(item.ext || "");
    const count = Number(item.count || 0);

    const label = document.createElement("label");
    label.className = "ext-checkbox";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = appState.mergerSelectedExts.has(ext);
    checkbox.addEventListener("change", async (event) => {
      if (event.target.checked) {
        appState.mergerSelectedExts.add(ext);
      } else {
        appState.mergerSelectedExts.delete(ext);
      }
      await refreshMergerCandidates({ resetOffset: true });
    });

    const text = document.createElement("span");
    text.textContent = `${ext} (${count})`;

    label.appendChild(checkbox);
    label.appendChild(text);
    DOM.mergerExtensionsList.appendChild(label);
  }

  if (appState.mergerExtensions.length === 0) {
    DOM.mergerExtensionsList.innerHTML = "<div class=\"extensions-placeholder\">No media extensions detected.</div>";
  }
}

function renderMergerCandidates() {
  if (!DOM.mergerCandidatesList) {
    return;
  }

  const totalCandidates = Number(appState.mergerTotalCount || 0);
  const shownCount = Array.isArray(appState.mergerCandidates) ? appState.mergerCandidates.length : 0;
  const start = shownCount > 0 ? appState.mergerOffset + 1 : 0;
  const end = appState.mergerOffset + shownCount;

  if (DOM.mergerCandidatesMeta) {
    DOM.mergerCandidatesMeta.textContent = `${totalCandidates} candidate(s) total`;
  }
  if (DOM.mergerPageInfo) {
    DOM.mergerPageInfo.textContent = `${start}-${end}/${totalCandidates}`;
  }
  if (DOM.mergerPrevBtn) {
    DOM.mergerPrevBtn.disabled = appState.mergerOffset <= 0;
  }
  if (DOM.mergerNextBtn) {
    DOM.mergerNextBtn.disabled = !appState.mergerTruncated;
  }

  DOM.mergerCandidatesList.innerHTML = "";
  if (!Array.isArray(appState.mergerCandidates) || appState.mergerCandidates.length === 0) {
    DOM.mergerCandidatesList.innerHTML = "<div class=\"extensions-placeholder\">No matching candidates.</div>";
    return;
  }

  const fragment = document.createDocumentFragment();
  for (const candidate of appState.mergerCandidates) {
    const name = String(candidate.name || "untitled");
    const indexes = Array.isArray(candidate.indexes) ? candidate.indexes : [];
    const conflicts = Array.isArray(candidate.conflicts) ? candidate.conflicts : [];
    const loopConfig = ensureCandidateLoopConfig(name);
    ensurePartLoopTrailingBlank(loopConfig);

    const row = document.createElement("div");
    row.className = "media-merger-candidate";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = appState.mergerSelectedCandidateNames.has(name);
    checkbox.addEventListener("change", (event) => {
      if (event.target.checked) {
        appState.mergerSelectedCandidateNames.add(name);
      } else {
        appState.mergerSelectedCandidateNames.delete(name);
      }
    });

    const content = document.createElement("div");
    content.className = "media-merger-candidate__content";
    content.textContent = `name: ${name}  indexes: [${indexes.join(", ")}]`;

    const body = document.createElement("div");
    body.className = "media-merger-candidate__body";
    body.appendChild(content);

    const loopsWrap = document.createElement("div");
    loopsWrap.className = "media-merger-loops";

    const entiretyRow = document.createElement("div");
    entiretyRow.className = "media-merger-loop-row";

    const entiretyLabel = document.createElement("span");
    entiretyLabel.className = "media-merger-loop-label";
    entiretyLabel.textContent = "loop entirety";

    const entiretyInput = document.createElement("input");
    entiretyInput.type = "number";
    entiretyInput.min = "1";
    entiretyInput.step = "1";
    entiretyInput.value = String(sanitizeLoopTimes(loopConfig.entiretyTimes));
    entiretyInput.className = "media-merger-loop-input";
    entiretyInput.addEventListener("input", () => {
      loopConfig.entiretyTimes = sanitizeLoopTimes(entiretyInput.value);
      appState.mergerCandidateLoops.set(name, loopConfig);
    });

    const entiretyTimes = document.createElement("span");
    entiretyTimes.className = "media-merger-loop-suffix";
    entiretyTimes.textContent = "times";

    entiretyRow.appendChild(entiretyLabel);
    entiretyRow.appendChild(entiretyInput);
    entiretyRow.appendChild(entiretyTimes);
    loopsWrap.appendChild(entiretyRow);

    loopConfig.partLoops.forEach((partLoop) => {
      const row = document.createElement("div");
      row.className = "media-merger-loop-row";

      const label = document.createElement("span");
      label.className = "media-merger-loop-label";
      label.textContent = "loop parts";

      const indexesInput = document.createElement("input");
      indexesInput.type = "text";
      indexesInput.placeholder = "indexes (e.g. 00,01)";
      indexesInput.value = String(partLoop.indexes || "");
      indexesInput.className = "media-merger-loop-indexes";
      indexesInput.addEventListener("input", () => {
        const beforeLength = loopConfig.partLoops.length;
        partLoop.indexes = indexesInput.value;
        ensurePartLoopTrailingBlank(loopConfig);
        appState.mergerCandidateLoops.set(name, loopConfig);
        if (loopConfig.partLoops.length > beforeLength) {
          renderMergerCandidates();
        }
      });

      const timesInput = document.createElement("input");
      timesInput.type = "number";
      timesInput.min = "1";
      timesInput.step = "1";
      timesInput.placeholder = "times";
      timesInput.value = String(partLoop.times || "");
      timesInput.className = "media-merger-loop-input";
      timesInput.addEventListener("input", () => {
        const beforeLength = loopConfig.partLoops.length;
        partLoop.times = timesInput.value;
        ensurePartLoopTrailingBlank(loopConfig);
        appState.mergerCandidateLoops.set(name, loopConfig);
        if (loopConfig.partLoops.length > beforeLength) {
          renderMergerCandidates();
        }
      });

      const timesSuffix = document.createElement("span");
      timesSuffix.className = "media-merger-loop-suffix";
      timesSuffix.textContent = "times";

      row.appendChild(label);
      row.appendChild(indexesInput);
      row.appendChild(timesInput);
      row.appendChild(timesSuffix);
      loopsWrap.appendChild(row);
    });

    const addLoopRowWrap = document.createElement("div");
    addLoopRowWrap.className = "media-merger-loop-add-row";

    const addLoopBtn = document.createElement("button");
    addLoopBtn.type = "button";
    addLoopBtn.className = "btn btn--ghost media-merger-plus-btn";
    addLoopBtn.textContent = "+";
    addLoopBtn.title = "Add part-loop row";
    addLoopBtn.setAttribute("aria-label", "Add part-loop row");
    addLoopBtn.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      loopConfig.partLoops.push({ indexes: "", times: "" });
      appState.mergerCandidateLoops.set(name, loopConfig);
      renderMergerCandidates();
    });

    addLoopRowWrap.appendChild(addLoopBtn);
    loopsWrap.appendChild(addLoopRowWrap);

    body.appendChild(loopsWrap);

    if (conflicts.length > 0) {
      const conflictWrap = document.createElement("div");
      conflictWrap.className = "media-merger-conflicts";

      const conflictTitle = document.createElement("div");
      conflictTitle.className = "media-merger-conflicts__title";
      conflictTitle.textContent = `conflicts: ${conflicts.length}`;
      conflictWrap.appendChild(conflictTitle);

      for (const conflict of conflicts) {
        const indexValue = String(conflict.index || "");
        const order = getConflictOrder(name, conflict);
        const optionByPath = new Map(
          (Array.isArray(conflict.options) ? conflict.options : []).map((option) => [String(option.path || ""), option])
        );

        const card = document.createElement("div");
        card.className = "media-merger-conflict-card";

        const heading = document.createElement("div");
        heading.className = "media-merger-conflict-card__heading";
        heading.textContent = `index ${indexValue}`;
        card.appendChild(heading);

        const blocks = document.createElement("div");
        blocks.className = "media-merger-conflict-blocks";

        order.forEach((path, idx) => {
          const option = optionByPath.get(path);
          if (!option) {
            return;
          }

          const block = document.createElement("div");
          block.className = "media-merger-ext-block";

          const extText = document.createElement("span");
          extText.className = "media-merger-ext-block__label";
          extText.textContent = String(option.ext || "");
          block.appendChild(extText);

          const controls = document.createElement("div");
          controls.className = "media-merger-ext-block__controls";

          const upBtn = document.createElement("button");
          upBtn.type = "button";
          upBtn.className = "btn btn--ghost media-merger-mini-btn";
          upBtn.textContent = "Up";
          upBtn.disabled = idx === 0;
          upBtn.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            moveConflictItem(name, indexValue, idx, idx - 1);
          });

          const downBtn = document.createElement("button");
          downBtn.type = "button";
          downBtn.className = "btn btn--ghost media-merger-mini-btn";
          downBtn.textContent = "Down";
          downBtn.disabled = idx >= order.length - 1;
          downBtn.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            moveConflictItem(name, indexValue, idx, idx + 1);
          });

          controls.appendChild(upBtn);
          controls.appendChild(downBtn);
          block.appendChild(controls);
          blocks.appendChild(block);
        });

        card.appendChild(blocks);

        conflictWrap.appendChild(card);
      }

      body.appendChild(conflictWrap);
    }

    row.appendChild(checkbox);
    row.appendChild(body);
    fragment.appendChild(row);
  }

  DOM.mergerCandidatesList.appendChild(fragment);
}

function getSelectedMergerPaths() {
  const selectedNames = new Set(appState.mergerSelectedCandidateNames);
  const paths = [];

  for (const candidate of appState.mergerCandidates) {
    const name = String(candidate.name || "");
    if (!selectedNames.has(name)) {
      continue;
    }

    const files = Array.isArray(candidate.files) ? candidate.files : [];
    const conflictList = Array.isArray(candidate.conflicts) ? candidate.conflicts : [];
    const conflictByIndex = new Map(conflictList.map((conflict) => [String(conflict.index || ""), conflict]));
    const emitted = new Set();
    const buckets = new Map();
    const parsedIndexByPath = new Map();

    for (const file of files) {
      const relPath = String(file.path || "").trim();
      if (!relPath) {
        continue;
      }
      const parsedIndex = String(file.parsedIndex || "").trim();
      const bucketKey = parsedIndex || `__single__${relPath}`;
      parsedIndexByPath.set(relPath, parsedIndex);
      if (!buckets.has(bucketKey)) {
        buckets.set(bucketKey, []);
      }
      buckets.get(bucketKey).push(relPath);
    }

    const baseCandidatePaths = [];

    for (const bucketKey of buckets.keys()) {
      const conflict = conflictByIndex.get(bucketKey);
      const bucketPaths = buckets.get(bucketKey) || [];

      if (conflict) {
        const resolvedOrder = getConflictOrder(name, conflict).filter((path) => bucketPaths.includes(path));
        for (const relPath of resolvedOrder) {
          if (!emitted.has(relPath)) {
            baseCandidatePaths.push(relPath);
            emitted.add(relPath);
          }
        }
        for (const relPath of bucketPaths) {
          if (!emitted.has(relPath)) {
            baseCandidatePaths.push(relPath);
            emitted.add(relPath);
          }
        }
      } else {
        for (const relPath of bucketPaths) {
          if (!emitted.has(relPath)) {
            baseCandidatePaths.push(relPath);
            emitted.add(relPath);
          }
        }
      }
    }

    const loopConfig = ensureCandidateLoopConfig(name);
    const partMultiplier = new Map();
    const partLoopRows = Array.isArray(loopConfig.partLoops) ? loopConfig.partLoops : [];
    for (const row of partLoopRows) {
      const indexes = parseLoopIndexes(row.indexes);
      const timesRaw = String(row.times || "").trim();
      if (indexes.size === 0 || !timesRaw) {
        continue;
      }
      const times = sanitizeLoopTimes(timesRaw);
      for (const idx of indexes) {
        partMultiplier.set(idx, times);
      }
    }

    const expandedByPartLoops = [];
    for (const relPath of baseCandidatePaths) {
      const parsedIndex = String(parsedIndexByPath.get(relPath) || "");
      const multiplier = partMultiplier.get(parsedIndex) || 1;
      for (let i = 0; i < multiplier; i += 1) {
        expandedByPartLoops.push(relPath);
      }
    }

    const entiretyTimes = sanitizeLoopTimes(loopConfig.entiretyTimes);
    for (let loopIndex = 0; loopIndex < entiretyTimes; loopIndex += 1) {
      for (const relPath of expandedByPartLoops) {
        paths.push(relPath);
      }
    }
  }

  return paths;
}

function getSelectedCandidateBuildSpecs() {
  const selectedNames = new Set(appState.mergerSelectedCandidateNames);
  const specs = [];

  for (const selectedName of selectedNames) {
    const name = String(selectedName || "").trim();
    if (!name) {
      continue;
    }

    const loopConfig = ensureCandidateLoopConfig(name);
    const partLoops = [];
    const rawPartLoops = Array.isArray(loopConfig.partLoops) ? loopConfig.partLoops : [];
    for (const row of rawPartLoops) {
      const indexes = String(row?.indexes || "").trim();
      const times = String(row?.times || "").trim();
      if (!indexes || !times) {
        continue;
      }
      partLoops.push({ indexes, times });
    }

    const conflictResolutions = {};
    for (const [key, order] of appState.mergerConflictResolutions.entries()) {
      const [candidateName, idx] = String(key).split("::");
      if (candidateName !== name) {
        continue;
      }
      if (idx && Array.isArray(order) && order.length > 0) {
        conflictResolutions[idx] = Array.from(order);
      }
    }

    specs.push({
      name,
      entiretyTimes: sanitizeLoopTimes(loopConfig.entiretyTimes),
      partLoops,
      conflictResolutions,
    });
  }

  return specs;
}

async function refreshMergerCandidates(options = {}) {
  const resetOffset = Boolean(options.resetOffset);
  const workingDir = String(DOM.mergerWorkingDir?.value || appState.mergerWorkingDir || "").trim();
  const namingPattern = String(DOM.mergerNamingPattern?.value || "number-to-name");
  const shouldLoadAllByDefault = !appState.mergerExtensionsInitialized && appState.mergerSelectedExts.size === 0;

  if (resetOffset) {
    appState.mergerOffset = 0;
  }

  setMediaMergerStatus("Refreshing media list...", "info");

  try {
    const payload = await api("/api/media-merger/list", {
      method: "POST",
      body: {
        workingDir,
        namingPattern,
        allowedExts: shouldLoadAllByDefault ? null : Array.from(appState.mergerSelectedExts),
        offset: appState.mergerOffset,
        limit: appState.mergerLimit,
      },
    });

    if (!payload.success) {
      setMediaMergerStatus(payload.error || "Could not list media candidates", "error");
      return;
    }

    appState.mergerWorkingDir = String(payload.workingDir || workingDir);
    if (DOM.mergerWorkingDir) {
      DOM.mergerWorkingDir.value = appState.mergerWorkingDir;
    }

    appState.mergerExtensions = Array.isArray(payload.extensions) ? payload.extensions : [];

    if (shouldLoadAllByDefault) {
      appState.mergerSelectedExts = new Set(appState.mergerExtensions.map((entry) => String(entry.ext || "")));
    } else {
      const available = new Set(appState.mergerExtensions.map((entry) => String(entry.ext || "")));
      appState.mergerSelectedExts = new Set(
        Array.from(appState.mergerSelectedExts).filter((ext) => available.has(ext))
      );
    }
    appState.mergerExtensionsInitialized = true;

    appState.mergerCandidates = Array.isArray(payload.candidates) ? payload.candidates : [];
    appState.mergerOffset = Math.max(0, Number(payload.offset || appState.mergerOffset || 0));
    appState.mergerLimit = Math.max(1, Number(payload.limit || appState.mergerLimit || 120));
    appState.mergerTotalCount = Math.max(0, Number(payload.totalCount || appState.mergerCandidates.length || 0));
    appState.mergerTruncated = Boolean(payload.truncated);

    if (!appState.mergerAutoSelectedOnce && appState.mergerSelectedCandidateNames.size === 0) {
      for (const candidate of appState.mergerCandidates) {
        appState.mergerSelectedCandidateNames.add(String(candidate.name || ""));
      }
      appState.mergerAutoSelectedOnce = true;
    }

    renderMergerExtensions();
    renderMergerCandidates();
    setMediaMergerStatus(
      `Loaded ${appState.mergerCandidates.length}/${appState.mergerTotalCount} candidate group(s) and ${Number(payload.fileCount || 0)} file(s)`,
      "ok"
    );
  } catch (_err) {
    setMediaMergerStatus("Failed to refresh media list", "error");
  }
}

async function initializeMediaMerger() {
  try {
    const payload = await api("/api/media-merger/state");
    if (!payload.success) {
      setMediaMergerStatus(payload.error || "Could not initialize media merger", "error");
      return;
    }

    appState.mergerWorkingDir = String(payload.workingDir || "");
    appState.mergerDir = String(payload.mergerDir || "");
    appState.mergerNamingPattern = String(payload.defaultPattern || "number-to-name");
    appState.mergerTransitionType = String(payload.defaultTransition || "diapo");
    appState.mergerDiapoDelay = Number(payload.defaultDiapoDelay || 3);
    appState.mergerFadeCrossTime = Number(payload.defaultFadeCrossTime || 0.7);

    if (DOM.mergerWorkingDir) {
      DOM.mergerWorkingDir.value = appState.mergerWorkingDir;
    }
    if (DOM.mergerNamingPattern) {
      DOM.mergerNamingPattern.value = appState.mergerNamingPattern;
    }
    if (DOM.mergerTransitionType) {
      DOM.mergerTransitionType.value = appState.mergerTransitionType;
    }
    if (DOM.mergerDiapoDelay) {
      DOM.mergerDiapoDelay.value = String(appState.mergerDiapoDelay);
    }
    if (DOM.mergerFadeCross) {
      DOM.mergerFadeCross.value = String(appState.mergerFadeCrossTime);
    }

    syncMergerTransitionFields();
    await refreshMergerCandidates();
  } catch (_err) {
    setMediaMergerStatus("Media merger initialization failed", "error");
  }
}

function isTypingTarget(target) {
  if (!target) {
    return false;
  }
  const tag = (target.tagName || "").toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || Boolean(target.isContentEditable);
}

function getSelectedAssetIndex() {
  return appState.sortingAssets.findIndex((asset) => asset.path === appState.selectedAssetPath);
}

function syncSelectedAssetIndex() {
  appState.selectedAssetIndex = getSelectedAssetIndex();
}

function compareString(a, b) {
  return String(a || "").localeCompare(String(b || ""), undefined, { sensitivity: "base" });
}

function extensionFromEncodedPath(encodedPath) {
  const decoded = decodeURIComponent(String(encodedPath || "").split("/").pop() || "");
  const dotIndex = decoded.lastIndexOf(".");
  if (dotIndex < 0) {
    return ".noext";
  }
  return decoded.slice(dotIndex).toLowerCase() || ".noext";
}

function inferAssetTypeFromExt(ext) {
  const normalized = String(ext || "").toLowerCase();
  if ([".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".svg", ".ico"].includes(normalized)) {
    return "image";
  }
  if ([".mp3", ".ogg", ".wav", ".m4a", ".aac", ".opus", ".flac"].includes(normalized)) {
    return "audio";
  }
  if ([".mp4", ".webm", ".mov", ".m4v", ".mpeg", ".mpg", ".avi", ".mkv"].includes(normalized)) {
    return "video";
  }
  if ([".txt", ".json", ".xml", ".csv", ".md", ".rpy", ".rpym", ".ini", ".log", ".py", ".js", ".css", ".html"].includes(normalized)) {
    return "text";
  }
  return "binary";
}

function createAssetStubFromPath(encodedPath) {
  const decodedName = decodeURIComponent(String(encodedPath || "").split("/").pop() || "asset");
  const ext = extensionFromEncodedPath(encodedPath);
  return {
    name: decodedName,
    path: String(encodedPath || ""),
    ext,
    size: 0,
    type: inferAssetTypeFromExt(ext),
  };
}

function applySortingToAssets() {
  const mode = appState.sortingSortBy || "nameAsc";
  appState.sortingAssets.sort((a, b) => {
    if (mode === "nameDesc") {
      return compareString(b.name, a.name) || compareString(a.path, b.path);
    }
    if (mode === "typeAsc") {
      return compareString(a.type, b.type) || compareString(a.name, b.name) || compareString(a.path, b.path);
    }
    if (mode === "extAsc") {
      return compareString(a.ext, b.ext) || compareString(a.name, b.name) || compareString(a.path, b.path);
    }
    if (mode === "sizeDesc") {
      return (Number(b.size || 0) - Number(a.size || 0)) || compareString(a.name, b.name) || compareString(a.path, b.path);
    }
    if (mode === "sizeAsc") {
      return (Number(a.size || 0) - Number(b.size || 0)) || compareString(a.name, b.name) || compareString(a.path, b.path);
    }
    return compareString(a.name, b.name) || compareString(a.path, b.path);
  });
}

function updateSortingPaginationUi() {
  const count = appState.sortingAssets.length;
  const start = count > 0 ? appState.sortingOffset + 1 : 0;
  const end = appState.sortingOffset + count;
  const safeTotal = Number.isFinite(appState.sortingTotalCount) ? appState.sortingTotalCount : end;
  const totalLabel = Math.max(end, safeTotal);

  if (DOM.sortingPageInfo) {
    DOM.sortingPageInfo.textContent = `${start}-${end}/${totalLabel}`;
  }

  if (DOM.sortingPrevBtn) {
    DOM.sortingPrevBtn.disabled = appState.sortingOffset <= 0;
  }
  if (DOM.sortingNextBtn) {
    DOM.sortingNextBtn.disabled = !appState.sortingTruncated;
  }
}

async function selectAssetByIndex(index) {
  if (!appState.sortingAssets.length) {
    return;
  }
  if (index < 0 || index >= appState.sortingAssets.length) {
    return;
  }
  const asset = appState.sortingAssets[index];
  if (!asset) {
    return;
  }
  await previewAsset(asset.path);
  renderSortingAssetsList();
}

async function loadNextAssetsPage() {
  if (!appState.sortingTruncated) {
    return false;
  }
  appState.sortingOffset += appState.sortingLimit;
  await loadSortingWindowAssets();
  if (appState.sortingAssets.length > 0) {
    await selectAssetByIndex(0);
    return true;
  }
  return false;
}

async function loadPreviousAssetsPage() {
  if (appState.sortingOffset <= 0) {
    return false;
  }
  appState.sortingOffset = Math.max(0, appState.sortingOffset - appState.sortingLimit);
  await loadSortingWindowAssets();
  if (appState.sortingAssets.length > 0) {
    await selectAssetByIndex(appState.sortingAssets.length - 1);
    return true;
  }
  return false;
}

async function navigateAsset(delta) {
  if (!appState.sortingAssets.length) {
    return;
  }
  const current = getSelectedAssetIndex();
  const index = current >= 0 ? current : 0;
  const target = index + delta;

  if (target < 0) {
    await loadPreviousAssetsPage();
    return;
  }

  if (target >= appState.sortingAssets.length) {
    if (delta > 0) {
      await loadNextAssetsPage();
    }
    return;
  }

  await selectAssetByIndex(target);
}

async function keepCurrentAsset() {
  if (!appState.selectedAssetPath) {
    return;
  }
  const result = await api("/api/sort-keep", {
    method: "POST",
    body: { path: appState.selectedAssetPath },
  });
  if (!result.success) {
    setStepStatus(3, result.error || "Keep failed", "error");
    return;
  }
  setStepStatus(3, `Kept ${result.name || "asset"}`, "ok");
  await navigateAsset(1);
}

async function trashCurrentAsset() {
  if (!appState.selectedAssetPath) {
    return;
  }

  const currentIndex = getSelectedAssetIndex();
  const currentPath = appState.selectedAssetPath;
  const result = await api("/api/sort-trash", {
    method: "POST",
    body: { path: currentPath },
  });
  if (!result.success) {
    setStepStatus(3, result.error || "Trash failed", "error");
    return;
  }

  setStepStatus(3, `Trashed ${result.name || "asset"}`, "warn");
  const removedIndex = appState.sortingAssets.findIndex((asset) => asset.path === currentPath);
  if (removedIndex >= 0) {
    appState.sortingAssets.splice(removedIndex, 1);
  }
  appState.previewCache.delete(currentPath);

  if (appState.sortingAssets.length === 0) {
    appState.selectedAssetPath = "";
    appState.selectedAssetIndex = -1;
    DOM.sortingPreviewMeta.textContent = "No assets available";
    DOM.sortingPreview.textContent = "All assets have been trashed from the sorting window.";
    updateSortingPaginationUi();
    renderSortingAssetsList();
    return;
  }

  const nextIndex = Math.max(0, Math.min(currentIndex, appState.sortingAssets.length - 1));
  updateSortingPaginationUi();
  await selectAssetByIndex(nextIndex);
}

async function undoSortingAction() {
  const result = await api("/api/sort-undo", { method: "POST", body: {} });
  if (!result.success) {
    setStepStatus(3, result.error || "Nothing to undo", "info");
    return;
  }

  const undoneLabel = String(result.undone || "action");
  setStepStatus(3, `Undo successful (${undoneLabel})`, "ok");

  const restoredPath = String(result.path || "");

  if (undoneLabel === "trash" && restoredPath) {
    const exists = appState.sortingAssets.some((asset) => asset.path === restoredPath);
    if (!exists) {
      appState.sortingAssets.push(createAssetStubFromPath(restoredPath));
      applySortingToAssets();
      updateSortingPaginationUi();
    }
  }

  if (undoneLabel === "rename" && restoredPath) {
    const previousPath = String(result.previousPath || "");
    if (previousPath) {
      const renamed = appState.sortingAssets.find((asset) => asset.path === previousPath);
      if (renamed) {
        const stub = createAssetStubFromPath(restoredPath);
        renamed.path = stub.path;
        renamed.name = stub.name;
        renamed.ext = stub.ext;
        renamed.type = stub.type;
        appState.previewCache.delete(previousPath);
      }
    }

    const restoredExists = appState.sortingAssets.some((asset) => asset.path === restoredPath);
    if (!restoredExists) {
      appState.sortingAssets.push(createAssetStubFromPath(restoredPath));
    }
    applySortingToAssets();
    updateSortingPaginationUi();
  }

  renderSortingAssetsList();

  if (restoredPath) {
    await previewAsset(restoredPath);
    renderSortingAssetsList();
  }
}

async function saveCurrentAssets() {
  if (!appState.sortingAssets.length) {
    setStepStatus(3, "No remaining assets to save", "info");
    return;
  }

  const picker = await api("/api/browse-folder");
  if (!picker.success) {
    if (picker.cancelled) {
      setStepStatus(3, "Save cancelled", "info");
      return;
    }
    setStepStatus(3, picker.error || "Failed to choose destination", "error");
    return;
  }

  const payload = await api("/api/save-remaining-assets", {
    method: "POST",
    body: {
      destinationPath: picker.path,
      paths: appState.sortingAssets.map((asset) => asset.path),
    },
  });

  if (!payload.success) {
    setStepStatus(3, payload.error || "Failed to save assets", "error");
    return;
  }

  setStepStatus(3, `Saved ${payload.moved} asset(s) to ${payload.destinationPath}`, "ok");
  await loadSortingWindowAssets();
}

async function clearSortingTrash() {
  const payload = await api("/api/clear-trash", { method: "POST", body: {} });
  if (!payload.success) {
    setStepStatus(3, payload.error || "Failed to clear trash", "error");
    return;
  }

  setStepStatus(3, `Cleared ${payload.cleared ?? 0} item(s) from trash`, "ok");
  await loadSortingWindowAssets();
}

function setupKeyboardShortcuts() {
  document.addEventListener("keydown", async (event) => {
    if (isTypingTarget(event.target)) {
      return;
    }
    if (DOM.sortingWindowBody?.getAttribute("aria-hidden") === "true") {
      return;
    }

    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      await undoSortingAction();
      return;
    }

    if (event.code === "Space") {
      const mediaElement = appState.currentPreviewElement;
      if (
        (appState.currentPreviewType === "audio" || appState.currentPreviewType === "video") &&
        mediaElement
      ) {
        event.preventDefault();
        try {
          if (mediaElement.paused) {
            await mediaElement.play();
          } else {
            mediaElement.pause();
          }
        } catch (_err) {
          setStepStatus(3, "Cannot toggle media playback", "warn");
        }
      }
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      await navigateAsset(-1);
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      await navigateAsset(1);
      return;
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      await keepCurrentAsset();
      return;
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      await trashCurrentAsset();
      return;
    }
    if (!event.ctrlKey && !event.metaKey && !event.altKey && event.key.toLowerCase() === "s") {
      event.preventDefault();
      await saveCurrentAssets();
      return;
    }
    if (!event.ctrlKey && !event.metaKey && !event.altKey && event.key.toLowerCase() === "t") {
      event.preventDefault();
      await clearSortingTrash();
    }
  });
}

DOM.choosePathBtn?.addEventListener("click", async () => {
  try {
    const initialPath = DOM.gamePath?.value?.trim() || "";
    const qs = initialPath ? `?initialPath=${encodeURIComponent(initialPath)}` : "";
    const result = await handleApiOperation(
      "browse-folder",
      `/api/browse-folder${qs}`,
      { method: "GET" },
      (okResult) => {
        DOM.gamePath.value = okResult.path;
        appState.gamePath = okResult.path;
        setStepStatus(1, `✓ Folder selected: ${okResult.path}`, "ok");
      },
      "Could not open folder picker"
    );

    if (!result.success && result.cancelled) {
      setStepStatus(1, "Browse cancelled", "info");
    }
  } catch (err) {
    setStepStatus(1, "Browser error", "error");
  }
});

DOM.extractBtn?.addEventListener("click", async () => {
  const gamePath = DOM.gamePath?.value?.trim();
  if (!gamePath) {
    setStepStatus(1, "No game path entered", "error");
    return;
  }

  appState.extracting = true;
  DOM.extractBtn.disabled = true;
  setStepStatus(1, "Extracting archives...", "info");

  try {
    const result = await handleApiOperation(
      "extract",
      "/api/extract",
      { method: "POST", body: { gamePath, selectedExts: null } },
      (okResult) => {
        appState.extractionDone = true;
        const details = okResult.result;
        setStepStatus(
          1,
          `✓ Extracted: ${details.archivesExtracted}/${details.archivesFound} archives, ${details.copiedFiles} files`,
          "ok"
        );

        if (okResult.assetPath) {
          DOM.step2Path.value = okResult.assetPath;
          appState.step2Path = okResult.assetPath;
        }

        setTimeout(() => openAccordion(2), 300);
      },
      "Extraction failed"
    );

    if (!result.success) {
      setStepStatus(1, `Error: ${result.error}`, "error");
    }
  } catch (_err) {
    setStepStatus(1, "Extraction exception", "error");
  } finally {
    appState.extracting = false;
    DOM.extractBtn.disabled = false;
  }
});

DOM.refreshDepsBtn?.addEventListener("click", async () => {
  await syncDependencyStatuses();
});

DOM.step2BrowseBtn?.addEventListener("click", async () => {
  try {
    const assetPath = (DOM.step2Path?.value || appState.step2Path || "").trim();
    const qs = assetPath ? `?initialPath=${encodeURIComponent(assetPath)}` : "";

    const result = await handleApiOperation(
      "browse-folder-step2",
      `/api/browse-folder${qs}`,
      { method: "GET" },
      (okResult) => {
        DOM.step2Path.value = okResult.path;
        appState.step2Path = okResult.path;
        setStepStatus(2, `✓ Path: ${okResult.path}`, "ok");
      },
      "Browse failed"
    );

    if (!result.success && !result.cancelled) {
      setStepStatus(2, result.error || "Browse failed", "error");
    }
  } catch (_err) {
    setStepStatus(2, "Browse error", "error");
  }
});

DOM.scanBtn?.addEventListener("click", async () => {
  appState.scanning = true;
  DOM.scanBtn.disabled = true;
  setStepStatus(2, "Scanning for extensions...", "info");

  try {
    const scanPath = DOM.step2Path?.value || appState.gamePath || "";
    const result = await handleApiOperation(
      "scan",
      "/api/scan",
      { method: "POST", body: { assetPath: scanPath } },
      (okResult) => {
        appState.detectedExtensions = okResult.detected || [];
        appState.selectedExtensions = new Set(appState.detectedExtensions);
        renderExtensionsList();
        setStepStatus(2, `✓ Found ${appState.detectedExtensions.length} extension types`, "ok");
      },
      "Scan failed"
    );

    if (!result.success) {
      setStepStatus(2, result.error || "Scan failed", "error");
    }
  } catch (_err) {
    setStepStatus(2, "Scan error", "error");
  } finally {
    appState.scanning = false;
    DOM.scanBtn.disabled = false;
  }
});

function renderExtensionsList() {
  DOM.extensionsList.innerHTML = "";
  DOM.extensionsPlaceholder.style.display = appState.detectedExtensions.length === 0 ? "block" : "none";

  for (const ext of appState.detectedExtensions) {
    const label = document.createElement("label");
    label.className = "ext-checkbox";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.value = ext;
    checkbox.checked = appState.selectedExtensions.has(ext);
    checkbox.addEventListener("change", (e) => {
      if (e.target.checked) {
        appState.selectedExtensions.add(ext);
      } else {
        appState.selectedExtensions.delete(ext);
      }
    });

    const span = document.createElement("span");
    span.textContent = ext;

    label.appendChild(checkbox);
    label.appendChild(span);
    DOM.extensionsList.appendChild(label);
  }
}

DOM.selectAllBtn?.addEventListener("click", () => {
  appState.selectedExtensions = new Set(appState.detectedExtensions);
  renderExtensionsList();
});

DOM.selectNoneBtn?.addEventListener("click", () => {
  appState.selectedExtensions.clear();
  renderExtensionsList();
});

DOM.keepSelectedBtn?.addEventListener("click", async () => {
  if (appState.selectedExtensions.size === 0) {
    setStepStatus(2, "No extensions selected", "error");
    return;
  }

  setStepStatus(2, "Applying selected extensions...", "info");

  try {
    const result = await handleApiOperation(
      "keep-selected",
      "/api/keep-selected",
      { method: "POST", body: { selectedExts: Array.from(appState.selectedExtensions) } },
      async () => {
        setStepStatus(2, "✓ Selection applied", "ok");
        setTimeout(() => openAccordion(3), 300);
        openWorkspacePanel("sorting");
        await loadSortingWindowAssets();
      },
      "Selection failed"
    );

    if (!result.success) {
      setStepStatus(2, result.error || "Selection failed", "error");
    }
  } catch (_err) {
    setStepStatus(2, "Selection error", "error");
  }
});

async function loadSortingWindowAssets() {
  setStepStatus(3, "Loading sorting window assets...", "info");
  try {
    const result = await api(`/api/assets-window?offset=${appState.sortingOffset}&limit=${appState.sortingLimit}`);
    if (!result.success) {
      setStepStatus(3, result.error || "Failed to load assets", "error");
      return;
    }

    appState.sortingAssets = Array.isArray(result.assets) ? result.assets : [];
    appState.sortingOffset = Number(result.offset || appState.sortingOffset || 0);
    appState.sortingTruncated = Boolean(result.truncated);
    const parsedTotalCount = Number(result.totalCount);
    appState.sortingTotalCount = Number.isFinite(parsedTotalCount)
      ? parsedTotalCount
      : appState.sortingOffset + appState.sortingAssets.length;
    applySortingToAssets();
    appState.previewCache.clear();
    syncSelectedAssetIndex();
    if (appState.selectedAssetIndex < 0 && appState.sortingAssets.length > 0) {
      appState.selectedAssetPath = appState.sortingAssets[0].path;
      syncSelectedAssetIndex();
    }
    updateSortingPaginationUi();
    renderSortingAssetsList();
    if (appState.sortingTruncated) {
      setStepStatus(
        3,
        `✓ Loaded ${appState.sortingAssets.length} asset(s) from offset ${appState.sortingOffset} (page size ${appState.sortingLimit})`,
        "ok"
      );
    } else {
      setStepStatus(3, `✓ Loaded ${appState.sortingAssets.length} asset(s) from offset ${appState.sortingOffset}`, "ok");
    }

    if (appState.sortingAssets.length > 0) {
      await previewAsset(appState.selectedAssetPath);
    }
  } catch (_err) {
    setStepStatus(3, "Failed to load assets", "error");
    appState.sortingTotalCount = appState.sortingOffset + appState.sortingAssets.length;
    updateSortingPaginationUi();
  }
}

function renderSortingAssetsList() {
  DOM.sortingAssetsList.innerHTML = "";
  if (appState.sortingAssets.length === 0) {
    DOM.sortingAssetsList.innerHTML = "<div class=\"extensions-placeholder\">No assets found.</div>";
    return;
  }

  for (const asset of appState.sortingAssets) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "sorting-asset-item";
    const isActive = asset.path === appState.selectedAssetPath;
    if (isActive) {
      btn.classList.add("active");
    }

    if (isActive) {
      const nameInput = document.createElement("input");
      nameInput.type = "text";
      nameInput.className = "sorting-asset-rename-input";
      nameInput.value = asset.name;
      nameInput.setAttribute("aria-label", `Rename ${asset.name}`);

      // Keep editing interactions from re-triggering row selection while typing.
      nameInput.addEventListener("click", (event) => event.stopPropagation());
      nameInput.addEventListener("mousedown", (event) => event.stopPropagation());
      nameInput.addEventListener("dblclick", (event) => event.stopPropagation());

      nameInput.addEventListener("keydown", async (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          await renameSelectedAssetAndAdvance(asset, nameInput.value);
          return;
        }
        if (event.key === "Escape") {
          event.preventDefault();
          nameInput.value = asset.name;
          nameInput.blur();
        }
      });

      nameInput.addEventListener("blur", () => {
        nameInput.value = asset.name;
      });

      btn.appendChild(nameInput);
    } else {
      const nameSpan = document.createElement("span");
      nameSpan.className = "sorting-asset-item__name";
      nameSpan.textContent = asset.name;
      btn.appendChild(nameSpan);
    }
    
    const metaSpan = document.createElement("span");
    metaSpan.className = "sorting-asset-item__meta";
    metaSpan.textContent = `${asset.ext} • ${asset.type}`;
    btn.appendChild(metaSpan);

    btn.addEventListener("click", async () => {
      await previewAsset(asset.path);
      renderSortingAssetsList();
    });

    DOM.sortingAssetsList.appendChild(btn);
  }
}

async function renameSelectedAssetAndAdvance(asset, rawNewName) {
  const currentName = String(asset?.name || "");
  const newName = String(rawNewName || "").trim();
  const currentIndex = getSelectedAssetIndex();
  const nextPathHint = appState.sortingAssets[currentIndex + 1]?.path || "";

  if (!newName) {
    setStepStatus(3, "Rename failed: name cannot be empty", "error");
    renderSortingAssetsList();
    return;
  }

  if (newName !== currentName) {
    try {
      const result = await api("/api/sort-rename", {
        method: "POST",
        body: { path: asset.path, newName },
      });

      if (!result.success) {
        setStepStatus(3, result.error || "Rename failed", "error");
        renderSortingAssetsList();
        return;
      }

      const renamedPath = String(result.newPath || asset.path);
      const renamedExt = renamedPath.includes(".") ? `.${renamedPath.split(".").pop()}`.toLowerCase() : ".noext";
      const target = appState.sortingAssets.find((candidate) => candidate.path === asset.path);
      if (target) {
        appState.previewCache.delete(target.path);
        target.name = String(result.name || newName);
        target.path = renamedPath;
        target.ext = renamedExt;
      }

      if (appState.selectedAssetPath === asset.path) {
        appState.selectedAssetPath = renamedPath;
      }
      applySortingToAssets();
      setStepStatus(3, `Renamed to: ${result.name}`, "ok");
    } catch (_err) {
      setStepStatus(3, "Rename failed", "error");
      renderSortingAssetsList();
      return;
    }
  }
  renderSortingAssetsList();

  if (nextPathHint) {
    const nextExists = appState.sortingAssets.some((candidate) => candidate.path === nextPathHint);
    if (nextExists) {
      await previewAsset(nextPathHint);
      renderSortingAssetsList();
      return;
    }
  }

  const fallbackIndex = Math.max(0, Math.min(currentIndex, appState.sortingAssets.length - 1));
  if (appState.sortingAssets.length > 0) {
    await selectAssetByIndex(fallbackIndex);
  }
}

async function fetchPreviewPayload(encodedPath) {
  if (!encodedPath) {
    return null;
  }

  if (appState.previewCache.has(encodedPath)) {
    return appState.previewCache.get(encodedPath);
  }

  const payload = await api(`/api/assets-window-preview?path=${encodeURIComponent(encodedPath)}`);
  appState.previewCache.set(encodedPath, payload);
  return payload;
}

async function preloadAdjacentPreviews(currentIndex) {
  if (currentIndex < 0 || currentIndex >= appState.sortingAssets.length) {
    return;
  }

  const indexes = [currentIndex - 1, currentIndex + 1, currentIndex + 2];
  const tasks = [];
  for (const idx of indexes) {
    if (idx < 0 || idx >= appState.sortingAssets.length) {
      continue;
    }
    const targetPath = appState.sortingAssets[idx]?.path;
    if (!targetPath || appState.previewCache.has(targetPath)) {
      continue;
    }
    tasks.push(fetchPreviewPayload(targetPath));
  }

  if (tasks.length > 0) {
    await Promise.allSettled(tasks);
  }
}

async function previewAsset(encodedPath) {
  appState.selectedAssetPath = encodedPath;
  syncSelectedAssetIndex();
  appState.currentPreviewType = "";
  appState.currentPreviewElement = null;
  DOM.sortingPreviewMeta.textContent = "Loading preview...";
  DOM.sortingPreview.innerHTML = "";

  try {
    const payload = await fetchPreviewPayload(encodedPath);
    if (!payload.success) {
      DOM.sortingPreviewMeta.textContent = payload.error || "Preview failed";
      DOM.sortingPreview.textContent = "Could not render this asset.";
      return;
    }

    DOM.sortingPreviewMeta.textContent = `${payload.name || "asset"} (${payload.type})`;

    if (payload.type === "image") {
      DOM.sortingPreview.innerHTML = `<img src="${payload.url}" alt="${escapeHtml(payload.name || "image")}" />`;
      appState.currentPreviewType = "image";
      appState.currentPreviewElement = DOM.sortingPreview.querySelector("img");
      await preloadAdjacentPreviews(appState.selectedAssetIndex);
      return;
    }

    if (payload.type === "audio") {
      DOM.sortingPreview.innerHTML = `<audio controls src="${payload.url}"></audio>`;
      appState.currentPreviewType = "audio";
      appState.currentPreviewElement = DOM.sortingPreview.querySelector("audio");
      if (appState.currentPreviewElement && DOM.previewSpeedSelect) {
        appState.currentPreviewElement.playbackRate = Number(DOM.previewSpeedSelect.value || "1");
      }
      await preloadAdjacentPreviews(appState.selectedAssetIndex);
      return;
    }

    if (payload.type === "video") {
      DOM.sortingPreview.innerHTML = `<video controls loop src="${payload.url}"></video>`;
      appState.currentPreviewType = "video";
      appState.currentPreviewElement = DOM.sortingPreview.querySelector("video");
      if (appState.currentPreviewElement && DOM.previewSpeedSelect) {
        appState.currentPreviewElement.playbackRate = Number(DOM.previewSpeedSelect.value || "1");
      }
      await preloadAdjacentPreviews(appState.selectedAssetIndex);
      return;
    }

    if (payload.type === "text") {
      const pre = document.createElement("pre");
      pre.textContent = payload.content || "";
      DOM.sortingPreview.innerHTML = "";
      DOM.sortingPreview.appendChild(pre);
      appState.currentPreviewType = "text";
      await preloadAdjacentPreviews(appState.selectedAssetIndex);
      return;
    }

    appState.currentPreviewType = "binary";
    DOM.sortingPreview.textContent = payload.message || "Binary preview not available for this type.";

    await preloadAdjacentPreviews(appState.selectedAssetIndex);
  } catch (_err) {
    DOM.sortingPreviewMeta.textContent = "Preview failed";
    DOM.sortingPreview.textContent = "Could not render this asset.";
  }
}

DOM.refreshSortingWindowBtn?.addEventListener("click", async () => {
  await loadSortingWindowAssets();
});

DOM.saveCurrentAssetsBtn?.addEventListener("click", async () => {
  await saveCurrentAssets();
});

DOM.clearSortingTrashBtn?.addEventListener("click", async () => {
  await clearSortingTrash();
});

DOM.sortingPrevBtn?.addEventListener("click", async () => {
  await loadPreviousAssetsPage();
});

DOM.sortingNextBtn?.addEventListener("click", async () => {
  await loadNextAssetsPage();
});

DOM.sortingSortBy?.addEventListener("change", async (event) => {
  const target = event.target;
  appState.sortingSortBy = String(target?.value || "nameAsc");
  applySortingToAssets();
  renderSortingAssetsList();
  if (appState.selectedAssetPath) {
    syncSelectedAssetIndex();
  }
  if (!appState.selectedAssetPath && appState.sortingAssets.length > 0) {
    await selectAssetByIndex(0);
  }
});

DOM.openSortingPanelBtn?.addEventListener("click", async () => {
  openWorkspacePanel("sorting");
  await loadSortingWindowAssets();
});

DOM.mergerBrowseBtn?.addEventListener("click", async () => {
  const initialPath = String(DOM.mergerWorkingDir?.value || "").trim();
  const qs = initialPath ? `?initialPath=${encodeURIComponent(initialPath)}` : "";
  try {
    const payload = await api(`/api/browse-folder${qs}`);
    if (!payload.success) {
      if (!payload.cancelled) {
        setMediaMergerStatus(payload.error || "Could not browse folder", "error");
      }
      return;
    }

    appState.mergerWorkingDir = payload.path;
    DOM.mergerWorkingDir.value = payload.path;
    await refreshMergerCandidates({ resetOffset: true });
  } catch (_err) {
    setMediaMergerStatus("Folder browse failed", "error");
  }
});

DOM.mergerTransitionType?.addEventListener("change", () => {
  appState.mergerTransitionType = String(DOM.mergerTransitionType.value || "diapo");
  syncMergerTransitionFields();
});

DOM.mergerNamingPattern?.addEventListener("change", async () => {
  appState.mergerNamingPattern = String(DOM.mergerNamingPattern.value || "number-to-name");
  await refreshMergerCandidates({ resetOffset: true });
});

DOM.mergerSelectOverlayBtn?.addEventListener("click", async () => {
  try {
    const payload = await api("/api/media-merger/browse-overlay", {
      method: "POST",
      body: {
        initialPath: String(DOM.mergerOverlaySound?.value || appState.mergerWorkingDir || "").trim(),
      },
    });

    if (!payload.success) {
      if (!payload.cancelled) {
        setMediaMergerStatus(payload.error || "Overlay selection failed", "error");
      }
      return;
    }

    appState.mergerOverlaySound = String(payload.path || "");
    DOM.mergerOverlaySound.value = appState.mergerOverlaySound;
    setMediaMergerStatus("Overlay sound selected", "ok");
  } catch (_err) {
    setMediaMergerStatus("Overlay selection failed", "error");
  }
});

DOM.mergerRefreshListBtn?.addEventListener("click", async () => {
  await refreshMergerCandidates({ resetOffset: true });
});

DOM.mergerSelectAllExtBtn?.addEventListener("click", async () => {
  appState.mergerSelectedExts = new Set(appState.mergerExtensions.map((entry) => String(entry.ext || "")));
  await refreshMergerCandidates({ resetOffset: true });
});

DOM.mergerSelectNoneExtBtn?.addEventListener("click", async () => {
  appState.mergerSelectedExts.clear();
  await refreshMergerCandidates({ resetOffset: true });
});

DOM.mergerSelectAllCandidatesBtn?.addEventListener("click", () => {
  for (const candidate of appState.mergerCandidates) {
    appState.mergerSelectedCandidateNames.add(String(candidate.name || ""));
  }
  renderMergerCandidates();
});

DOM.mergerSelectNoneCandidatesBtn?.addEventListener("click", () => {
  appState.mergerSelectedCandidateNames.clear();
  renderMergerCandidates();
});

DOM.mergerPrevBtn?.addEventListener("click", async () => {
  if (appState.mergerOffset <= 0) {
    return;
  }
  appState.mergerOffset = Math.max(0, appState.mergerOffset - appState.mergerLimit);
  await refreshMergerCandidates();
});

DOM.mergerNextBtn?.addEventListener("click", async () => {
  if (!appState.mergerTruncated) {
    return;
  }
  appState.mergerOffset += appState.mergerLimit;
  await refreshMergerCandidates();
});

DOM.mergerBuildBtn?.addEventListener("click", async () => {
  const selectedCandidates = getSelectedCandidateBuildSpecs();
  if (selectedCandidates.length === 0) {
    setMediaMergerStatus("No selected media candidates", "error");
    return;
  }

  const transitionType = String(DOM.mergerTransitionType?.value || "diapo");
  const diapoDelay = Number(DOM.mergerDiapoDelay?.value || "3");
  const fadeCrossTime = Number(DOM.mergerFadeCross?.value || "0.7");
  const overlaySound = String(DOM.mergerOverlaySound?.value || "").trim();
  const outputName = String(DOM.mergerOutputName?.value || "").trim();
  const trashAfterBuild = Boolean(DOM.mergerTrashToggle?.checked);

  DOM.mergerBuildBtn.disabled = true;
  setMediaMergerStatus("Building merged media...", "info");

  try {
    const payload = await api("/api/media-merger/build", {
      method: "POST",
      body: {
        workingDir: String(DOM.mergerWorkingDir?.value || appState.mergerWorkingDir || "").trim(),
        selectedCandidates,
        namingPattern: String(DOM.mergerNamingPattern?.value || "number-to-name"),
        transitionType,
        diapoDelay,
        fadeCrossTime,
        overlaySound,
        outputName,
        trashAfterBuild,
      },
    });

    if (!payload.success) {
      setMediaMergerStatus(payload.error || "Media merge failed", "error");
      return;
    }

    setMediaMergerStatus(
      `Build complete: ${payload.outputName} (${payload.mergedCount} item(s), trashed: ${payload.trashedCount})`,
      "ok"
    );
    addLog(`[MERGER] Created ${payload.outputPath}`);

    if (trashAfterBuild) {
      await refreshMergerCandidates();
    }
  } catch (_err) {
    setMediaMergerStatus("Media merge failed", "error");
  } finally {
    DOM.mergerBuildBtn.disabled = false;
  }
});

DOM.clearLogBtn?.addEventListener("click", async () => {
  const result = await api("/api/logs/clear", { method: "POST", body: {} });
  if (!result.success) {
    addLog("[LOG] Failed to clear log");
    return;
  }

  appState.logs = [];
  appState.seenLogs.clear();
  DOM.mainLog.innerHTML = "";
  addLog("[LOG] Activity log cleared");
});

DOM.loadLogBtn?.addEventListener("click", async () => {
  const result = await api("/api/logs/load", { method: "GET" });
  if (!result.success) {
    addLog(`[LOG] Failed to load persisted logs: ${result.error || "unknown error"}`);
    return;
  }

  const lines = Array.isArray(result.logs) ? result.logs : [];
  if (lines.length === 0) {
    addLog("[LOG] No persisted log lines found");
    return;
  }

  for (const line of lines) {
    if (typeof line === "string" && line.trim()) {
      addLog(line);
    }
  }

  addLog(`[LOG] Loaded ${lines.length} line(s) from ${result.source || "latest log"}`);
});

DOM.previewFullscreenBtn?.addEventListener("click", async () => {
  const mediaElement = appState.currentPreviewElement || DOM.sortingPreview;
  if (!mediaElement || !mediaElement.requestFullscreen) {
    return;
  }
  try {
    await mediaElement.requestFullscreen();
  } catch (_err) {
    setStepStatus(3, "Fullscreen is not available", "warn");
  }
});

DOM.previewSpeedSelect?.addEventListener("change", () => {
  const mediaElement = appState.currentPreviewElement;
  if (!mediaElement) {
    return;
  }
  if (appState.currentPreviewType !== "audio" && appState.currentPreviewType !== "video") {
    return;
  }
  mediaElement.playbackRate = Number(DOM.previewSpeedSelect.value || "1");
});

DOM.previewMoreBtn?.addEventListener("click", () => {
  const mediaElement = appState.currentPreviewElement;
  if (!mediaElement) {
    return;
  }
  if (appState.currentPreviewType === "audio" || appState.currentPreviewType === "video") {
    mediaElement.muted = !mediaElement.muted;
    setStepStatus(3, mediaElement.muted ? "Media muted" : "Media unmuted", "info");
    return;
  }
  if (appState.currentPreviewType === "image") {
    mediaElement.classList.toggle("image-zoomed");
  }
});

async function initializeApp() {
  setStatus("Initializing...", "info");
  addLog("[BOOT] Initializing RPy Extractor UI");
  try {
    await api("/api/state");
    setStatus("Ready", "ok");
    addLog("[BOOT] Connected to API");
    await syncLogs();
    await syncDependencyStatuses();
    addLog("[BOOT] Activity log sync started");
    setInterval(syncLogs, 1200);

    setupAccordionHandlers();
    setupWorkspaceAccordionHandlers();
    setupKeyboardShortcuts();
    openAccordion(1);
    openWorkspacePanel("sorting");
    await initializeMediaMerger();
    addLog("[BOOT] Ready");
  } catch (err) {
    setStatus("Error", "error");
    addLog(`Initialization failed: ${err.message}`);
  }
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeApp);
} else {
  initializeApp();
}
