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
  sortingSortBy: "nameAsc",
  selectedAssetPath: "",
  selectedAssetIndex: -1,
  currentPreviewType: "",
  currentPreviewElement: null,
  previewCache: new Map(),
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

  const logLine = document.createElement("div");
  logLine.className = "log-line";
  logLine.innerHTML = `<span class="log-time">[${formatTime()}]</span> ${escapeHtml(message)}`;
  DOM.mainLog.appendChild(logLine);
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
  DOM.sortingWindowHeader.setAttribute("aria-expanded", String(openSorting));
  DOM.sortingWindowBody.setAttribute("aria-hidden", String(!openSorting));
  DOM.activityLogHeader.setAttribute("aria-expanded", String(!openSorting));
  DOM.activityLogBody.setAttribute("aria-hidden", String(openSorting));
}

function setupWorkspaceAccordionHandlers() {
  DOM.sortingWindowHeader?.addEventListener("click", () => {
    const sortingOpen = DOM.sortingWindowHeader.getAttribute("aria-expanded") === "true";
    openWorkspacePanel(sortingOpen ? "log" : "sorting");
  });

  DOM.activityLogHeader?.addEventListener("click", () => {
    const logOpen = DOM.activityLogHeader.getAttribute("aria-expanded") === "true";
    openWorkspacePanel(logOpen ? "sorting" : "log");
  });
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
  const totalLabel = appState.sortingTruncated ? `${end}+` : `${end}`;

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
  const result = await api("/api/sort-trash", {
    method: "POST",
    body: { path: appState.selectedAssetPath },
  });
  if (!result.success) {
    setStepStatus(3, result.error || "Trash failed", "error");
    return;
  }

  setStepStatus(3, `Trashed ${result.name || "asset"}`, "warn");
  await loadSortingWindowAssets();

  if (appState.sortingAssets.length > 0) {
    const nextIndex = Math.min(currentIndex, appState.sortingAssets.length - 1);
    await selectAssetByIndex(nextIndex);
  } else {
    appState.selectedAssetPath = "";
    appState.selectedAssetIndex = -1;
    DOM.sortingPreviewMeta.textContent = "No assets available";
    DOM.sortingPreview.textContent = "All assets have been trashed from the sorting window.";
  }
}

async function undoSortingAction() {
  const result = await api("/api/sort-undo", { method: "POST", body: {} });
  if (!result.success) {
    setStepStatus(3, result.error || "Nothing to undo", "info");
    return;
  }

  setStepStatus(3, "Undo successful", "ok");
  await loadSortingWindowAssets();
  if (result.path) {
    await previewAsset(result.path);
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
    if (asset.path === appState.selectedAssetPath) {
      btn.classList.add("active");
    }
    btn.innerHTML = `<span class=\"sorting-asset-item__name\">${escapeHtml(asset.name)}</span><span class=\"sorting-asset-item__meta\">${escapeHtml(asset.ext)} • ${asset.type}</span>`;
    btn.addEventListener("click", async () => {
      await previewAsset(asset.path);
      renderSortingAssetsList();
    });
    DOM.sortingAssetsList.appendChild(btn);
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
    addLog("[BOOT] Activity log sync started");
    setInterval(syncLogs, 1200);

    setupAccordionHandlers();
    setupWorkspaceAccordionHandlers();
    setupKeyboardShortcuts();
    openAccordion(1);
    openWorkspacePanel("sorting");
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
