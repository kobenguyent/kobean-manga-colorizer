// Manga Colorizer Pro - Client Application Logic

let currentSession = null;
let activeSessions = [];
let currentBatchId = null;
let eventSource = null;
let activeProvider = "resnext_generator";
let currentPreviewPageIndex = 0;
let isBatchColorizing = false;
let batchQueuePoller = null;
let selectedPages = new Set();


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
        if (data.status === "processing") {
          const progCard = document.getElementById("progress-card");
          if (progCard) progCard.classList.remove("hidden");
          const expCard = document.getElementById("export-card");
          if (expCard) expCard.classList.add("hidden");
          const btnStart = document.getElementById("btn-start-colorize");
          if (btnStart) btnStart.disabled = true;
          subscribeToProgressStream(data.session_id);
        } else if (data.pages[0].status === "colorized") {
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

        // Check if a batch is active on the server
        fetch("/api/colorize/batch/status")
          .then(res => res.ok ? res.json() : null)
          .then(batchData => {
            if (batchData && batchData.is_running) {
              isBatchColorizing = true;
              startBatchQueuePoller();
              if (batchData.current_session_id) {
                if (!currentSession || currentSession.session_id === batchData.current_session_id) {
                  subscribeToProgressStream(batchData.current_session_id);
                }
              }
            }
          })
          .catch(() => {});
      }
    })
    .catch(() => {});
});

function startBatchQueuePoller() {
  if (batchQueuePoller) clearInterval(batchQueuePoller);
  batchQueuePoller = setInterval(async () => {
    try {
      const batchRes = await fetch("/api/colorize/batch/status");
      if (batchRes.ok) {
        const batchData = await batchRes.json();
        if (!batchData.is_running && isBatchColorizing) {
          const anyProcessing = activeSessions.some(s => s.status === "processing");
          if (!anyProcessing) {
            isBatchColorizing = false;
            clearInterval(batchQueuePoller);
            batchQueuePoller = null;
            const progCard = document.getElementById("progress-card");
            if (progCard) progCard.classList.add("hidden");
            const btnStart = document.getElementById("btn-start-colorize");
            if (btnStart) btnStart.disabled = false;
            const btnBatch = document.getElementById("btn-start-batch-colorize");
            if (btnBatch) btnBatch.disabled = false;
            const expCard = document.getElementById("export-card");
            if (expCard) expCard.classList.remove("hidden");
            const sidebarExportCard = document.getElementById("sidebar-export-card");
            if (sidebarExportCard) sidebarExportCard.classList.remove("hidden");
          }
        }
      }

      const sessRes = await fetch("/api/sessions");
      if (sessRes.ok) {
        const sessData = await sessRes.json();
        if (sessData && sessData.sessions) {
          activeSessions = sessData.sessions;
          renderDocumentQueue();
          if (currentSession) {
            const updatedCurr = activeSessions.find(s => s.session_id === currentSession.session_id);
            if (updatedCurr) {
              currentSession.processed_count = updatedCurr.processed_count;
              currentSession.status = updatedCurr.status;
            }
          }
        }
      }
    } catch (err) {
      // transient polling error
    }
  }, 3000);
}

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

  // Click handler on entire dropzone box to open file explorer
  dropzone.addEventListener("click", (e) => {
    if (e.target === fileInput) return;
    const loadingContent = document.getElementById("dropzone-loading-content");
    if (loadingContent && !loadingContent.classList.contains("hidden")) return;
    fileInput.click();
  });

  fileInput.addEventListener("change", (e) => {
    if (fileInput.files.length > 0) {
      handleFileSelection(fileInput.files);
    }
  });

  if (addMoreInput) {
    addMoreInput.addEventListener("change", (e) => {
      if (addMoreInput.files && addMoreInput.files.length > 0) {
        handleFileSelection(addMoreInput.files);
      }
    });
  }

  // Window-level drag & drop support so dropping files anywhere on the page uploads them
  ["dragenter", "dragover"].forEach(eventName => {
    window.addEventListener(eventName, (e) => {
      e.preventDefault();
      const dropzone = document.getElementById("dropzone");
      if (dropzone) dropzone.classList.add("dragover");
    });
  });

  ["dragleave"].forEach(eventName => {
    window.addEventListener(eventName, (e) => {
      if (e.clientX <= 0 || e.clientY <= 0 || e.clientX >= window.innerWidth || e.clientY >= window.innerHeight) {
        const dropzone = document.getElementById("dropzone");
        if (dropzone) dropzone.classList.remove("dragover");
      }
    });
  });

  window.addEventListener("drop", (e) => {
    e.preventDefault();
    const dropzone = document.getElementById("dropzone");
    if (dropzone) dropzone.classList.remove("dragover");
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelection(e.dataTransfer.files);
    }
  });

  // Keyboard navigation for split comparator (ArrowLeft, ArrowRight, Escape)
  window.addEventListener("keydown", (e) => {
    const splitCard = document.getElementById("split-preview-card");
    if (!splitCard || splitCard.classList.contains("hidden")) return;
    if (["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement?.tagName)) return;

    if (e.key === "ArrowLeft") {
      e.preventDefault();
      navigatePreviewPage(-1);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      navigatePreviewPage(1);
    } else if (e.key === "Escape") {
      closeSplitPreview();
    }
  });

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

function triggerAddFiles() {
  const addMoreInput = document.getElementById("add-more-input");
  if (addMoreInput) {
    addMoreInput.value = "";
    addMoreInput.click();
  }
}
window.triggerAddFiles = triggerAddFiles;

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

  // Visual feedback on the Add Files button in the sidebar
  const addBtn = document.getElementById("btn-add-files");
  let origAddBtnHTML = "";
  if (addBtn) {
    origAddBtnHTML = addBtn.innerHTML;
    addBtn.disabled = true;
    addBtn.innerHTML = '<i class="ri-loader-4-line spin"></i> Adding...';
  }

  // Show dropzone upload loading UI (for initial landing page state)
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
      // 1. Refresh activeSessions from server to get accurate natural sort and status
      const sessRes = await fetch("/api/sessions");
      if (sessRes.ok) {
        const sessData = await sessRes.json();
        if (sessData && sessData.sessions) {
          activeSessions = sessData.sessions;
        }
      }

      // 2. Fetch full session details for the newly uploaded primary document
      const newSessionId = data.session_id;
      const fullSessRes = await fetch(`/api/session/${newSessionId}`);
      if (fullSessRes.ok) {
        currentSession = await fullSessRes.json();
      } else {
        currentSession = data;
      }
      currentBatchId = data.batch_id || currentBatchId;
      sessionStorage.setItem("active_session_id", currentSession.session_id);
      if (currentBatchId) {
        sessionStorage.setItem("active_batch_id", currentBatchId);
      }

      renderDashboard();
      renderDocumentQueue();
      showToast(`Added ${validFiles.length} document(s) with ${data.total_pages || 0} pages!`, "success");
    } else {
      showToast(data.detail || "Upload failed.", "error");
      if (idleContent) idleContent.classList.remove("hidden");
      if (loadingContent) loadingContent.classList.add("hidden");
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
    if (idleContent) idleContent.classList.remove("hidden");
    if (loadingContent) loadingContent.classList.add("hidden");
  } finally {
    if (addBtn && origAddBtnHTML) {
      addBtn.disabled = false;
      addBtn.innerHTML = origAddBtnHTML;
    }
    const addMore = document.getElementById("add-more-input");
    if (addMore) addMore.value = "";
    const fileInput = document.getElementById("file-input");
    if (fileInput) fileInput.value = "";
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
      batchColorizeBtn.disabled = isBatchColorizing;
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

    let statusBadgeClass = "status-pending";
    let statusHTML = `${sess.processed_count || 0}/${sess.total_pages || 0}`;

    if (sess.status === "completed") {
      statusBadgeClass = "status-colorized";
      statusHTML = "Ready";
    } else if (sess.status === "processing") {
      statusBadgeClass = "status-processing";
      statusHTML = `<i class="ri-loader-4-line spin"></i> ${sess.processed_count || 0}/${sess.total_pages || 0}`;
    }

    item.innerHTML = `
      <div class="doc-queue-icon">${iconHTML}</div>
      <div class="doc-queue-info">
        <div class="doc-queue-name" title="${sess.filename}">${sess.filename}</div>
        <div class="doc-queue-meta">
          <span>${sess.total_pages} pages</span>
          <span class="page-status-badge ${statusBadgeClass}" id="doc-queue-badge-${sess.session_id}" style="font-size: 0.68rem; padding: 1px 6px;">${statusHTML}</span>
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

      const progCard = document.getElementById("progress-card");
      const expCard = document.getElementById("export-card");
      const btnStart = document.getElementById("btn-start-colorize");

      if (data.status === "processing") {
        if (progCard) progCard.classList.remove("hidden");
        if (expCard) expCard.classList.add("hidden");
        if (btnStart) btnStart.disabled = true;
        subscribeToProgressStream(sessionId);
      } else if (data.status === "completed") {
        if (!isBatchColorizing && progCard) progCard.classList.add("hidden");
        if (expCard) expCard.classList.remove("hidden");
        if (btnStart) btnStart.disabled = false;
      } else {
        if (!isBatchColorizing && progCard) progCard.classList.add("hidden");
        if (btnStart) btnStart.disabled = isBatchColorizing;
      }

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

  // Initialize all pages as selected when opening or switching documents
  if (currentSession.pages) {
    selectedPages = new Set(currentSession.pages.map((_, i) => i));
  } else {
    selectedPages = new Set();
  }

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

function updateColorizedCount() {
  if (!currentSession || !currentSession.pages) return;
  const colorizedCount = currentSession.pages.filter(p => p.status === "colorized").length;
  currentSession.processed_count = colorizedCount;

  const countElem = document.getElementById("colorized-count");
  if (countElem) countElem.innerText = colorizedCount;

  const totalElem = document.getElementById("gallery-total-count");
  if (totalElem) totalElem.innerText = currentSession.total_pages || currentSession.pages.length;

  const exportBadge = document.getElementById("export-badge-count");
  if (exportBadge) exportBadge.innerText = `${colorizedCount} Ready`;

  const exportCard = document.getElementById("export-card");
  const sidebarExportCard = document.getElementById("sidebar-export-card");
  if (colorizedCount > 0 || (currentSession && currentSession.status === "completed")) {
    if (exportCard) exportCard.classList.remove("hidden");
    if (sidebarExportCard) sidebarExportCard.classList.remove("hidden");
  } else {
    if (exportCard) exportCard.classList.add("hidden");
    if (sidebarExportCard) sidebarExportCard.classList.add("hidden");
  }

  // Synchronize with activeSessions sidebar queue
  if (Array.isArray(activeSessions)) {
    const sessIdx = activeSessions.findIndex(s => s.session_id === currentSession.session_id);
    if (sessIdx !== -1) {
      activeSessions[sessIdx].processed_count = colorizedCount;
      if (colorizedCount === currentSession.total_pages) {
        activeSessions[sessIdx].status = "completed";
      }
      renderDocumentQueue();
    }
  }
}

function renderGalleryGrid() {
  const grid = document.getElementById("pages-grid");
  grid.innerHTML = "";

  currentSession.pages.forEach((page, idx) => {
    const isSelected = selectedPages.has(idx);
    const card = document.createElement("div");
    card.className = `page-card ${isSelected ? "selected" : ""}`;
    card.id = `page-card-${idx}`;
    card.onclick = () => openSplitPreview(idx);

    const thumbUrl = page.colorized_url || `/api/session/${currentSession.session_id}/image/original/${page.filename}`;
    
    const dimText = (page.width && page.height) ? `${page.width} × ${page.height}` : "";
    card.innerHTML = `
      <div class="page-thumb-container">
        <label class="page-select-checkbox ${isSelected ? 'checked' : ''}" onclick="event.stopPropagation()" title="Select/Deselect page for colorization">
          <input type="checkbox" id="page-check-${idx}" ${isSelected ? 'checked' : ''} onchange="togglePageSelection(${idx}, this.checked, event)" />
          <span class="custom-checkbox"><i class="ri-check-line"></i></span>
        </label>
        <button class="page-delete-btn" title="Delete this page" onclick="deletePage(event, ${idx})">
          <i class="ri-delete-bin-line"></i>
        </button>
        <span class="page-status-badge status-${page.status}" id="page-badge-${idx}">
          ${page.status.toUpperCase()}
        </span>
        <img class="page-thumb-img" id="page-img-${idx}" src="${thumbUrl}" alt="${page.display_name}" loading="lazy" />
      </div>
      <div class="page-card-footer">
        <span class="page-card-title">${page.display_name}</span>
        ${dimText ? `<span class="page-card-dim">${dimText}</span>` : '<i class="ri-eye-line"></i>'}
      </div>
    `;
    grid.appendChild(card);
  });

  updateColorizedCount();
  updateSelectionUI();
}

function togglePageSelection(idx, isSelected, event) {
  if (event) event.stopPropagation();
  if (isSelected) {
    selectedPages.add(idx);
  } else {
    selectedPages.delete(idx);
  }

  const card = document.getElementById(`page-card-${idx}`);
  if (card) {
    const cbLabel = card.querySelector(".page-select-checkbox");
    if (isSelected) {
      card.classList.add("selected");
      if (cbLabel) cbLabel.classList.add("checked");
    } else {
      card.classList.remove("selected");
      if (cbLabel) cbLabel.classList.remove("checked");
    }
  }

  updateSelectionUI();
}

function toggleSelectAllPages(selectAll) {
  if (!currentSession || !currentSession.pages) return;
  if (selectAll) {
    selectedPages = new Set(currentSession.pages.map((_, i) => i));
  } else {
    selectedPages.clear();
  }

  currentSession.pages.forEach((_, idx) => {
    const cb = document.getElementById(`page-check-${idx}`);
    if (cb) cb.checked = selectAll;
    const card = document.getElementById(`page-card-${idx}`);
    if (card) {
      const cbLabel = card.querySelector(".page-select-checkbox");
      if (selectAll) {
        card.classList.add("selected");
        if (cbLabel) cbLabel.classList.add("checked");
      } else {
        card.classList.remove("selected");
        if (cbLabel) cbLabel.classList.remove("checked");
      }
    }
  });

  updateSelectionUI();
}

function updateSelectionUI() {
  if (!currentSession || !currentSession.pages) return;
  const total = currentSession.pages.length;
  const count = selectedPages.size;

  const selectAllCb = document.getElementById("select-all-pages-checkbox");
  if (selectAllCb) {
    selectAllCb.checked = count === total && total > 0;
    selectAllCb.indeterminate = count > 0 && count < total;
  }

  const selectedTextElem = document.getElementById("selected-pages-text");
  if (selectedTextElem) {
    if (count === total && total > 0) {
      selectedTextElem.innerText = `All (${total}) Selected`;
    } else if (count === 0) {
      selectedTextElem.innerText = `0 Selected`;
    } else {
      selectedTextElem.innerText = `${count} of ${total} Selected`;
    }
  }

  const btnStart = document.getElementById("btn-start-colorize");
  if (btnStart) {
    if (count === 0) {
      btnStart.innerHTML = '<i class="ri-checkbox-blank-line"></i> Select Pages to Colorize';
      btnStart.disabled = true;
    } else if (count === total) {
      btnStart.innerHTML = `<i class="ri-magic-line"></i> Start Colorizing All (${total} Pages)`;
      btnStart.disabled = false;
    } else {
      btnStart.innerHTML = `<i class="ri-magic-line"></i> Start Colorizing (${count} Selected Pages)`;
      btnStart.disabled = false;
    }
  }
}

async function startColorization() {
  if (!currentSession) return;

  const modelVariant = document.getElementById("model-variant-select").value;
  const apiKey = document.getElementById("api-key-input").value;
  const style = document.getElementById("style-select").value;
  const linePreserve = parseFloat(document.getElementById("slider-line").value) / 100.0;
  const saturation = parseFloat(document.getElementById("slider-saturation").value) / 10.0;

  // Determine selected pages
  let pagesToColorize = null;
  if (selectedPages && selectedPages.size > 0 && selectedPages.size < currentSession.pages.length) {
    pagesToColorize = Array.from(selectedPages).sort((a, b) => a - b);
  } else if (selectedPages && selectedPages.size === 0) {
    showToast("Please select at least one page to colorize.", "warning");
    return;
  }

  const payload = {
    session_id: currentSession.session_id,
    model_provider: activeProvider,
    model_name: modelVariant,
    api_key: apiKey,
    style: style,
    saturation: saturation,
    contrast: 1.1,
    line_preserve: linePreserve,
    selected_pages: pagesToColorize
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

  const pageCountText = pagesToColorize ? `${pagesToColorize.length} Selected Pages` : `${currentSession.total_pages} Pages`;
  document.getElementById("progress-subtext").innerText = `Using ${providerNames[activeProvider]} (${modelVariant}) • ${pageCountText}`;

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
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }

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
          const pct = Math.min(100, Math.round((data.processed_count / currentSession.total_pages) * 100));
          const barFill = document.getElementById("progress-bar-fill");
          if (barFill) barFill.style.width = `${pct}%`;
          const counterText = document.getElementById("progress-counter-text");
          if (counterText) counterText.innerText = `${data.processed_count} / ${currentSession.total_pages}`;
          const countText = document.getElementById("colorized-count");
          if (countText) countText.innerText = data.processed_count;
        }

        updateColorizedCount();
      }

      // Update activeSessions and sidebar badge directly for fast live feedback
      const sessIdx = activeSessions.findIndex(s => s.session_id === targetId);
      if (sessIdx !== -1) {
        activeSessions[sessIdx].status = "processing";
        if (data.processed_count !== undefined) {
          activeSessions[sessIdx].processed_count = data.processed_count;
        }
        const badgeElem = document.getElementById(`doc-queue-badge-${targetId}`);
        if (badgeElem) {
          badgeElem.className = "page-status-badge status-processing";
          badgeElem.innerHTML = `<i class="ri-loader-4-line spin"></i> ${activeSessions[sessIdx].processed_count || 0}/${activeSessions[sessIdx].total_pages || 0}`;
        }
      }

    } else if (data.type === "completed") {
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }

      // Mark this session as completed in activeSessions
      const sessIdx = activeSessions.findIndex(s => s.session_id === targetId);
      if (sessIdx !== -1) {
        activeSessions[sessIdx].status = "completed";
        activeSessions[sessIdx].processed_count = activeSessions[sessIdx].total_pages;
      }
      if (currentSession && currentSession.session_id === targetId) {
        currentSession.status = "completed";
        currentSession.processed_count = currentSession.total_pages;
      }
      renderDocumentQueue();

      if (isBatchColorizing) {
        // Look for next session that needs colorization
        const nextSess = activeSessions.find(s => s.status !== "completed");
        if (nextSess) {
          showToast(`Completed "${currentSession?.filename || 'Document'}"! Starting "${nextSess.filename}"...`, "info");
          switchActiveDocument(nextSess.session_id).then(() => {
            subscribeToProgressStream(nextSess.session_id);
          });
          return;
        } else {
          isBatchColorizing = false;
          showToast("All documents in queue colorized successfully!", "success");
        }
      }

      const progCard = document.getElementById("progress-card");
      if (progCard) progCard.classList.add("hidden");
      const expCard = document.getElementById("export-card");
      if (expCard) expCard.classList.remove("hidden");
      const sidebarExportCard = document.getElementById("sidebar-export-card");
      if (sidebarExportCard) sidebarExportCard.classList.remove("hidden");
      const btnStart = document.getElementById("btn-start-colorize");
      if (btnStart) btnStart.disabled = false;
      const btnBatch = document.getElementById("btn-start-batch-colorize");
      if (btnBatch) btnBatch.disabled = false;

      if (!isBatchColorizing) {
        showToast("Colorization complete!", "success");
      }
      renderDocumentQueue();

    } else if (data.type === "cancelled") {
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      isBatchColorizing = false;
      const progCard = document.getElementById("progress-card");
      if (progCard) progCard.classList.add("hidden");
      const btnStart = document.getElementById("btn-start-colorize");
      if (btnStart) btnStart.disabled = false;
      const btnBatch = document.getElementById("btn-start-batch-colorize");
      if (btnBatch) btnBatch.disabled = false;

      renderGalleryGrid();
      updateColorizedCount();
      renderDocumentQueue();
      showToast("Colorization cancelled.", "info");
    }
  };

  eventSource.onerror = (err) => {
    // If SSE disconnects, don't crash, poller handles state
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

      // Keep counter, badge, and export cards in sync
      updateColorizedCount();

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

  // Update prev / next buttons and floating chevron indicators
  const totalPages = currentSession?.pages?.length || 0;
  const prevBtn = document.getElementById("btn-prev-page");
  const nextBtn = document.getElementById("btn-next-page");
  if (prevBtn) prevBtn.disabled = pageIdx <= 0;
  if (nextBtn) nextBtn.disabled = pageIdx >= totalPages - 1;

  const chevronPrev = document.querySelector(".preview-nav-prev");
  const chevronNext = document.querySelector(".preview-nav-next");
  if (chevronPrev) chevronPrev.style.display = pageIdx <= 0 ? "none" : "flex";
  if (chevronNext) chevronNext.style.display = pageIdx >= totalPages - 1 ? "none" : "flex";

  // Reset handle with container dimensions applied
  requestAnimationFrame(() => setSplitPosition(currentSplitPct));
}

function closeSplitPreview() {
  document.getElementById("split-preview-card").classList.add("hidden");
}

let currentSplitPct = 50;

function setupSplitSlider() {
  const container = document.getElementById("split-container");
  if (!container) return;

  let isDragging = false;

  const updateFromPointer = (clientX) => {
    const rect = container.getBoundingClientRect();
    if (rect.width <= 0) return;
    let x = clientX - rect.left;
    if (x < 0) x = 0;
    if (x > rect.width) x = rect.width;
    const pct = Math.max(0, Math.min(100, (x / rect.width) * 100));
    setSplitPosition(pct);
  };

  // Modern Pointer Events API (supports Mouse, Touch, and Stylus without native drag interference)
  container.addEventListener("pointerdown", (e) => {
    if (e.button !== undefined && e.button !== 0) return;
    isDragging = true;
    try {
      container.setPointerCapture(e.pointerId);
    } catch (err) {}
    updateFromPointer(e.clientX);
    e.preventDefault();
  });

  container.addEventListener("pointermove", (e) => {
    if (!isDragging) return;
    updateFromPointer(e.clientX);
    e.preventDefault();
  });

  const stopDrag = (e) => {
    if (isDragging) {
      isDragging = false;
      try {
        container.releasePointerCapture(e.pointerId);
      } catch (err) {}
    }
  };

  container.addEventListener("pointerup", stopDrag);
  container.addEventListener("pointercancel", stopDrag);

  // Horizontal Trackpad / Wheel Scroll Support (Swipe left/right to slide divider)
  container.addEventListener("wheel", (e) => {
    const isHorizontal = Math.abs(e.deltaX) > Math.abs(e.deltaY);
    const delta = isHorizontal ? e.deltaX : (e.shiftKey ? e.deltaY : 0);
    if (delta !== 0) {
      e.preventDefault();
      const step = (delta / (container.clientWidth || 600)) * 100 * 1.2;
      const newPct = Math.max(0, Math.min(100, currentSplitPct + step));
      setSplitPosition(newPct);
    }
  }, { passive: false });

  // Window resize & ResizeObserver for dynamic image alignment
  window.addEventListener("resize", () => setSplitPosition(currentSplitPct));
  if (window.ResizeObserver) {
    const ro = new ResizeObserver(() => setSplitPosition(currentSplitPct));
    ro.observe(container);
  }
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

function navigatePreviewPage(direction) {
  if (!currentSession || !currentSession.pages || currentSession.pages.length === 0) return;
  const newIndex = currentPreviewPageIndex + direction;
  if (newIndex >= 0 && newIndex < currentSession.pages.length) {
    openSplitPreview(newIndex, true);
  } else if (newIndex < 0) {
    showToast("Already on the first page.", "info");
  } else {
    showToast("Already on the last page.", "info");
  }
}
window.navigatePreviewPage = navigatePreviewPage;

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

  isBatchColorizing = true;
  const btnStart = document.getElementById("btn-start-colorize");
  if (btnStart) btnStart.disabled = true;
  const btnBatch = document.getElementById("btn-start-batch-colorize");
  if (btnBatch) btnBatch.disabled = true;

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
    if (resp.ok && (data.status === "started" || data.status === "already_running")) {
      showToast(data.message, "success");
      startBatchQueuePoller();

      // Find the first document that needs colorization
      const targetSess = activeSessions.find(s => s.status !== "completed") || currentSession;
      if (targetSess) {
        if (!currentSession || currentSession.session_id !== targetSess.session_id) {
          await switchActiveDocument(targetSess.session_id);
        } else {
          const progCard = document.getElementById("progress-card");
          if (progCard) progCard.classList.remove("hidden");
          const expCard = document.getElementById("export-card");
          if (expCard) expCard.classList.add("hidden");
          subscribeToProgressStream(targetSess.session_id);
        }
      }
    } else {
      showToast(data.detail || "Batch colorization failed.", "error");
      isBatchColorizing = false;
      if (btnStart) btnStart.disabled = false;
      if (btnBatch) btnBatch.disabled = false;
    }
  } catch (err) {
    showToast(`Batch error: ${err.message}`, "error");
    isBatchColorizing = false;
    if (btnStart) btnStart.disabled = false;
    if (btnBatch) btnBatch.disabled = false;
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
