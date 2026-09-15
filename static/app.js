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
let historyData = [];
let currentHistoryFilter = "all";
let currentHistorySearch = "";


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

// ==========================================================================
// Smooth & Elegant Custom Dropdown System
// ==========================================================================
function initCustomSelect(selectElement) {
  if (!selectElement || selectElement.dataset.customSelectInitialized) return;
  selectElement.dataset.customSelectInitialized = "true";

  // Create container
  const container = document.createElement("div");
  container.className = "custom-select-container";
  container.id = `custom-select-${selectElement.id}`;

  // Create trigger button
  const trigger = document.createElement("button");
  trigger.type = "button";
  trigger.className = "custom-select-trigger";
  trigger.setAttribute("aria-haspopup", "listbox");
  trigger.setAttribute("aria-expanded", "false");

  const labelSpan = document.createElement("span");
  labelSpan.className = "custom-select-label";

  const arrowSpan = document.createElement("span");
  arrowSpan.className = "custom-select-arrow";
  arrowSpan.innerHTML = '<i class="ri-arrow-down-s-line"></i>';

  trigger.appendChild(labelSpan);
  trigger.appendChild(arrowSpan);

  // Create floating dropdown menu
  const dropdown = document.createElement("div");
  dropdown.className = "custom-select-dropdown";
  dropdown.setAttribute("role", "listbox");

  const optionsContainer = document.createElement("div");
  optionsContainer.className = "custom-select-options";
  dropdown.appendChild(optionsContainer);

  // Insert container in place of native select
  selectElement.parentNode.insertBefore(container, selectElement);
  container.appendChild(selectElement);
  container.appendChild(trigger);
  container.appendChild(dropdown);

  // Hide native select visually while keeping it fully functional in DOM
  selectElement.classList.add("custom-select-hidden");

  function syncOptions() {
    optionsContainer.innerHTML = "";
    const options = Array.from(selectElement.options);
    const selectedOpt = selectElement.options[selectElement.selectedIndex] || options[0];

    if (selectedOpt) {
      labelSpan.innerText = selectedOpt.text;
    } else {
      labelSpan.innerText = "";
    }

    options.forEach((opt, idx) => {
      const isSelected = opt.selected || opt.value === selectElement.value;
      const optElem = document.createElement("div");
      optElem.className = `custom-select-option ${isSelected ? "selected" : ""}`;
      optElem.setAttribute("role", "option");
      optElem.setAttribute("aria-selected", isSelected ? "true" : "false");
      optElem.dataset.value = opt.value;
      optElem.style.animationDelay = `${Math.min(idx * 28, 200)}ms`;

      optElem.innerHTML = `
        <span class="custom-option-text">${opt.text}</span>
        <i class="ri-check-line custom-option-check"></i>
      `;

      optElem.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        selectOption(opt.value);
      });

      optionsContainer.appendChild(optElem);
    });
  }

  function selectOption(value) {
    if (selectElement.value !== value) {
      selectElement.value = value;
      selectElement.dispatchEvent(new Event("change", { bubbles: true }));
    }
    syncOptions();
    closeDropdown();
  }

  function openDropdown() {
    // Close other open custom selects
    document.querySelectorAll(".custom-select-container.open").forEach(other => {
      if (other !== container) {
        other.classList.remove("open");
        const trig = other.querySelector(".custom-select-trigger");
        if (trig) trig.setAttribute("aria-expanded", "false");
      }
    });

    // Smart viewport collision detection: open upwards only if genuinely restricted below
    const rect = trigger.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const estHeight = Math.min((selectElement.options.length * 44) + 20, 280);
    if (spaceBelow < estHeight && rect.top > estHeight) {
      dropdown.style.top = "auto";
      dropdown.style.bottom = "calc(100% + 6px)";
      dropdown.style.transformOrigin = "bottom center";
    } else {
      dropdown.style.top = "calc(100% + 6px)";
      dropdown.style.bottom = "auto";
      dropdown.style.transformOrigin = "top center";
    }

    container.classList.add("open");
    trigger.setAttribute("aria-expanded", "true");

    const selected = optionsContainer.querySelector(".custom-select-option.selected");
    if (selected) {
      selected.scrollIntoView({ block: "nearest" });
    }
  }

  function closeDropdown() {
    container.classList.remove("open");
    trigger.setAttribute("aria-expanded", "false");
  }

  function toggleDropdown() {
    if (container.classList.contains("open")) {
      closeDropdown();
    } else {
      openDropdown();
    }
  }

  trigger.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    toggleDropdown();
  });

  // Keyboard navigation & accessibility
  trigger.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (!container.classList.contains("open")) {
        openDropdown();
      } else if (e.key === "ArrowDown") {
        focusNextOption(1);
      } else if (e.key === "Enter" || e.key === " ") {
        const focused = optionsContainer.querySelector(".custom-select-option.focused");
        if (focused && focused.dataset.value) {
          selectOption(focused.dataset.value);
        } else {
          closeDropdown();
        }
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (container.classList.contains("open")) {
        focusNextOption(-1);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      closeDropdown();
    }
  });

  function focusNextOption(direction) {
    const opts = Array.from(optionsContainer.querySelectorAll(".custom-select-option"));
    if (opts.length === 0) return;
    let focusedIndex = opts.findIndex(o => o.classList.contains("focused") || o.classList.contains("selected"));
    if (focusedIndex === -1) focusedIndex = 0;
    else focusedIndex = (focusedIndex + direction + opts.length) % opts.length;

    opts.forEach((o, i) => o.classList.toggle("focused", i === focusedIndex));
    opts[focusedIndex].scrollIntoView({ block: "nearest" });
  }

  // React to programmatic native select change events
  selectElement.addEventListener("change", () => {
    syncOptions();
  });

  // Observe option modifications on native select
  const observer = new MutationObserver(() => {
    syncOptions();
  });
  observer.observe(selectElement, { childList: true, subtree: true });

  // Store refresh hook on native select
  selectElement.refreshCustomSelect = syncOptions;

  // Initial sync
  syncOptions();
}

function initAllCustomSelects() {
  document.querySelectorAll("select.form-select").forEach(initCustomSelect);
}

// Global click-outside listener to close dropdowns smoothly
document.addEventListener("click", (e) => {
  if (!e.target.closest(".custom-select-container")) {
    document.querySelectorAll(".custom-select-container.open").forEach(c => {
      c.classList.remove("open");
      const trig = c.querySelector(".custom-select-trigger");
      if (trig) trig.setAttribute("aria-expanded", "false");
    });
  }
});


document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  updateModelVariants("resnext_generator");
  initAllCustomSelects();

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

  // Fetch recent sessions to populate the documents queue and history badges
  fetch("/api/sessions")
    .then(res => res.ok ? res.json() : null)
    .then(data => {
      if (data && data.sessions) {
        historyData = data.sessions;
        updateHistoryBadges();

        if (data.sessions.length > 0) {
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
          historyData = sessData.sessions;
          updateHistoryBadges();
          renderDocumentQueue();

          const histOverlay = document.getElementById("history-modal-overlay");
          if (histOverlay && !histOverlay.classList.contains("hidden")) {
            updateHistoryStatsBar();
            renderHistoryList();
          }

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

  // Keyboard navigation for split comparator & modal dismissal (Escape, ArrowLeft, ArrowRight)
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const histOverlay = document.getElementById("history-modal-overlay");
      if (histOverlay && !histOverlay.classList.contains("hidden")) {
        closeHistoryModal();
        return;
      }
    }

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
  const sliderLine = document.getElementById("slider-line");
  if (sliderLine) {
    sliderLine.addEventListener("input", (e) => {
      const valLine = document.getElementById("val-line");
      if (valLine) valLine.innerText = `${e.target.value}%`;
      triggerLivePreview(350);
    });
  }

  const sliderSat = document.getElementById("slider-saturation");
  if (sliderSat) {
    sliderSat.addEventListener("input", (e) => {
      const valSat = document.getElementById("val-saturation");
      if (valSat) valSat.innerText = `${(e.target.value / 10).toFixed(1)}x`;
      triggerLivePreview(350);
    });
  }

  // Style and Variant Dropdown Listeners
  const styleSelect = document.getElementById("style-select");
  if (styleSelect) styleSelect.addEventListener("change", () => triggerLivePreview(100));

  const modelVariantSelect = document.getElementById("model-variant-select");
  if (modelVariantSelect) modelVariantSelect.addEventListener("change", () => triggerLivePreview(100));

  // Buttons
  const btnStartColorize = document.getElementById("btn-start-colorize");
  if (btnStartColorize) btnStartColorize.addEventListener("click", startColorization);

  const mainExportBtn = document.getElementById("btn-export");
  if (mainExportBtn) mainExportBtn.addEventListener("click", () => exportDocument("auto"));

  const btnChangeFile = document.getElementById("btn-change-file");
  if (btnChangeFile) btnChangeFile.addEventListener("click", resetUpload);

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
  if (!select) return;
  select.innerHTML = "";
  const variants = MODEL_VARIANTS[provider] || [];
  
  variants.forEach(v => {
    const opt = document.createElement("option");
    opt.value = v.value;
    opt.innerText = v.label;
    select.appendChild(opt);
  });

  if (select.refreshCustomSelect) {
    select.refreshCustomSelect();
  }
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

  // Show palette card and load existing characters for this session
  const paletteCard = document.getElementById("palette-card");
  if (paletteCard) paletteCard.style.display = "";
  paletteLoadFromServer();
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

  // Show "Recolorize Selected" button when at least one page is already colorized
  const btnRecolorizeSelected = document.getElementById("btn-recolorize-selected");
  if (btnRecolorizeSelected) {
    if (colorizedCount > 0) {
      btnRecolorizeSelected.classList.remove("hidden");
    } else {
      btnRecolorizeSelected.classList.add("hidden");
    }
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
  if (!grid || !currentSession || !currentSession.pages) return;
  grid.innerHTML = "";

  currentSession.pages.forEach((page, idx) => {
    const isSelected = selectedPages.has(idx);
    const card = document.createElement("div");
    card.className = `page-card ${isSelected ? "selected" : ""}`;
    card.id = `page-card-${idx}`;
    card.onclick = () => openSplitPreview(idx);

    const origUrl = `/api/session/${currentSession.session_id}/image/original/${page.filename}`;
    const thumbUrl = page.colorized_url || origUrl;
    const dimText = (page.width && page.height) ? `${page.width} × ${page.height}` : "";

    // Show a small recolorize button on colorized pages
    const recolorizeBtn = page.status === "colorized"
      ? `<button class="page-recolorize-btn" title="Force re-colorize this page"
               onclick="event.stopPropagation(); recolorizePage(${idx})"
               style="position:absolute;bottom:28px;right:6px;z-index:4;
                      background:rgba(249,115,22,0.92);border:none;border-radius:4px;
                      padding:3px 7px;cursor:pointer;color:#fff;font-size:0.7rem;
                      display:flex;align-items:center;gap:3px;">
           <i class="ri-refresh-line"></i> Recolorize
         </button>`
      : "";
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
        ${recolorizeBtn}
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
    if (isBatchColorizing) {
      btnStart.disabled = true;
    } else if (count === 0) {
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
    selected_pages: pagesToColorize,
    skip_if_colored: document.getElementById("chk-skip-colored")?.checked || false
  };

  // UI state updates
  document.getElementById("progress-card").classList.remove("hidden");
  document.getElementById("export-card").classList.add("hidden");
  const btnStart = document.getElementById("btn-start-colorize");
  if (btnStart) btnStart.disabled = true;

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
      if (btnStart) btnStart.disabled = false;
      updateSelectionUI();
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
    if (btnStart) btnStart.disabled = false;
    updateSelectionUI();
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
        updateSelectionUI();
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
  if (currentCombinedExportJobId) {
    await cancelCombinedExport();
    return;
  }

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

  const rightLabel = document.getElementById("split-label-right");
  if (rightLabel) {
    rightLabel.innerHTML = '<i class="ri-loader-4-line spinner"></i> AI Colorizing...';
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
      
      const imgElem = document.getElementById(`page-img-${pageIdx}`);
      if (imgElem) imgElem.src = `${data.colorized_url}?t=${ts}`;

      const badge = document.getElementById(`page-badge-${pageIdx}`);
      if (badge) {
        badge.className = "page-status-badge status-colorized";
        badge.innerText = "COLORIZED";
      }

      updateColorizedCount();
      updateSelectionUI();

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

      // Open in Before / After Comparator and switch to split view so color is visible
      openSplitPreview(pageIdx, !showToastFeedback);
      setComparatorView("split", true);

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
    if (rightLabel) {
      rightLabel.innerHTML = '<i class="ri-palette-line"></i> Colorized AI';
    }
    const colorImg = document.getElementById("split-img-colorized");
    if (colorImg) colorImg.style.opacity = "1.0";
    if (btnPreview) {
      btnPreview.disabled = false;
      btnPreview.innerHTML = `<i class="ri-sparkles-line"></i> Preview Page ${pageIdx + 1}`;
    }
  }
}

let currentViewMode = "split"; // "bw", "split", "color"

function setComparatorView(mode, animate = true) {
  currentViewMode = mode;
  const overlay = document.getElementById("split-overlay");
  const handle = document.getElementById("split-handle");
  const currentPage = currentSession?.pages?.[currentPreviewPageIndex];

  // If user requests color view but page has not been colorized yet, trigger preview on demand
  if (mode === "color" && currentPage && !currentPage.colorized_url && currentPage.status !== "processing") {
    previewSinglePage(currentPreviewPageIndex, true).then(() => {
      setComparatorView("color", true);
    });
    return;
  }

  // Update toggle button active states
  ["bw", "split", "color"].forEach(m => {
    const btn = document.getElementById(`btn-view-${m}`);
    if (btn) btn.classList.toggle("active", m === mode);
  });

  const btnLeft = document.querySelector(".split-label.label-left");
  const btnRight = document.getElementById("split-label-right");
  if (btnLeft) btnLeft.classList.toggle("active", mode === "bw");
  if (btnRight) btnRight.classList.toggle("active", mode === "color");

  if (animate) {
    if (overlay) overlay.style.transition = "width 0.28s cubic-bezier(0.4, 0, 0.2, 1)";
    if (handle) handle.style.transition = "left 0.28s cubic-bezier(0.4, 0, 0.2, 1)";
    setTimeout(() => {
      if (overlay) overlay.style.transition = "";
      if (handle) handle.style.transition = "";
    }, 300);
  } else {
    if (overlay) overlay.style.transition = "";
    if (handle) handle.style.transition = "";
  }

  if (mode === "bw") {
    setSplitPosition(100);
  } else if (mode === "color") {
    setSplitPosition(0);
  } else {
    setSplitPosition(50);
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
    origImg.draggable = false;
    origImg.onload = () => {
      if (origImg.naturalWidth && origImg.naturalHeight) {
        syncContainerRatio(origImg.naturalWidth, origImg.naturalHeight);
      }
      setSplitPosition(currentSplitPct);
    };
    origImg.src = origUrl;
    if (origImg.complete && origImg.naturalWidth) {
      syncContainerRatio(origImg.naturalWidth, origImg.naturalHeight);
      setSplitPosition(currentSplitPct);
    }
  }
  if (colorImg) {
    colorImg.draggable = false;
    colorImg.onload = () => {
      if (colorImg.naturalWidth && colorImg.naturalHeight) {
        syncContainerRatio(colorImg.naturalWidth, colorImg.naturalHeight);
      }
      setSplitPosition(currentSplitPct);
    };
    colorImg.style.opacity = "1.0";
    colorImg.src = `${colorUrl}?t=${Date.now()}`;
    if (colorImg.complete && colorImg.naturalWidth) {
      syncContainerRatio(colorImg.naturalWidth, colorImg.naturalHeight);
      setSplitPosition(currentSplitPct);
    }
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

  // Setup slider listeners
  setupSplitSlider();

  // Set initial view: if page is colorized, show split; if not, show B&W
  if (page.colorized_url) {
    setComparatorView("split", false);
  } else {
    setComparatorView("bw", false);
  }

  // Reset handle with container dimensions applied
  requestAnimationFrame(() => setSplitPosition(currentSplitPct));
}

function closeSplitPreview() {
  document.getElementById("split-preview-card").classList.add("hidden");
}

let currentSplitPct = 50;
let isSplitSliderInitialized = false;

function setupSplitSlider() {
  const container = document.getElementById("split-container");
  const handle = document.getElementById("split-handle");
  if (!container || isSplitSliderInitialized) return;
  isSplitSliderInitialized = true;

  let isDragging = false;

  const updateFromPointer = (clientX) => {
    const rect = container.getBoundingClientRect();
    if (rect.width <= 0) return;
    let x = clientX - rect.left;
    if (x < 0) x = 0;
    if (x > rect.width) x = rect.width;
    const pct = Math.max(0, Math.min(100, (x / rect.width) * 100));

    const btnLeft = document.querySelector(".split-label.label-left");
    const btnRight = document.getElementById("split-label-right");
    if (btnLeft) btnLeft.classList.toggle("active", pct >= 98);
    if (btnRight) btnRight.classList.toggle("active", pct <= 2);

    setSplitPosition(pct);
  };

  // Modern Pointer Events API (supports Mouse, Touch, and Stylus without native drag interference)
  container.addEventListener("pointerdown", (e) => {
    if (e.button !== undefined && e.button !== 0) return;
    isDragging = true;
    if (handle) handle.classList.add("active");
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
      if (handle) handle.classList.remove("active");
      try {
        container.releasePointerCapture(e.pointerId);
      } catch (err) {}
    }
  };

  container.addEventListener("pointerup", stopDrag);
  container.addEventListener("pointercancel", stopDrag);

  // Prevent browser native image dragging and selection
  container.addEventListener("dragstart", (e) => e.preventDefault());
  container.addEventListener("selectstart", (e) => e.preventDefault());

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
    mobi: "Kindle MOBI e-book",
    azw3: "Kindle AZW3 e-book",
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
    pdf: "all documents as PDFs",
    mobi: "all documents as Kindle MOBIs"
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

// ─────────────────────────────────────────────────────────────────────
//  Combined Single-Volume Export with Real-time Progress & Cancel
// ─────────────────────────────────────────────────────────────────────

let currentCombinedExportJobId = null;
let combinedExportEventSource = null;

function resetCombinedExportUI() {
  const epubBtn = document.getElementById("btn-combined-epub");
  const mobiBtn = document.getElementById("btn-combined-mobi");
  const pdfBtn  = document.getElementById("btn-combined-pdf");
  if (epubBtn) epubBtn.disabled = false;
  if (mobiBtn) mobiBtn.disabled = false;
  if (pdfBtn)  pdfBtn.disabled  = false;

  const progressBox = document.getElementById("combined-export-progress-box");
  if (progressBox) progressBox.classList.add("hidden");

  const progCard = document.getElementById("progress-card");
  if (progCard && progCard.dataset.combinedExport === "true") {
    progCard.classList.add("hidden");
    progCard.dataset.combinedExport = "false";
  }

  if (combinedExportEventSource) {
    try { combinedExportEventSource.close(); } catch (_) {}
    combinedExportEventSource = null;
  }
  currentCombinedExportJobId = null;
}

async function cancelCombinedExport() {
  if (!currentCombinedExportJobId) {
    showToast("No active combined export to cancel.", "warning");
    return;
  }

  const btnCancel = document.getElementById("btn-cancel-combined-export");
  if (btnCancel) {
    btnCancel.disabled = true;
    btnCancel.innerHTML = '<i class="ri-loader-4-line spin"></i> Cancelling...';
  }

  showToast("Cancelling combined export...", "info");

  try {
    await fetch(`/api/export/combined/cancel/${currentCombinedExportJobId}`, {
      method: "POST"
    });
  } catch (err) {
    console.error("Cancel combined export request error:", err);
  }
}

/**
 * Merges all active sessions into a single EPUB, MOBI, or PDF file with live progress.
 *
 * @param {"epub"|"mobi"|"pdf"} format
 */
async function exportCombined(format = "epub") {
  let sessionList = (activeSessions && activeSessions.length > 0)
    ? activeSessions
    : (currentSession ? [currentSession] : []);

  if (sessionList.length === 0 && Array.isArray(historyData) && historyData.length > 0) {
    sessionList = historyData;
  }

  const sessionIds = sessionList.map(s => s.session_id).filter(Boolean);
  const title = document.getElementById("combined-title-input")?.value?.trim()
    || "Colorized Manga Collection";

  const fmtLabel = format === "pdf" ? "Single PDF" : (format === "mobi" ? "Single Kindle MOBI" : "Single EPUB");

  const epubBtn = document.getElementById("btn-combined-epub");
  const mobiBtn = document.getElementById("btn-combined-mobi");
  const pdfBtn  = document.getElementById("btn-combined-pdf");
  if (epubBtn) epubBtn.disabled = true;
  if (mobiBtn) mobiBtn.disabled = true;
  if (pdfBtn)  pdfBtn.disabled  = true;

  // Sidebar progress box
  const progressBox = document.getElementById("combined-export-progress-box");
  const progressTitle = document.getElementById("combined-progress-title-text");
  const progressPct = document.getElementById("combined-progress-pct");
  const progressBarFill = document.getElementById("combined-progress-bar-fill");
  const progressSubtext = document.getElementById("combined-progress-subtext");
  const btnCancel = document.getElementById("btn-cancel-combined-export");

  if (progressBox) progressBox.classList.remove("hidden");
  if (progressTitle) progressTitle.innerText = `Exporting ${fmtLabel}...`;
  if (progressPct) progressPct.innerText = "0%";
  if (progressBarFill) progressBarFill.style.width = "0%";
  if (progressSubtext) progressSubtext.innerText = "Starting packager...";
  if (btnCancel) {
    btnCancel.disabled = false;
    btnCancel.innerHTML = '<i class="ri-close-circle-line"></i> Cancel';
  }

  // Main banner progress card
  const progCard = document.getElementById("progress-card");
  const progStatus = document.getElementById("progress-status-text");
  const progSub = document.getElementById("progress-subtext");
  const progCounter = document.getElementById("progress-counter-text");
  const progFill = document.getElementById("progress-bar-fill");
  if (progCard) {
    progCard.classList.remove("hidden");
    progCard.dataset.combinedExport = "true";
  }
  if (progStatus) progStatus.innerText = `Assembling ${fmtLabel}...`;
  if (progSub) progSub.innerText = `Preparing ${sessionIds.length || 'all'} volumes: "${title}"`;
  if (progCounter) progCounter.innerText = "0%";
  if (progFill) progFill.style.width = "0%";

  showToast(`Preparing ${fmtLabel} (${sessionIds.length || 'all'} volumes)...`, "info");

  try {
    const resp = await fetch("/api/export/combined", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_ids: sessionIds, format, title })
    });

    const data = await resp.json();
    if (!resp.ok || !data.job_id) {
      throw new Error(data.detail || `${fmtLabel} export failed to start.`);
    }

    currentCombinedExportJobId = data.job_id;

    if (combinedExportEventSource) {
      try { combinedExportEventSource.close(); } catch (_) {}
    }

    const sseUrl = data.stream_url || `/api/export/combined/stream/${data.job_id}`;
    combinedExportEventSource = new EventSource(sseUrl);

    combinedExportEventSource.onmessage = (event) => {
      try {
        const ev = JSON.parse(event.data);

        if (ev.type === "progress") {
          const pct = Math.min(100, Math.max(0, ev.percent || 0));
          if (progressPct) progressPct.innerText = `${pct}%`;
          if (progressBarFill) progressBarFill.style.width = `${pct}%`;
          if (progressSubtext) {
            progressSubtext.innerText = ev.status || `Page ${ev.processed_pages}/${ev.total_pages}`;
          }

          if (progCounter) progCounter.innerText = `${ev.processed_pages || 0} / ${ev.total_pages || 0} (${pct}%)`;
          if (progFill) progFill.style.width = `${pct}%`;
          if (progSub && ev.status) progSub.innerText = ev.status;

        } else if (ev.type === "completed") {
          resetCombinedExportUI();
          showToast(`${fmtLabel} ready — ${ev.total_volumes || 'All'} volume(s) merged! Downloading…`, "success");

          const a = document.createElement("a");
          a.href = ev.download_url;
          a.download = ev.filename;
          document.body.appendChild(a);
          a.click();
          a.remove();

        } else if (ev.type === "cancelled") {
          resetCombinedExportUI();
          showToast(`Combined ${fmtLabel} export cancelled.`, "warning");

        } else if (ev.type === "error") {
          resetCombinedExportUI();
          showToast(`Combined export error: ${ev.error || 'Failed'}`, "error");
        }
      } catch (e) {
        console.error("Error parsing combined export SSE message:", e);
      }
    };

    combinedExportEventSource.onerror = () => {
      if (currentCombinedExportJobId) {
        pollCombinedExportFallback(currentCombinedExportJobId, fmtLabel);
      }
    };

  } catch (err) {
    resetCombinedExportUI();
    showToast(`Combined export error: ${err.message}`, "error");
  }
}

async function pollCombinedExportFallback(jobId, fmtLabel) {
  const pollInterval = setInterval(async () => {
    if (!currentCombinedExportJobId || currentCombinedExportJobId !== jobId) {
      clearInterval(pollInterval);
      return;
    }

    try {
      const resp = await fetch(`/api/export/combined/status/${jobId}`);
      if (!resp.ok) {
        clearInterval(pollInterval);
        resetCombinedExportUI();
        return;
      }
      const data = await resp.json();
      if (data.status === "completed") {
        clearInterval(pollInterval);
        resetCombinedExportUI();
        const dlUrl = `/api/download/combined/${data.out_filename || ('collection.' + (data.format || 'epub'))}`;
        const a = document.createElement("a");
        a.href = dlUrl;
        a.download = data.out_filename || "combined_manga";
        document.body.appendChild(a);
        a.click();
        a.remove();
        showToast(`${fmtLabel} download started!`, "success");
      } else if (data.status === "cancelled") {
        clearInterval(pollInterval);
        resetCombinedExportUI();
        showToast(`Combined export cancelled.`, "warning");
      } else if (data.status === "error") {
        clearInterval(pollInterval);
        resetCombinedExportUI();
        showToast(`Export error: ${data.error || 'Failed'}`, "error");
      } else if (data.progress) {
        const pct = data.progress.percent || 0;
        const progressPct = document.getElementById("combined-progress-pct");
        const progressBarFill = document.getElementById("combined-progress-bar-fill");
        const progressSubtext = document.getElementById("combined-progress-subtext");
        if (progressPct) progressPct.innerText = `${pct}%`;
        if (progressBarFill) progressBarFill.style.width = `${pct}%`;
        if (progressSubtext && data.progress.status) progressSubtext.innerText = data.progress.status;
      }
    } catch (_) {
      clearInterval(pollInterval);
      resetCombinedExportUI();
    }
  }, 1000);
}

window.exportCombined = exportCombined;
window.cancelCombinedExport = cancelCombinedExport;


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
      historyData = historyData.filter(s => s.session_id !== sessionId);
      updateHistoryBadges();
      updateHistoryStatsBar();

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

// ─── Document & Processing History Modal Logic ─────────────────────────────

function openHistoryModal() {
  const overlay = document.getElementById("history-modal-overlay");
  if (!overlay) return;
  overlay.classList.remove("hidden");
  document.body.style.overflow = "hidden";

  loadHistoryData();

  setTimeout(() => {
    const input = document.getElementById("history-search-input");
    if (input) input.focus();
  }, 100);
}

function closeHistoryModal() {
  const overlay = document.getElementById("history-modal-overlay");
  if (!overlay) return;
  overlay.classList.add("hidden");
  document.body.style.overflow = "";
}

function handleHistoryOverlayClick(event) {
  if (event.target && event.target.id === "history-modal-overlay") {
    closeHistoryModal();
  }
}

function updateHistoryBadges() {
  const count = historyData ? historyData.length : 0;
  const badge = document.getElementById("history-badge-count");
  if (badge) badge.innerText = count;

  const idleContainer = document.getElementById("idle-history-container");
  const idleCount = document.getElementById("idle-history-count");
  if (idleContainer && idleCount) {
    if (count > 0) {
      idleCount.innerText = count;
      idleContainer.classList.remove("hidden");
    } else {
      idleContainer.classList.add("hidden");
    }
  }
}

async function loadHistoryData(forceRefresh = false) {
  const listContainer = document.getElementById("history-list-container");
  if (forceRefresh && listContainer) {
    listContainer.innerHTML = `
      <div class="history-loading-placeholder">
        <i class="ri-loader-4-line spin" style="font-size: 2rem; color: var(--accent-cyan);"></i>
        <span>Refreshing document sessions...</span>
      </div>
    `;
  }

  try {
    const res = await fetch("/api/sessions");
    if (!res.ok) throw new Error("Failed to load sessions");
    const data = await res.json();
    historyData = data.sessions || [];

    // Keep activeSessions in sync if needed
    if (historyData.length > 0 && (!activeSessions || activeSessions.length === 0)) {
      activeSessions = historyData;
      renderDocumentQueue();
    }

    updateHistoryBadges();
    updateHistoryStatsBar();
    renderHistoryList();
  } catch (err) {
    if (listContainer) {
      listContainer.innerHTML = `
        <div class="history-empty-state">
          <i class="ri-error-warning-line history-empty-icon" style="color: #ef4444;"></i>
          <h4 class="history-empty-title">Unable to Load History</h4>
          <p class="history-empty-desc">${err.message}</p>
          <button class="btn btn-secondary btn-sm" onclick="loadHistoryData(true)">Try Again</button>
        </div>
      `;
    }
  }
}

function updateHistoryStatsBar() {
  const total = historyData.length;
  const completed = historyData.filter(s => s.status === "completed").length;
  const processing = historyData.filter(s => s.status === "processing").length;
  const idle = historyData.filter(s => s.status !== "completed" && s.status !== "processing").length;

  const totalEl = document.getElementById("hist-stat-total");
  const compEl = document.getElementById("hist-stat-completed");
  const procEl = document.getElementById("hist-stat-processing");
  const idleEl = document.getElementById("hist-stat-idle");

  if (totalEl) totalEl.innerText = total;
  if (compEl) compEl.innerText = completed;
  if (procEl) procEl.innerText = processing;
  if (idleEl) idleEl.innerText = idle;

  const tabAll = document.getElementById("hist-tab-all-count");
  const tabComp = document.getElementById("hist-tab-completed-count");
  const tabProc = document.getElementById("hist-tab-proc-count");
  const tabIdle = document.getElementById("hist-tab-idle-count");

  if (tabAll) tabAll.innerText = total;
  if (tabComp) tabComp.innerText = completed;
  if (tabProc) tabProc.innerText = processing;
  if (tabIdle) tabIdle.innerText = idle;

  const batchExportBtn = document.getElementById("btn-history-batch-export");
  if (batchExportBtn) {
    batchExportBtn.disabled = completed === 0;
  }
}

function setHistoryFilter(filter, tabBtn) {
  currentHistoryFilter = filter;
  const tabs = document.querySelectorAll(".history-tab-btn");
  tabs.forEach(t => t.classList.remove("active"));
  if (tabBtn) tabBtn.classList.add("active");
  renderHistoryList();
}

function filterHistoryList() {
  const input = document.getElementById("history-search-input");
  const clearBtn = document.getElementById("btn-history-clear-search");
  currentHistorySearch = input ? input.value.trim().toLowerCase() : "";

  if (clearBtn) {
    if (currentHistorySearch) {
      clearBtn.classList.remove("hidden");
    } else {
      clearBtn.classList.add("hidden");
    }
  }

  renderHistoryList();
}

function clearHistorySearch() {
  const input = document.getElementById("history-search-input");
  if (input) input.value = "";
  filterHistoryList();
}

function renderHistoryList() {
  const container = document.getElementById("history-list-container");
  const summaryEl = document.getElementById("history-footer-summary");
  if (!container) return;

  // Filter items
  let filtered = historyData.filter(item => {
    // Status filter
    if (currentHistoryFilter === "completed" && item.status !== "completed") return false;
    if (currentHistoryFilter === "processing" && item.status !== "processing") return false;
    if (currentHistoryFilter === "idle" && (item.status === "completed" || item.status === "processing")) return false;

    // Search query filter
    if (currentHistorySearch) {
      const name = (item.filename || "").toLowerCase();
      if (!name.includes(currentHistorySearch)) return false;
    }

    return true;
  });

  if (summaryEl) {
    summaryEl.innerText = `Showing ${filtered.length} of ${historyData.length} documents`;
  }

  if (filtered.length === 0) {
    let emptyMsg = "No documents uploaded or processed yet.";
    let emptyDesc = "Drag & drop manga files onto the upload area to start colorizing!";
    if (currentHistorySearch || currentHistoryFilter !== "all") {
      emptyMsg = "No matching documents found.";
      emptyDesc = "Try adjusting your search query or status filter tab above.";
    }

    container.innerHTML = `
      <div class="history-empty-state">
        <i class="ri-folder-history-line history-empty-icon"></i>
        <h4 class="history-empty-title">${emptyMsg}</h4>
        <p class="history-empty-desc">${emptyDesc}</p>
        ${currentHistorySearch || currentHistoryFilter !== "all" ? `
          <button class="btn btn-secondary btn-sm" onclick="clearHistorySearch(); setHistoryFilter('all', document.querySelector('.history-tab-btn[data-filter=all]'));">
            Reset Filters
          </button>
        ` : ""}
      </div>
    `;
    return;
  }

  container.innerHTML = "";

  filtered.forEach(item => {
    const isCurrent = currentSession && currentSession.session_id === item.session_id;
    const totalPages = item.total_pages || 0;
    const processedPages = item.processed_count || 0;
    const pct = totalPages > 0 ? Math.min(100, Math.round((processedPages / totalPages) * 100)) : 0;

    const fn = (item.filename || "").toLowerCase();
    let iconHTML = '<i class="ri-image-fill" style="color: #06b6d4;"></i>';
    if (fn.endsWith(".epub")) {
      iconHTML = '<i class="ri-book-2-fill" style="color: #8b5cf6;"></i>';
    } else if (fn.endsWith(".pdf")) {
      iconHTML = '<i class="ri-file-pdf-fill" style="color: #ef4444;"></i>';
    } else if (fn.endsWith(".zip")) {
      iconHTML = '<i class="ri-folder-zip-fill" style="color: #eab308;"></i>';
    }

    let statusBadgeClass = "status-pending";
    let statusText = "Queued";
    if (item.status === "completed") {
      statusBadgeClass = "status-colorized";
      statusText = "Completed";
    } else if (item.status === "processing") {
      statusBadgeClass = "status-processing";
      statusText = `<i class="ri-loader-4-line spin"></i> Processing (${processedPages}/${totalPages})`;
    }

    const row = document.createElement("div");
    row.className = `history-item ${isCurrent ? "is-current" : ""}`;
    row.id = `history-item-${item.session_id}`;

    row.innerHTML = `
      <div class="history-item-icon">
        ${iconHTML}
      </div>
      <div class="history-item-details">
        <div class="history-item-title-row">
          <span class="history-item-title" title="${item.filename}" onclick="switchFromHistory('${item.session_id}')">
            ${item.filename}
          </span>
          ${isCurrent ? '<span class="history-active-tag">Active</span>' : ''}
        </div>
        <div class="history-item-meta">
          <span class="page-status-badge ${statusBadgeClass}" style="font-size: 0.7rem; padding: 2px 8px;">
            ${statusText}
          </span>
          <span>${processedPages} / ${totalPages} pages (${pct}%)</span>
          <div class="history-progress-track">
            <div class="history-progress-fill" style="width: ${pct}%;"></div>
          </div>
        </div>
      </div>
      <div class="history-item-actions">
        <button class="btn btn-secondary btn-sm btn-history-open" onclick="switchFromHistory('${item.session_id}')" title="Open and view in workspace">
          <i class="ri-arrow-right-line"></i> Open
        </button>
        ${item.status === "completed" ? `
          <button class="btn btn-secondary btn-sm" onclick="exportDocumentFromHistory('${item.session_id}')" title="Export colorized document">
            <i class="ri-download-cloud-2-line"></i> Export
          </button>
        ` : ""}
        <button class="btn-icon btn-danger-icon" onclick="deleteFromHistory(event, '${item.session_id}')" title="Delete document session">
          <i class="ri-delete-bin-line"></i>
        </button>
      </div>
    `;

    container.appendChild(row);
  });
}

async function switchFromHistory(sessionId) {
  closeHistoryModal();
  await switchActiveDocument(sessionId);
}

async function exportDocumentFromHistory(sessionId, format = "auto") {
  const sess = historyData.find(s => s.session_id === sessionId) || (currentSession?.session_id === sessionId ? currentSession : null);
  const docName = sess ? sess.filename : "document";

  showToast(`Preparing export for "${docName}"...`, "info");

  try {
    const queryParam = format && format !== "auto" ? `?format=${encodeURIComponent(format)}` : "";
    const resp = await fetch(`/api/export/${sessionId}${queryParam}`, {
      method: "POST"
    });

    const data = await resp.json();
    if (resp.ok && data.download_url) {
      showToast(`Exported "${data.filename}" successfully! Downloading...`, "success");
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
  }
}

async function deleteFromHistory(event, sessionId) {
  if (event) event.stopPropagation();

  await deleteDocument(event, sessionId);

  // Refresh data in history list
  loadHistoryData(false);
}

// Make history handlers globally available
window.openHistoryModal = openHistoryModal;
window.closeHistoryModal = closeHistoryModal;
window.handleHistoryOverlayClick = handleHistoryOverlayClick;
window.loadHistoryData = loadHistoryData;
window.setHistoryFilter = setHistoryFilter;
window.filterHistoryList = filterHistoryList;
window.clearHistorySearch = clearHistorySearch;
window.switchFromHistory = switchFromHistory;
window.exportDocumentFromHistory = exportDocumentFromHistory;
window.deleteFromHistory = deleteFromHistory;


// ─────────────────────────────────────────────────────────────────────
//  Character Palette Manager
// ─────────────────────────────────────────────────────────────────────

/** In-memory palette state for the active session. */
let paletteCharacters = [];

/**
 * Fetches the current session's palette from the server and re-renders the list.
 */
async function paletteLoadFromServer() {
  if (!currentSession) return;
  try {
    const resp = await fetch(`/api/palette/${currentSession.session_id}`);
    if (!resp.ok) return;
    const data = await resp.json();
    paletteCharacters = data.palette?.characters || [];
    paletteRender();
  } catch (_) {
    // Silent — palette is optional
  }
}

/**
 * Renders the character list inside #palette-character-list.
 * Each row shows the name + color swatches + a delete button.
 */
function paletteRender() {
  const list = document.getElementById("palette-character-list");
  const badge = document.getElementById("palette-badge-count");
  if (!list) return;

  if (badge) badge.innerText = `${paletteCharacters.length} Character${paletteCharacters.length !== 1 ? "s" : ""}`;

  if (paletteCharacters.length === 0) {
    list.innerHTML = `<p style="font-size:0.78rem;color:var(--text-secondary);text-align:center;padding:0.5rem 0;">
      No characters yet. Add one below.
    </p>`;
    return;
  }

  list.innerHTML = paletteCharacters.map((ch, i) => {
    const swatches = [ch.hair_hex, ch.skin_hex, ch.costume_hex, ch.extra_hex]
      .filter(Boolean)
      .map(hx => `<span title="${hx}" style="
        display:inline-block;width:14px;height:14px;border-radius:3px;
        background:${hx};border:1px solid rgba(255,255,255,0.2);vertical-align:middle;"></span>`)
      .join(" ");

    return `
      <div style="display:flex;align-items:center;justify-content:space-between;
                  background:var(--card-bg,#1e1e2e);border:1px solid var(--border-color);
                  border-radius:6px;padding:6px 10px;gap:6px;">
        <span style="font-size:0.82rem;font-weight:500;flex:1;min-width:0;
                     overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
              title="${ch.name}">${ch.name}</span>
        <span style="display:flex;gap:3px;align-items:center;">${swatches}</span>
        <button class="btn-icon" title="Remove ${ch.name}"
                onclick="paletteDeleteCharacter(${i})"
                style="padding:2px 5px;opacity:0.6;flex-shrink:0;">
          <i class="ri-delete-bin-line" style="font-size:0.85rem;"></i>
        </button>
      </div>`;
  }).join("");
}

/**
 * Reads the add-character form, calls POST /api/palette/upsert, and refreshes.
 */
async function paletteAddCharacter() {
  if (!currentSession) { showToast("No active session.", "warning"); return; }

  const name = (document.getElementById("pal-char-name")?.value || "").trim();
  if (!name) { showToast("Please enter a character name.", "warning"); return; }

  const hairHex    = document.getElementById("pal-hair")?.value    || "";
  const skinHex    = document.getElementById("pal-skin")?.value    || "";
  const costumeHex = document.getElementById("pal-costume")?.value || "";
  const extraHex   = document.getElementById("pal-extra")?.value   || "";

  try {
    const resp = await fetch("/api/palette/upsert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: currentSession.session_id,
        character: { name, hair_hex: hairHex, skin_hex: skinHex, costume_hex: costumeHex, extra_hex: extraHex }
      })
    });
    if (!resp.ok) throw new Error((await resp.json()).detail || "Failed");
    const data = await resp.json();
    paletteCharacters = data.palette?.characters || [];
    paletteRender();
    const nameInput = document.getElementById("pal-char-name");
    if (nameInput) nameInput.value = "";
    showToast(`Character "${name}" saved to palette.`, "success");
  } catch (err) {
    showToast(`Palette error: ${err.message}`, "error");
  }
}

/**
 * Removes a character by index from the local list and calls DELETE on the server.
 */
async function paletteDeleteCharacter(index) {
  if (!currentSession) return;
  const ch = paletteCharacters[index];
  if (!ch) return;

  try {
    const resp = await fetch(
      `/api/palette/${currentSession.session_id}/${encodeURIComponent(ch.name)}`,
      { method: "DELETE" }
    );
    if (!resp.ok) throw new Error((await resp.json()).detail || "Failed");
    const data = await resp.json();
    paletteCharacters = data.palette?.characters || [];
    paletteRender();
    showToast(`"${ch.name}" removed from palette.`, "info");
  } catch (err) {
    showToast(`Could not remove character: ${err.message}`, "error");
  }
}

window.paletteAddCharacter    = paletteAddCharacter;
window.paletteDeleteCharacter = paletteDeleteCharacter;
window.paletteLoadFromServer  = paletteLoadFromServer;


// ─────────────────────────────────────────────────────────────────────
//  Recolorize — force re-run colorization on already-done pages
// ─────────────────────────────────────────────────────────────────────

/**
 * Force-recolorizes a single page using the preview endpoint.
 * Works from both the split preview header and the per-card button.
 *
 * @param {number} pageIdx  - 0-based page index
 */
async function recolorizePage(pageIdx) {
  if (!currentSession) return;
  const page = currentSession.pages[pageIdx];
  if (!page) return;

  const modelVariant  = document.getElementById("model-variant-select")?.value || "";
  const apiKey        = document.getElementById("api-key-input")?.value || "";
  const style         = document.getElementById("style-select")?.value || "gemini_anime";
  const linePreserve  = parseFloat(document.getElementById("slider-line")?.value || "85") / 100.0;
  const saturation    = parseFloat(document.getElementById("slider-saturation")?.value || "14") / 10.0;

  // Show loading state in split preview header
  const recolorBtn = document.getElementById("btn-recolorize-page");
  if (recolorBtn) {
    recolorBtn.disabled = true;
    recolorBtn.innerHTML = '<i class="ri-loader-4-line spinner"></i> Recolorizing…';
  }

  // Mark card badge as processing
  const badge = document.getElementById(`page-badge-${pageIdx}`);
  if (badge) { badge.className = "page-status-badge status-processing"; badge.innerText = "PROCESSING"; }

  showToast(`Recolorizing ${page.display_name}…`, "info");

  try {
    const resp = await fetch("/api/colorize/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id:      currentSession.session_id,
        page_index:      pageIdx,
        model_provider:  activeProvider,
        model_name:      modelVariant,
        api_key:         apiKey,
        style:           style,
        saturation:      saturation,
        contrast:        1.1,
        line_preserve:   linePreserve,
        force_recolorize: true,
      })
    });

    const data = await resp.json();
    if (resp.ok && data.status === "success") {
      page.status = "colorized";
      page.colorized_url = data.colorized_url;
      const ts = Date.now();

      // Update gallery thumbnail
      const imgElem = document.getElementById(`page-img-${pageIdx}`);
      if (imgElem) imgElem.src = `${data.colorized_url}?t=${ts}`;

      if (badge) { badge.className = "page-status-badge status-colorized"; badge.innerText = "COLORIZED"; }

      // Refresh split preview images
      const colorImg = document.getElementById("split-img-colorized");
      if (colorImg && currentPreviewPageIndex === pageIdx) {
        colorImg.src = `${data.colorized_url}?t=${ts}`;
      }

      showToast(`${page.display_name} recolorized!`, "success");
      updateColorizedCount();
      // Re-render gallery so card recolorize button refreshes
      renderGalleryGrid();
    } else {
      if (badge) { badge.className = "page-status-badge status-colorized"; badge.innerText = "COLORIZED"; }
      showToast(data.detail || "Recolorize failed.", "error");
    }
  } catch (err) {
    if (badge) { badge.className = "page-status-badge status-colorized"; badge.innerText = "COLORIZED"; }
    showToast(`Error: ${err.message}`, "error");
  } finally {
    if (recolorBtn) {
      recolorBtn.disabled = false;
      recolorBtn.innerHTML = '<i class="ri-magic-line"></i> Recolorize';
    }
  }
}

/**
 * Force-recolorizes all currently selected pages.
 * Mirrors startColorization() but always passes force_recolorize=true.
 */
async function recolorizeSelected() {
  if (!currentSession) return;

  const pagesToRecolorize = selectedPages.size > 0
    ? Array.from(selectedPages).sort((a, b) => a - b)
    : null;

  if (!pagesToRecolorize || pagesToRecolorize.length === 0) {
    showToast("No pages selected.", "warning");
    return;
  }

  const modelVariant = document.getElementById("model-variant-select")?.value || "";
  const apiKey       = document.getElementById("api-key-input")?.value || "";
  const style        = document.getElementById("style-select")?.value || "gemini_anime";
  const linePreserve = parseFloat(document.getElementById("slider-line")?.value || "85") / 100.0;
  const saturation   = parseFloat(document.getElementById("slider-saturation")?.value || "14") / 10.0;

  const payload = {
    session_id:       currentSession.session_id,
    model_provider:   activeProvider,
    model_name:       modelVariant,
    api_key:          apiKey,
    style:            style,
    saturation:       saturation,
    contrast:         1.1,
    line_preserve:    linePreserve,
    selected_pages:   pagesToRecolorize,
    force_recolorize: true,
    skip_if_colored:  false,
  };

  // UI feedback
  document.getElementById("progress-card")?.classList.remove("hidden");
  document.getElementById("export-card")?.classList.add("hidden");
  document.getElementById("btn-start-colorize").disabled = true;

  const pageCountText = `${pagesToRecolorize.length} Page${pagesToRecolorize.length !== 1 ? "s" : ""}`;
  const progSub = document.getElementById("progress-subtext");
  if (progSub) progSub.innerText = `Force recolorizing ${pageCountText}…`;

  showToast(`Recolorizing ${pagesToRecolorize.length} page(s)…`, "info");

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
      showToast(err.detail || "Failed to start recolorization.", "error");
      document.getElementById("btn-start-colorize").disabled = false;
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
    document.getElementById("btn-start-colorize").disabled = false;
  }
}

window.recolorizePage     = recolorizePage;
window.recolorizeSelected = recolorizeSelected;
