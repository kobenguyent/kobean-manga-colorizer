// Manga Colorizer Pro - Client Application Logic

let currentSession = null;
let activeSessions = [];
let currentBatchId = null;
let eventSource = null;
let activeProvider = "resnext_generator";
let currentPreviewPageIndex = 0;

// Sub-model options per provider
const MODEL_VARIANTS = {
  resnext_generator: [
    { value: "resnext-v2-manga", label: "🧬 ResNeXt-based Manga Generator (Deep U-Net + FFDNet)" },
    { value: "resnext-chroma-hd", label: "🚀 ResNeXt High-Res Chroma Fusion (Native Detail)" },
    { value: "resnext-comicolor", label: "🎨 ResNeXt Comicolorization Pipeline" }
  ],
  google_nano: [
    { value: "nano-banana", label: "🍌 Google Nano Banana (Multimodal Vision)" },
    { value: "gemini-2.0-flash", label: "⚡ Gemini 2.0 Flash (Fast Vision)" },
    { value: "gemini-1.5-flash", label: "✨ Gemini 1.5 Flash" },
    { value: "imagen-3.0-generate-002", label: "🎨 Google Imagen 3 Colorizer" }
  ],
  apple_foundation: [
    { value: "apple-foundation-v1", label: "🍏 Apple Foundation Model (Vision Neural Engine)" },
    { value: "apple-mlx-manga", label: "🚀 Apple MLX Silicon Acceleration" },
    { value: "apple-coreml-manga", label: "🧠 Apple CoreML Pipeline" }
  ],
  local_smart: [
    { value: "semantic-manga-v2", label: "🎨 Semantic Manga Colorizer v2 (Multi-Band, Offline)" },
    { value: "semantic-anime-pastel", label: "🌸 Semantic Anime Pastel Engine" },
    { value: "semantic-dark-fantasy", label: "🦇 Semantic Dark Fantasy Engine" }
  ]
};


document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  updateModelVariants("resnext_generator");

  // Auto-restore session from sessionStorage or fetch the latest active session
  const savedSessionId = sessionStorage.getItem("active_session_id");
  const sessionPromise = savedSessionId
    ? fetch(`/api/session/${savedSessionId}`).then(res => res.ok ? res.json() : null)
    : fetch("/api/session/latest").then(res => res.ok ? res.json() : null);

  sessionPromise
    .then(data => {
      if (data && data.session_id && data.pages && data.pages.length > 0) {
        currentSession = data;
        currentBatchId = data.batch_id || null;
        sessionStorage.setItem("active_session_id", data.session_id);
        renderDashboard();
        if (data.pages[0].status === "colorized") {
          openSplitPreview(0, true);
        }
      }
    })
    .catch(() => {});

  // Fetch recent sessions to populate the documents queue
  fetch("/api/sessions")
    .then(res => res.ok ? res.json() : null)
    .then(data => {
      if (data && data.sessions && data.sessions.length > 0) {
        activeSessions = data.sessions;
        renderDocumentQueue();
      }
    })
    .catch(() => {});
});

function setupEventListeners() {
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const addMoreInput = document.getElementById("add-more-input");

  // Drag & drop handlers
  ["dragenter", "dragover"].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropzone.classList.add("dragover");
    });
  });

  ["dragleave", "drop"].forEach(eventName => {
    dropzone.addEventListener(eventName, (e) => {
      e.preventDefault();
      dropzone.classList.remove("dragover");
    });
  });

  dropzone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileSelection(files);
    }
  });

  fileInput.addEventListener("change", (e) => {
    if (fileInput.files.length > 0) {
      handleFileSelection(fileInput.files);
    }
  });

  if (addMoreInput) {
    addMoreInput.addEventListener("change", (e) => {
      if (addMoreInput.files.length > 0) {
        handleFileSelection(addMoreInput.files);
      }
    });
  }

  // Slider Value Displays with Real-time Live Preview Trigger
  document.getElementById("slider-line").addEventListener("input", (e) => {
    document.getElementById("val-line").innerText = `${e.target.value}%`;
    triggerLivePreview(350);
  });

  document.getElementById("slider-saturation").addEventListener("input", (e) => {
    document.getElementById("val-saturation").innerText = `${(e.target.value / 10).toFixed(1)}x`;
    triggerLivePreview(350);
  });

  // Style and Variant Dropdown Listeners
  document.getElementById("style-select").addEventListener("change", () => triggerLivePreview(100));
  document.getElementById("model-variant-select").addEventListener("change", () => triggerLivePreview(100));

  // Buttons
  document.getElementById("btn-start-colorize").addEventListener("click", startColorization);
  const mainExportBtn = document.getElementById("btn-export");
  if (mainExportBtn) mainExportBtn.addEventListener("click", () => exportDocument("auto"));
  document.getElementById("btn-change-file").addEventListener("click", resetUpload);

  // Setup Split Slider Dragging
  setupSplitSlider();
}

let livePreviewDebounceTimer = null;
function triggerLivePreview(delay = 300) {
  if (!currentSession || !currentSession.pages || currentSession.pages.length === 0) return;

  const splitCard = document.getElementById("split-preview-card");
  const isSplitVisible = splitCard && !splitCard.classList.contains("hidden");
  const currentPage = currentSession.pages[currentPreviewPageIndex];
  const isColorized = currentPage && currentPage.status === "colorized";

  // Auto-refresh if the preview comparator is currently open or page was previously previewed
  if (isSplitVisible || isColorized) {
    clearTimeout(livePreviewDebounceTimer);
    const titleBadge = document.getElementById("preview-page-title");
    if (titleBadge && isSplitVisible) {
      titleBadge.innerHTML = '<i class="ri-loader-4-line spinner"></i> Updating Preview...';
    }
    const colorImg = document.getElementById("split-img-colorized");
    if (colorImg && isSplitVisible) {
      colorImg.style.transition = "opacity 0.2s";
      colorImg.style.opacity = "0.6";
    }
    livePreviewDebounceTimer = setTimeout(() => {
      previewSinglePage(currentPreviewPageIndex, false);
    }, delay);
  }
}

function selectProvider(provider) {
  activeProvider = provider;
  
  // Highlight active tab
  document.querySelectorAll(".model-option").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.provider === provider);
  });

  // Update badge in header
  const badge = document.getElementById("active-model-badge");
  if (provider === "resnext_generator") {
    badge.innerHTML = '<i class="ri-dna-line"></i> ResNeXt Deep Generator';
  } else if (provider === "google_nano") {
    badge.innerHTML = '<i class="ri-sparkles-fill"></i> Google Nano Banana';
  } else if (provider === "apple_foundation") {
    badge.innerHTML = '<i class="ri-apple-fill"></i> Apple Foundation AI';
  } else {
    badge.innerHTML = '<i class="ri-palette-line"></i> Smart Local Engine';
  }

  // Show/Hide API Key input
  const apiKeyGroup = document.getElementById("api-key-group");
  apiKeyGroup.style.display = (provider === "google_nano") ? "block" : "none";

  updateModelVariants(provider);
  triggerLivePreview(100);
}

function updateModelVariants(provider) {
  const select = document.getElementById("model-variant-select");
  select.innerHTML = "";
  const variants = MODEL_VARIANTS[provider] || [];
  
  variants.forEach(v => {
    const opt = document.createElement("option");
    opt.value = v.value;
    opt.innerText = v.label;
    select.appendChild(opt);
  });
}

function toggleApiKeyVisibility() {
  const input = document.getElementById("api-key-input");
  const icon = document.getElementById("api-key-toggle-icon");
  if (input.type === "password") {
    input.type = "text";
    icon.className = "ri-eye-off-line";
  } else {
    input.type = "password";
    icon.className = "ri-eye-line";
  }
}

async function handleFileSelection(fileOrFiles) {
  const allowed = ["pdf", "epub", "png", "jpg", "jpeg", "webp", "bmp", "gif", "tiff", "zip"];
  const fileList = Array.from(fileOrFiles instanceof FileList ? fileOrFiles : (Array.isArray(fileOrFiles) ? fileOrFiles : [fileOrFiles]));

  const validFiles = fileList.filter(f => {
    const ext = f.name.split(".").pop().toLowerCase();
    return allowed.includes(ext);
  });

  if (validFiles.length === 0) {
    showToast("Supported formats: .pdf, .epub, images (.png, .jpg, .webp) & .zip", "error");
    return;
  }

  // Show dropzone upload loading UI
  const idleContent = document.getElementById("dropzone-idle-content");
  const loadingContent = document.getElementById("dropzone-loading-content");
  const filenameText = document.getElementById("upload-filename-text");

  if (idleContent) idleContent.classList.add("hidden");
  if (loadingContent) loadingContent.classList.remove("hidden");
  if (filenameText) {
    filenameText.innerText = validFiles.length === 1
      ? `Processing ${validFiles[0].name}...`
      : `Processing ${validFiles.length} manga documents...`;
  }

  showToast(`Uploading & extracting ${validFiles.length} file(s)...`, "info");

  const formData = new FormData();
  if (currentBatchId) {
    formData.append("batch_id", currentBatchId);
  }
  validFiles.forEach(f => formData.append("files", f));

  try {
    const resp = await fetch("/api/upload", {
      method: "POST",
      body: formData
    });

    const data = await resp.json();
    if (resp.ok && data.status === "success") {
      currentSession = data;
      currentBatchId = data.batch_id || currentBatchId;
      sessionStorage.setItem("active_session_id", data.session_id);
      if (currentBatchId) {
        sessionStorage.setItem("active_batch_id", currentBatchId);
      }

      if (data.sessions && data.sessions.length > 0) {
        data.sessions.forEach(newSess => {
          const existingIdx = activeSessions.findIndex(s => s.session_id === newSess.session_id);
          if (existingIdx !== -1) {
            activeSessions[existingIdx] = newSess;
          } else {
            activeSessions.push(newSess);
          }
        });
      } else {
        if (!activeSessions.some(s => s.session_id === data.session_id)) {
          activeSessions.push({
            session_id: data.session_id,
            filename: data.filename,
            ext: data.ext || "." + data.filename.split(".").pop(),
            total_pages: data.total_pages,
            status: data.status || "idle",
            processed_count: data.processed_count || 0
          });
        }
      }

      renderDashboard();
      renderDocumentQueue();
      showToast(`Uploaded ${validFiles.length} file(s) with ${data.total_pages} total pages!`, "success");
    } else {
      showToast(data.detail || "Upload failed.", "error");
      if (idleContent) idleContent.classList.remove("hidden");
      if (loadingContent) loadingContent.classList.add("hidden");
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
    if (idleContent) idleContent.classList.remove("hidden");
    if (loadingContent) loadingContent.classList.add("hidden");
  }
}

function renderDocumentQueue() {
  const queueList = document.getElementById("doc-queue-list");
  const queueBadge = document.getElementById("doc-queue-badge");
  const batchColorizeBtn = document.getElementById("btn-start-batch-colorize");
  const batchCountText = document.getElementById("batch-count-text");
  const sidebarBatchExport = document.getElementById("sidebar-batch-export");
  const bannerBatchBtn = document.getElementById("btn-export-batch-banner");
  const bannerBatchCount = document.getElementById("banner-batch-count");

  if (!queueList) return;

  const count = activeSessions.length;
  if (queueBadge) {
    queueBadge.innerText = `${count} Document${count > 1 ? "s" : ""}`;
  }

  const hasMultiple = count > 1;
  if (hasMultiple) {
    queueList.classList.remove("hidden");
    if (batchColorizeBtn) {
      batchColorizeBtn.classList.remove("hidden");
      if (batchCountText) batchCountText.innerText = count;
    }
    if (sidebarBatchExport) sidebarBatchExport.classList.remove("hidden");
    if (bannerBatchBtn) {
      bannerBatchBtn.classList.remove("hidden");
      if (bannerBatchCount) bannerBatchCount.innerText = count;
    }
  } else {
    queueList.classList.add("hidden");
    if (batchColorizeBtn) batchColorizeBtn.classList.add("hidden");
    if (sidebarBatchExport) sidebarBatchExport.classList.add("hidden");
    if (bannerBatchBtn) bannerBatchBtn.classList.add("hidden");
  }

  queueList.innerHTML = "";
  activeSessions.forEach((sess) => {
    const item = document.createElement("div");
    const isActive = currentSession && currentSession.session_id === sess.session_id;
    item.className = `doc-queue-item ${isActive ? "active" : ""}`;
    item.onclick = () => switchActiveDocument(sess.session_id);

    const fn = (sess.filename || "").toLowerCase();
    let iconHTML = '<i class="ri-image-fill" style="color: #06b6d4;"></i>';
    if (fn.endsWith(".epub")) {
      iconHTML = '<i class="ri-book-2-fill" style="color: #8b5cf6;"></i>';
    } else if (fn.endsWith(".pdf")) {
      iconHTML = '<i class="ri-file-pdf-fill" style="color: #ef4444;"></i>';
    } else if (fn.endsWith(".zip")) {
      iconHTML = '<i class="ri-folder-zip-fill" style="color: #eab308;"></i>';
    }

    const statusBadgeClass = sess.status === "completed" ? "status-colorized" : "status-pending";
    const statusText = sess.status === "completed" ? "Ready" : `${sess.processed_count || 0}/${sess.total_pages || 0}`;

    item.innerHTML = `
      <div class="doc-queue-icon">${iconHTML}</div>
      <div class="doc-queue-info">
        <div class="doc-queue-name" title="${sess.filename}">${sess.filename}</div>
        <div class="doc-queue-meta">
          <span>${sess.total_pages} pages</span>
          <span class="page-status-badge ${statusBadgeClass}" style="font-size: 0.68rem; padding: 1px 6px;">${statusText}</span>
        </div>
      </div>
      <button class="btn-icon doc-delete-btn" title="Delete ${sess.filename}" onclick="deleteDocument(event, '${sess.session_id}')">
        <i class="ri-delete-bin-line"></i>
      </button>
      <i class="ri-arrow-right-s-line" style="color: var(--text-secondary); margin-left: 2px;"></i>
    `;
    queueList.appendChild(item);
  });
}

async function switchActiveDocument(sessionId) {
  if (currentSession && currentSession.session_id === sessionId) return;

  showToast("Switching active document...", "info");
  try {
    const resp = await fetch(`/api/session/${sessionId}`);
    const data = await resp.json();
    if (resp.ok && data.session_id) {
      currentSession = data;
      sessionStorage.setItem("active_session_id", data.session_id);

      const idx = activeSessions.findIndex(s => s.session_id === sessionId);
      if (idx !== -1) {
        activeSessions[idx] = { ...activeSessions[idx], ...data };
      }

      renderDashboard();
      renderDocumentQueue();
      if (data.pages && data.pages.length > 0 && data.pages[0].status === "colorized") {
        openSplitPreview(0, true);
      }
    }
  } catch (err) {
    showToast(`Failed to switch document: ${err.message}`, "error");
  }
}

function renderDashboard() {
  document.getElementById("upload-section").classList.add("hidden");
  document.getElementById("dashboard-section").classList.remove("hidden");

  document.getElementById("doc-filename").innerText = currentSession.filename;
  document.getElementById("doc-total-pages").innerText = currentSession.total_pages;

  const iconBox = document.getElementById("file-type-icon");
  const fn = currentSession.filename.toLowerCase();
  if (fn.endsWith(".epub")) {
    iconBox.innerHTML = '<i class="ri-book-2-fill" style="color: #8b5cf6;"></i>';
  } else if (fn.endsWith(".pdf")) {
    iconBox.innerHTML = '<i class="ri-file-pdf-fill" style="color: #ef4444;"></i>';
  } else if (fn.endsWith(".zip")) {
    iconBox.innerHTML = '<i class="ri-folder-zip-fill" style="color: #eab308;"></i>';
  } else {
    iconBox.innerHTML = '<i class="ri-image-fill" style="color: #06b6d4;"></i>';
  }

  document.getElementById("gallery-total-count").innerText = currentSession.total_pages;
  renderGalleryGrid();
  renderDocumentQueue();
}

function renderGalleryGrid() {
  const grid = document.getElementById("pages-grid");
  grid.innerHTML = "";

  let colorizedCount = 0;

  currentSession.pages.forEach((page, idx) => {
    if (page.status === "colorized") colorizedCount++;

    const card = document.createElement("div");
    card.className = "page-card";
    card.id = `page-card-${idx}`;
    card.onclick = () => openSplitPreview(idx);

    const thumbUrl = page.colorized_url || `/api/session/${currentSession.session_id}/image/original/${page.filename}`;
    
    const dimText = (page.width && page.height) ? `${page.width} × ${page.height}` : "";
    card.innerHTML = `
      <div class="page-thumb-container">
        <img class="page-thumb-img" id="page-img-${idx}" src="${thumbUrl}" alt="${page.display_name}" loading="lazy" />
        <button class="page-delete-btn" title="Delete this page" onclick="deletePage(event, ${idx})">
          <i class="ri-delete-bin-line"></i>
        </button>
        <span class="page-status-badge status-${page.status}" id="page-badge-${idx}">
          ${page.status.toUpperCase()}
        </span>
      </div>
      <div class="page-card-footer">
        <span class="page-card-title">${page.display_name}</span>
        ${dimText ? `<span class="page-card-dim">${dimText}</span>` : '<i class="ri-eye-line"></i>'}
      </div>
    `;
    grid.appendChild(card);
  });

  document.getElementById("colorized-count").innerText = colorizedCount;

  // Unhide export banners and update count badge whenever colorized pages are available
  const exportCard = document.getElementById("export-card");
  const sidebarExportCard = document.getElementById("sidebar-export-card");
  const exportBadge = document.getElementById("export-badge-count");

  if (exportBadge) {
    exportBadge.innerText = `${colorizedCount} Ready`;
  }

  if (colorizedCount > 0 || (currentSession && currentSession.status === "completed")) {
    if (exportCard) exportCard.classList.remove("hidden");
    if (sidebarExportCard) sidebarExportCard.classList.remove("hidden");
  } else {
    if (exportCard) exportCard.classList.add("hidden");
    if (sidebarExportCard) sidebarExportCard.classList.add("hidden");
  }
}

async function startColorization() {
  if (!currentSession) return;

  const modelVariant = document.getElementById("model-variant-select").value;
  const apiKey = document.getElementById("api-key-input").value;
  const style = document.getElementById("style-select").value;
  const linePreserve = parseFloat(document.getElementById("slider-line").value) / 100.0;
  const saturation = parseFloat(document.getElementById("slider-saturation").value) / 10.0;

  const payload = {
    session_id: currentSession.session_id,
    model_provider: activeProvider,
    model_name: modelVariant,
    api_key: apiKey,
    style: style,
    saturation: saturation,
    contrast: 1.1,
    line_preserve: linePreserve
  };

  // UI state updates
  document.getElementById("progress-card").classList.remove("hidden");
  document.getElementById("export-card").classList.add("hidden");
  document.getElementById("btn-start-colorize").disabled = true;

  const providerNames = {
    resnext_generator: "ResNeXt Deep Generator",
    google_nano: "Google Nano Banana",
    apple_foundation: "Apple Foundation Model",
    local_smart: "Smart Local Engine"
  };

  document.getElementById("progress-subtext").innerText = `Using ${providerNames[activeProvider]} (${modelVariant})`;

  try {
    const resp = await fetch("/api/colorize/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (resp.ok) {
      subscribeToProgressStream();
    } else {
      const err = await resp.json();
      showToast(err.detail || "Failed to start colorization.", "error");
      document.getElementById("btn-start-colorize").disabled = false;
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
    document.getElementById("btn-start-colorize").disabled = false;
  }
}

function subscribeToProgressStream(sessionId = null) {
  if (eventSource) eventSource.close();

  const targetId = sessionId || (currentSession ? currentSession.session_id : null);
  if (!targetId) return;

  eventSource = new EventSource(`/api/colorize/stream/${targetId}`);

  eventSource.onmessage = (e) => {
    const data = JSON.parse(e.data);

    if (data.type === "page_update") {
      const idx = data.page_index;
      if (currentSession && currentSession.session_id === targetId && currentSession.pages && currentSession.pages[idx]) {
        const pageInfo = currentSession.pages[idx];
        pageInfo.status = data.status;

        if (data.colorized_url) {
          pageInfo.colorized_url = data.colorized_url;
          const imgElem = document.getElementById(`page-img-${idx}`);
          if (imgElem) imgElem.src = `${data.colorized_url}?t=${Date.now()}`;
        }

        const badge = document.getElementById(`page-badge-${idx}`);
        if (badge) {
          badge.className = `page-status-badge status-${data.status}`;
          badge.innerText = data.status.toUpperCase();
        }

        // Update progress bar
        if (data.processed_count !== undefined) {
          const pct = Math.round((data.processed_count / currentSession.total_pages) * 100);
          const barFill = document.getElementById("progress-bar-fill");
          if (barFill) barFill.style.width = `${pct}%`;
          const counterText = document.getElementById("progress-counter-text");
          if (counterText) counterText.innerText = `${data.processed_count} / ${currentSession.total_pages}`;
          const countText = document.getElementById("colorized-count");
          if (countText) countText.innerText = data.processed_count;
        }
      }
    } else if (data.type === "completed") {
      eventSource.close();
      const progCard = document.getElementById("progress-card");
      if (progCard) progCard.classList.add("hidden");
      const expCard = document.getElementById("export-card");
      if (expCard) expCard.classList.remove("hidden");
      const sidebarExportCard = document.getElementById("sidebar-export-card");
      if (sidebarExportCard) sidebarExportCard.classList.remove("hidden");
      const btnStart = document.getElementById("btn-start-colorize");
      if (btnStart) btnStart.disabled = false;
      showToast("Colorization complete!", "success");
      if (typeof renderDocumentQueue === "function") renderDocumentQueue();
    } else if (data.type === "cancelled") {
      eventSource.close();
      const progCard = document.getElementById("progress-card");
      if (progCard) progCard.classList.add("hidden");
      const btnStart = document.getElementById("btn-start-colorize");
      if (btnStart) btnStart.disabled = false;

      // Re-render gallery grid to reset pending statuses
      renderGalleryGrid();

      // Show export card if at least one page was colorized before cancelling
      const processedCount = data.processed_count || 0;
      if (processedCount > 0) {
        const expCard = document.getElementById("export-card");
        if (expCard) expCard.classList.remove("hidden");
        const sidebarExportCard = document.getElementById("sidebar-export-card");
        if (sidebarExportCard) sidebarExportCard.classList.remove("hidden");
      }

      showToast(`Colorization cancelled (${processedCount} pages colorized).`, "info");
    }
  };

  eventSource.onerror = (err) => {
    console.error("SSE stream error:", err);
    eventSource.close();
  };
}

// Global aliases to ensure availability across all modules and scopes
const connectProgressStream = subscribeToProgressStream;
window.subscribeToProgressStream = subscribeToProgressStream;
window.connectProgressStream = subscribeToProgressStream;

async function cancelColorization() {
  if (!currentSession) return;

  const btnCancel = document.getElementById("btn-cancel-colorize");
  if (btnCancel) {
    btnCancel.disabled = true;
    btnCancel.innerHTML = '<i class="ri-loader-4-line"></i> Cancelling...';
  }

  try {
    const resp = await fetch(`/api/colorize/cancel/${currentSession.session_id}`, {
      method: "POST"
    });
    if (resp.ok) {
      showToast("Colorization cancelled.", "info");
      document.getElementById("progress-card").classList.add("hidden");
      document.getElementById("btn-start-colorize").disabled = false;
      if (btnCancel) {
        btnCancel.disabled = false;
        btnCancel.innerHTML = '<i class="ri-close-circle-line"></i> Cancel';
      }
    }
  } catch (err) {
    showToast(`Cancel error: ${err.message}`, "error");
    if (btnCancel) {
      btnCancel.disabled = false;
      btnCancel.innerHTML = '<i class="ri-close-circle-line"></i> Cancel';
    }
  }
}

async function previewCurrentPage() {
  await previewSinglePage(currentPreviewPageIndex, true);
}

async function previewSinglePage(pageIdx, showToastFeedback = true) {
  if (!currentSession) return;

  const modelVariant = document.getElementById("model-variant-select").value;
  const apiKey = document.getElementById("api-key-input").value;
  const style = document.getElementById("style-select").value;
  const linePreserve = parseFloat(document.getElementById("slider-line").value) / 100.0;
  const saturation = parseFloat(document.getElementById("slider-saturation").value) / 10.0;

  const page = currentSession.pages[pageIdx];
  if (showToastFeedback) {
    showToast(`Generating preview for ${page.display_name}...`, "info");
  }

  const btnPreview = document.getElementById("btn-preview-page");
  if (btnPreview && showToastFeedback) {
    btnPreview.disabled = true;
    btnPreview.innerHTML = '<i class="ri-loader-4-line spinner"></i> Rendering Preview...';
  }

  const titleBadge = document.getElementById("preview-page-title");
  if (titleBadge) {
    titleBadge.innerHTML = `<i class="ri-loader-4-line spinner"></i> ${page.display_name} (Updating...)`;
  }

  const payload = {
    session_id: currentSession.session_id,
    page_index: pageIdx,
    model_provider: activeProvider,
    model_name: modelVariant,
    api_key: apiKey,
    style: style,
    saturation: saturation,
    contrast: 1.1,
    line_preserve: linePreserve
  };

  try {
    const resp = await fetch("/api/colorize/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await resp.json();
    if (resp.ok && data.status === "success") {
      page.status = "colorized";
      page.colorized_url = data.colorized_url;
      const ts = Date.now();
      
      // Update page card thumbnail in gallery
      const imgElem = document.getElementById(`page-img-${pageIdx}`);
      if (imgElem) imgElem.src = `${data.colorized_url}?t=${ts}`;

      const badge = document.getElementById(`page-badge-${pageIdx}`);
      if (badge) {
        badge.className = "page-status-badge status-colorized";
        badge.innerText = "COLORIZED";
      }

      // Update split comparator images directly
      const origImg = document.getElementById("split-img-original");
      const colorImg = document.getElementById("split-img-colorized");
      const origUrl = `/api/session/${currentSession.session_id}/image/original/${page.filename}`;
      
      if (origImg) origImg.src = origUrl;
      if (colorImg) {
        colorImg.style.opacity = "1.0";
        colorImg.src = `${data.colorized_url}?t=${ts}`;
      }

      const styleSelect = document.getElementById("style-select");
      const selectedStyleText = styleSelect.options[styleSelect.selectedIndex]?.text?.split(" ")[1] || style;
      if (titleBadge) {
        titleBadge.innerText = `${page.display_name} • ${selectedStyleText}`;
      }

      // Open in Before / After Comparator (prevent jarring scroll when auto-triggered by sliders)
      openSplitPreview(pageIdx, !showToastFeedback);

      // Unhide export options since at least one colorized page is ready
      const exportCard = document.getElementById("export-card");
      const sidebarExportCard = document.getElementById("sidebar-export-card");
      if (exportCard) exportCard.classList.remove("hidden");
      if (sidebarExportCard) sidebarExportCard.classList.remove("hidden");

      if (showToastFeedback) {
        showToast(`Preview updated for ${page.display_name}!`, "success");
      }
    } else {
      showToast(data.detail || "Preview failed.", "error");
    }
  } catch (err) {
    showToast(`Preview error: ${err.message}`, "error");
  } finally {
    const colorImg = document.getElementById("split-img-colorized");
    if (colorImg) colorImg.style.opacity = "1.0";
    if (btnPreview) {
      btnPreview.disabled = false;
      btnPreview.innerHTML = `<i class="ri-sparkles-line"></i> Preview Page ${pageIdx + 1}`;
    }
  }
}

function openSplitPreview(pageIdx, preventScroll = false) {
  currentPreviewPageIndex = pageIdx;
  const page = currentSession.pages[pageIdx];

  const origUrl = `/api/session/${currentSession.session_id}/image/original/${page.filename}`;
  const colorUrl = page.colorized_url || origUrl;

  const origImg = document.getElementById("split-img-original");
  const colorImg = document.getElementById("split-img-colorized");
  const container = document.getElementById("split-container");

  const syncContainerRatio = (w, h) => {
    if (container && w > 0 && h > 0) {
      container.style.aspectRatio = `${w} / ${h}`;
    }
  };

  // Immediate aspect ratio lock from page metadata
  if (page.width && page.height) {
    syncContainerRatio(page.width, page.height);
  }

  if (origImg) {
    origImg.onload = () => {
      if (origImg.naturalWidth && origImg.naturalHeight) {
        syncContainerRatio(origImg.naturalWidth, origImg.naturalHeight);
      }
      setSplitPosition(currentSplitPct);
    };
    origImg.src = origUrl;
  }
  if (colorImg) {
    colorImg.onload = () => {
      if (colorImg.naturalWidth && colorImg.naturalHeight) {
        syncContainerRatio(colorImg.naturalWidth, colorImg.naturalHeight);
      }
      setSplitPosition(currentSplitPct);
    };
    colorImg.style.opacity = "1.0";
    colorImg.src = `${colorUrl}?t=${Date.now()}`;
  }

  const styleSelect = document.getElementById("style-select");
  const selectedStyleText = styleSelect.options[styleSelect.selectedIndex]?.text?.split(" ")[1] || "";
  const titleBadge = document.getElementById("preview-page-title");
  if (titleBadge) {
    const dim = (page.width && page.height) ? ` [${page.width}×${page.height}]` : "";
    titleBadge.innerText = selectedStyleText ? `${page.display_name}${dim} • ${selectedStyleText}` : `${page.display_name}${dim}`;
  }

  const btnPreview = document.getElementById("btn-preview-page");
  if (btnPreview) {
    btnPreview.innerHTML = `<i class="ri-sparkles-line"></i> Preview ${page.display_name}`;
  }

  const splitCard = document.getElementById("split-preview-card");
  const wasHidden = splitCard.classList.contains("hidden");
  splitCard.classList.remove("hidden");

  if (!preventScroll || wasHidden) {
    splitCard.scrollIntoView({ behavior: 'smooth' });
  }

  // Reset handle with container dimensions applied
  setSplitPosition(currentSplitPct);
}

function closeSplitPreview() {
  document.getElementById("split-preview-card").classList.add("hidden");
}

let currentSplitPct = 50;

function setupSplitSlider() {
  const container = document.getElementById("split-container");
  let isDragging = false;

  const onMove = (clientX) => {
    if (!isDragging) return;
    const rect = container.getBoundingClientRect();
    let x = clientX - rect.left;
    if (x < 0) x = 0;
    if (x > rect.width) x = rect.width;
    const pct = (x / rect.width) * 100;
    setSplitPosition(pct);
  };

  container.addEventListener("mousedown", (e) => {
    isDragging = true;
    onMove(e.clientX);
  });

  window.addEventListener("mousemove", (e) => onMove(e.clientX));
  window.addEventListener("mouseup", () => { isDragging = false; });

  // Touch support
  container.addEventListener("touchstart", (e) => {
    isDragging = true;
    onMove(e.touches[0].clientX);
  });
  window.addEventListener("touchmove", (e) => {
    if (isDragging) onMove(e.touches[0].clientX);
  });
  window.addEventListener("touchend", () => { isDragging = false; });

  // Window resize handler keeps image layers aligned
  window.addEventListener("resize", () => setSplitPosition(currentSplitPct));
}

function setSplitPosition(pct) {
  currentSplitPct = pct;
  const container = document.getElementById("split-container");
  const overlay = document.getElementById("split-overlay");
  const handle = document.getElementById("split-handle");
  const overlayImg = document.getElementById("split-img-original");

  if (overlay) overlay.style.width = `${pct}%`;
  if (handle) handle.style.left = `${pct}%`;

  if (container && overlayImg) {
    const w = container.clientWidth;
    const h = container.clientHeight;
    if (w > 0 && h > 0) {
      overlayImg.style.width = `${w}px`;
      overlayImg.style.height = `${h}px`;
    }
  }
}

async function exportDocument(format = "auto") {
  if (!currentSession) return;

  const formatLabels = {
    pdf: "PDF document",
    epub: "EPUB e-book",
    zip: "ZIP images archive",
    auto: "colorized document"
  };
  const label = formatLabels[format] || format;

  showToast(`Building ${label}...`, "info");

  // Disable all export buttons while processing
  const exportButtons = Array.from(document.querySelectorAll("button")).filter(btn => 
    (btn.id && btn.id.includes("export")) || (btn.getAttribute("onclick") && btn.getAttribute("onclick").includes("exportDocument"))
  );
  exportButtons.forEach(btn => btn.disabled = true);

  const activeBtns = [
    document.getElementById(`btn-export-${format}`),
    document.getElementById(`btn-sidebar-export-${format}`),
    format === 'auto' ? document.getElementById("btn-export") : null
  ].filter(Boolean);

  const origBtnStates = activeBtns.map(btn => ({ btn, html: btn.innerHTML }));
  activeBtns.forEach(btn => {
    btn.innerHTML = `<i class="ri-loader-4-line spinner"></i> Exporting...`;
  });

  try {
    const queryParam = format && format !== "auto" ? `?format=${encodeURIComponent(format)}` : "";
    const resp = await fetch(`/api/export/${currentSession.session_id}${queryParam}`, {
      method: "POST"
    });

    const data = await resp.json();
    if (resp.ok && data.download_url) {
      showToast(`Exported ${data.filename}! Downloading...`, "success");
      
      // Trigger download
      const a = document.createElement("a");
      a.href = data.download_url;
      a.download = data.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } else {
      showToast(data.detail || "Export failed.", "error");
    }
  } catch (err) {
    showToast(`Export error: ${err.message}`, "error");
  } finally {
    exportButtons.forEach(btn => btn.disabled = false);
    origBtnStates.forEach(({ btn, html }) => {
      btn.innerHTML = html;
    });
  }
}

async function startBatchColorization() {
  if (!activeSessions || activeSessions.length === 0) return;

  const modelVariant = document.getElementById("model-variant-select").value;
  const apiKey = document.getElementById("api-key-input").value;
  const style = document.getElementById("style-select").value;
  const linePreserve = parseFloat(document.getElementById("slider-line").value) / 100.0;
  const saturation = parseFloat(document.getElementById("slider-saturation").value) / 10.0;

  const sessionIds = activeSessions.map(s => s.session_id);
  showToast(`Starting batch colorization for ${sessionIds.length} documents...`, "info");

  try {
    const resp = await fetch("/api/colorize/batch/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_ids: sessionIds,
        model_provider: activeProvider,
        model_name: modelVariant,
        api_key: apiKey,
        style: style,
        saturation: saturation,
        contrast: 1.1,
        line_preserve: linePreserve
      })
    });

    const data = await resp.json();
    if (resp.ok && data.status === "started") {
      showToast(data.message, "success");
      if (currentSession) {
        const progCard = document.getElementById("progress-card");
        if (progCard) progCard.classList.remove("hidden");
        const expCard = document.getElementById("export-card");
        if (expCard) expCard.classList.add("hidden");
        const btnStart = document.getElementById("btn-start-colorize");
        if (btnStart) btnStart.disabled = true;

        subscribeToProgressStream(currentSession.session_id);
      }
    } else {
      showToast(data.detail || "Batch colorization failed.", "error");
    }
  } catch (err) {
    showToast(`Batch error: ${err.message}`, "error");
  }
}

async function exportBatch(format = "auto") {
  if (!activeSessions || activeSessions.length === 0) return;

  const sessionIds = activeSessions.map(s => s.session_id);
  const formatNames = {
    auto: "collection (preserving original formats)",
    epub: "all documents as EPUBs",
    pdf: "all documents as PDFs"
  };
  const label = formatNames[format] || format;

  showToast(`Building batch export: ${label}...`, "info");

  const batchBtns = Array.from(document.querySelectorAll("[id*='batch-export'], #btn-export-batch-banner"));
  batchBtns.forEach(btn => btn.disabled = true);

  try {
    const resp = await fetch("/api/export/batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_ids: sessionIds,
        format: format
      })
    });

    const data = await resp.json();
    if (resp.ok && data.download_url) {
      showToast(`Batch exported: ${data.filename}! Downloading...`, "success");
      const a = document.createElement("a");
      a.href = data.download_url;
      a.download = data.filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
    } else {
      showToast(data.detail || "Batch export failed.", "error");
    }
  } catch (err) {
    showToast(`Batch export error: ${err.message}`, "error");
  } finally {
    batchBtns.forEach(btn => btn.disabled = false);
  }
}

// ─── File & Page Deletion Handlers ──────────────────────────────────

async function deleteDocument(event, sessionId) {
  if (event) event.stopPropagation();

  const sessToDelete = activeSessions.find(s => s.session_id === sessionId) || (currentSession?.session_id === sessionId ? currentSession : null);
  const docName = sessToDelete ? sessToDelete.filename : "this document";

  if (!confirm(`Are you sure you want to delete "${docName}"? This will permanently delete the file and all its pages.`)) {
    return;
  }

  showToast(`Deleting "${docName}"...`, "info");

  try {
    const resp = await fetch(`/api/session/${sessionId}`, { method: "DELETE" });
    const data = await resp.json();

    if (resp.ok) {
      activeSessions = activeSessions.filter(s => s.session_id !== sessionId);

      if (currentSession && currentSession.session_id === sessionId) {
        if (activeSessions.length > 0) {
          await switchActiveDocument(activeSessions[0].session_id);
          showToast(`Deleted "${docName}". Switched to "${activeSessions[0].filename}".`, "success");
        } else {
          resetUpload();
          showToast(`Deleted "${docName}". All files removed.`, "success");
        }
      } else {
        renderDocumentQueue();
        showToast(`Deleted "${docName}".`, "success");
      }
    } else {
      showToast(`Failed to delete document: ${data.detail || "Error"}`, "error");
    }
  } catch (err) {
    showToast(`Error deleting document: ${err.message}`, "error");
  }
}

async function deleteActiveDocument(event) {
  if (event) event.stopPropagation();
  if (!currentSession) return;
  await deleteDocument(event, currentSession.session_id);
}

async function deletePage(event, pageIdx) {
  if (event) event.stopPropagation();
  if (!currentSession || !currentSession.pages || !currentSession.pages[pageIdx]) return;

  const page = currentSession.pages[pageIdx];
  const pageName = page.display_name || `Page ${pageIdx + 1}`;

  if (!confirm(`Delete ${pageName}? This will remove it from the document.`)) {
    return;
  }

  try {
    const resp = await fetch(`/api/session/${currentSession.session_id}/page/${pageIdx}`, {
      method: "DELETE"
    });
    const data = await resp.json();

    if (resp.ok && data.status === "success") {
      currentSession = data.session;

      // Update activeSessions reference
      const sessIdx = activeSessions.findIndex(s => s.session_id === currentSession.session_id);
      if (sessIdx !== -1) {
        activeSessions[sessIdx] = { ...activeSessions[sessIdx], ...data.session };
      }

      // Re-render dashboard and queue
      renderDashboard();
      renderDocumentQueue();

      // If comparator is open, update or close it
      if (currentPreviewPageIndex === pageIdx) {
        if (currentSession.pages.length > 0) {
          const nextIdx = Math.min(pageIdx, currentSession.pages.length - 1);
          openSplitPreview(nextIdx, true);
        } else {
          closeSplitPreview();
        }
      } else if (currentPreviewPageIndex > pageIdx) {
        currentPreviewPageIndex--;
      }

      showToast(`Deleted ${pageName}.`, "success");
    } else {
      showToast(`Failed to delete page: ${data.detail || "Error"}`, "error");
    }
  } catch (err) {
    showToast(`Error deleting page: ${err.message}`, "error");
  }
}

async function deleteCurrentPreviewPage(event) {
  if (event) event.stopPropagation();
  if (typeof currentPreviewPageIndex !== "number") return;
  await deletePage(event, currentPreviewPageIndex);
}

async function clearAllDocuments(event) {
  if (event) event.stopPropagation();

  const count = activeSessions.length || (currentSession ? 1 : 0);
  if (!confirm(`Are you sure you want to delete all ${count} document(s) and files? This cannot be undone.`)) {
    return;
  }

  showToast("Deleting all documents...", "info");

  try {
    const resp = await fetch("/api/sessions", { method: "DELETE" });
    const data = await resp.json();

    if (resp.ok) {
      resetUpload();
      showToast("All documents and files deleted successfully.", "success");
    } else {
      showToast(`Failed to delete documents: ${data.detail || "Error"}`, "error");
    }
  } catch (err) {
    showToast(`Error deleting documents: ${err.message}`, "error");
  }
}

function resetUpload() {
  sessionStorage.removeItem("active_session_id");
  sessionStorage.removeItem("active_batch_id");
  if (eventSource) eventSource.close();
  currentSession = null;
  activeSessions = [];
  currentBatchId = null;
  document.getElementById("dashboard-section").classList.add("hidden");
  document.getElementById("upload-section").classList.remove("hidden");
  
  const idleContent = document.getElementById("dropzone-idle-content");
  const loadingContent = document.getElementById("dropzone-loading-content");
  if (idleContent) idleContent.classList.remove("hidden");
  if (loadingContent) loadingContent.classList.add("hidden");

  document.getElementById("file-input").value = "";
  const addMore = document.getElementById("add-more-input");
  if (addMore) addMore.value = "";
}

function showToast(message, type = "info") {
  const toast = document.getElementById("toast");
  const msgElem = document.getElementById("toast-message");
  const iconElem = document.getElementById("toast-icon");

  msgElem.innerText = message;
  
  if (type === "success") {
    iconElem.className = "ri-checkbox-circle-line";
    toast.style.borderColor = "var(--accent-green)";
  } else if (type === "error") {
    iconElem.className = "ri-error-warning-line";
    toast.style.borderColor = "#ef4444";
  } else {
    iconElem.className = "ri-information-line";
    toast.style.borderColor = "var(--accent-cyan)";
  }

  toast.classList.remove("hidden");
  setTimeout(() => {
    toast.classList.add("hidden");
  }, 4000);
}
