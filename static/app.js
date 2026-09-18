// Manga Colorizer Pro - Client Application Logic

let currentSession = null;
let isImportCancelled = false;
let currentImportId = null;
let folderImportPoller = null;
let queueSearchQuery = "";
let queueRenderLimit = 50;
let currentHistoryPage = 1;
const historyPageSize = 25;
let activeSessions = [];
let currentBatchId = null;
let eventSource = null;
let activeProvider = "resnext_generator";
let currentPreviewPageIndex = 0;
let isBatchColorizing = false;
let batchQueuePoller = null;
let selectedPages = new Set();
let exportBannerDismissed = false;
let historyData = [];
let currentHistoryFilter = "all";
let currentHistorySearch = "";
let selectedHistorySessions = new Set();
let selectedQueueSessions = new Set();


// Sub-model options per provider
const MODEL_VARIANTS = {
  resnext_generator: [
    { value: "resnext-v2-manga", label: "🧬 ResNeXt-based Manga Generator (Deep U-Net + FFDNet)" },
    { value: "resnext-chroma-hd", label: "🚀 ResNeXt High-Res Chroma Fusion (Native Detail)" },
    { value: "resnext-comicolor", label: "🎨 ResNeXt Comicolorization Pipeline" }
  ],
  google_nano: [
    { value: "gemini-3.1-flash-image", label: "🍌 Gemini 3.1 Flash Image (Nano Banana - Recommended)" },
    { value: "gemini-3-pro-image", label: "💎 Gemini 3 Pro Image (4K Studio Quality)" },
    { value: "gemini-3.1-flash-lite-image", label: "⚡ Gemini 3.1 Flash Lite Image (Fast Vision)" },
    { value: "gemini-2.5-flash-image", label: "✨ Gemini 2.5 Flash Image" },
    { value: "imagen-3.0-generate-002", label: "🎨 Google Imagen 3 Colorizer" },
    { value: "nano-banana", label: "🍌 Google Nano Banana (Default Alias)" }
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
  if (selectElement.classList.contains("form-select-sm") || selectElement.classList.contains("custom-select-sm")) {
    container.classList.add("custom-select-sm");
  }
  if (selectElement.style.flex) {
    container.style.flex = selectElement.style.flex;
  }
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

    let lastGroup = null;
    options.forEach((opt, idx) => {
      const groupLabel = opt.parentElement && opt.parentElement.tagName === "OPTGROUP" ? opt.parentElement.label : null;
      if (groupLabel && groupLabel !== lastGroup) {
        lastGroup = groupLabel;
        const grpHdr = document.createElement("div");
        grpHdr.className = "custom-select-group-header";
        grpHdr.textContent = groupLabel;
        optionsContainer.appendChild(grpHdr);
      }

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
      container.classList.add("open-upwards");
    } else {
      dropdown.style.top = "calc(100% + 6px)";
      dropdown.style.bottom = "auto";
      dropdown.style.transformOrigin = "top center";
      container.classList.remove("open-upwards");
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
    container.classList.remove("open-upwards");
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
  document.querySelectorAll("select.form-select, select:not(.no-custom)").forEach(initCustomSelect);
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


// Sidebar Cards Collapsible & Expandable System
const SIDEBAR_CARDS = [
  { id: "card-doc-queue", headerId: "header-doc-queue", btnId: "btn-collapse-doc-queue", key: "doc_queue", label: "Document Queue" },
  { id: "config-card", headerId: "header-config", btnId: "btn-collapse-config", key: "config", label: "AI Engine & Models" },
  { id: "palette-card", headerId: "header-palette", btnId: "btn-collapse-palette", key: "palette", label: "Character Palette" },
  { id: "sidebar-export-card", headerId: "header-export", btnId: "btn-collapse-export", key: "export", label: "Export Manga" }
];

function loadSidebarCollapsedStates() {
  try {
    return JSON.parse(localStorage.getItem("kobean_sidebar_cards_collapsed") || "{}");
  } catch (e) {
    return {};
  }
}

function saveSidebarCollapsedState(key, isCollapsed) {
  try {
    const states = loadSidebarCollapsedStates();
    states[key] = isCollapsed;
    localStorage.setItem("kobean_sidebar_cards_collapsed", JSON.stringify(states));
  } catch (e) {}
}

function toggleSidebarCard(cardId, forceState) {
  const cfg = SIDEBAR_CARDS.find(c => c.id === cardId);
  const card = document.getElementById(cardId);
  if (!card) return;

  const header = cfg ? document.getElementById(cfg.headerId) : card.querySelector(".card-collapsible-header");
  const btn = cfg ? document.getElementById(cfg.btnId) : card.querySelector(".btn-card-collapse");
  const body = card.querySelector(".card-collapsible-body");
  const label = cfg ? cfg.label : "Card";

  const isCurrentlyCollapsed = card.classList.contains("collapsed");
  const willCollapse = (forceState !== undefined) ? forceState : !isCurrentlyCollapsed;

  // Add animating flag for smooth transition
  card.classList.add("is-animating");

  if (body) {
    const onEnd = (e) => {
      if (e.target === body && (e.propertyName === "grid-template-rows" || e.propertyName === "opacity")) {
        card.classList.remove("is-animating");
        body.removeEventListener("transitionend", onEnd);
      }
    };
    body.addEventListener("transitionend", onEnd);
    setTimeout(() => card.classList.remove("is-animating"), 400);
  }

  if (willCollapse) {
    card.classList.add("collapsed");
    if (header) header.setAttribute("aria-expanded", "false");
    if (btn) {
      btn.setAttribute("aria-expanded", "false");
      btn.title = `Expand ${label}`;
      btn.setAttribute("aria-label", `Expand ${label}`);
    }
    // Close any active custom-select dropdowns within this card
    card.querySelectorAll(".custom-select-container.open").forEach(c => {
      c.classList.remove("open");
      const trig = c.querySelector(".custom-select-trigger");
      if (trig) trig.setAttribute("aria-expanded", "false");
    });
  } else {
    card.classList.remove("collapsed");
    if (header) header.setAttribute("aria-expanded", "true");
    if (btn) {
      btn.setAttribute("aria-expanded", "true");
      btn.title = `Collapse ${label}`;
      btn.setAttribute("aria-label", `Collapse ${label}`);
    }
  }

  if (cfg) {
    saveSidebarCollapsedState(cfg.key, willCollapse);
  }
}

function updateSidebarConfigSummary(provider) {
  const summaryBadge = document.getElementById("config-card-summary-badge");
  if (!summaryBadge) return;
  if (provider === "resnext_generator") {
    summaryBadge.innerText = "🧬 ResNeXt Net";
  } else if (provider === "google_nano") {
    summaryBadge.innerText = "🍌 Google Nano";
  } else if (provider === "apple_foundation") {
    summaryBadge.innerText = "🍏 Apple AI";
  } else {
    summaryBadge.innerText = "🎨 Smart Local";
  }
}

function initSidebarCollapsibleCards() {
  const savedStates = loadSidebarCollapsedStates();

  SIDEBAR_CARDS.forEach(cfg => {
    const card = document.getElementById(cfg.id);
    const header = document.getElementById(cfg.headerId);
    const btn = document.getElementById(cfg.btnId);
    if (!card) return;

    // Restore saved state without animation
    if (savedStates[cfg.key] === true) {
      card.classList.add("collapsed");
      if (header) header.setAttribute("aria-expanded", "false");
      if (btn) {
        btn.setAttribute("aria-expanded", "false");
        btn.title = `Expand ${cfg.label}`;
        btn.setAttribute("aria-label", `Expand ${cfg.label}`);
      }
    }

    // Bind header click
    if (header) {
      header.addEventListener("click", (e) => {
        // Prevent toggle if clicking interactive controls
        if (e.target.closest("button:not(.btn-card-collapse), a, input, select, textarea, .custom-select-container, .badge")) {
          return;
        }
        toggleSidebarCard(cfg.id);
      });

      header.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          if (e.target.closest("button, a, input, select, textarea")) return;
          e.preventDefault();
          toggleSidebarCard(cfg.id);
        }
      });
    }

    // Bind button click
    if (btn) {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleSidebarCard(cfg.id);
      });
    }
  });
}

/* ============================================================
   Sidebar Drawer Collapse & Expand System (Left Edge Dock)
   ============================================================ */

const SIDEBAR_DRAWER_STORAGE_KEY = "kobean_sidebar_drawer_collapsed";

function isSidebarDrawerCollapsed() {
  const dashboard = document.getElementById("dashboard-section");
  return dashboard ? dashboard.classList.contains("sidebar-collapsed") : false;
}

function toggleSidebarDrawer(forceCollapsed) {
  const dashboard = document.getElementById("dashboard-section");
  const edgeBtn = document.getElementById("btn-sidebar-edge-expand");
  const collapseBtn = document.getElementById("btn-sidebar-collapse");
  const sidebar = document.getElementById("app-sidebar");
  if (!dashboard) return;

  const isCurrentlyCollapsed = dashboard.classList.contains("sidebar-collapsed");
  const willCollapse = (forceCollapsed !== undefined) ? forceCollapsed : !isCurrentlyCollapsed;

  if (willCollapse) {
    dashboard.classList.add("sidebar-collapsed");
    if (sidebar) sidebar.setAttribute("aria-hidden", "true");
    if (edgeBtn) {
      // Only reveal floating edge button if dashboard section is active
      if (!dashboard.classList.contains("hidden")) {
        edgeBtn.classList.remove("hidden");
      }
      edgeBtn.setAttribute("aria-expanded", "false");
    }
    if (collapseBtn) {
      collapseBtn.setAttribute("aria-expanded", "false");
    }
  } else {
    dashboard.classList.remove("sidebar-collapsed");
    if (sidebar) sidebar.removeAttribute("aria-hidden");
    if (edgeBtn) {
      edgeBtn.classList.add("hidden");
      edgeBtn.setAttribute("aria-expanded", "true");
    }
    if (collapseBtn) {
      collapseBtn.setAttribute("aria-expanded", "true");
    }
  }

  try {
    localStorage.setItem(SIDEBAR_DRAWER_STORAGE_KEY, willCollapse ? "true" : "false");
  } catch (e) {}
}

function initSidebarDrawer() {
  const dashboard = document.getElementById("dashboard-section");
  const edgeBtn = document.getElementById("btn-sidebar-edge-expand");
  const collapseBtn = document.getElementById("btn-sidebar-collapse");
  const sidebar = document.getElementById("app-sidebar");
  if (!dashboard) return;

  let savedCollapsed = false;
  try {
    savedCollapsed = localStorage.getItem(SIDEBAR_DRAWER_STORAGE_KEY) === "true";
  } catch (e) {}

  if (savedCollapsed) {
    dashboard.classList.add("sidebar-collapsed");
    if (sidebar) sidebar.setAttribute("aria-hidden", "true");
    if (edgeBtn && !dashboard.classList.contains("hidden")) {
      edgeBtn.classList.remove("hidden");
      edgeBtn.setAttribute("aria-expanded", "false");
    }
    if (collapseBtn) {
      collapseBtn.setAttribute("aria-expanded", "false");
    }
  } else {
    if (collapseBtn) {
      collapseBtn.setAttribute("aria-expanded", "true");
    }
  }

  // Keyboard shortcut: Cmd+B (Mac) or Ctrl+B (Windows/Linux)
  window.addEventListener("keydown", (e) => {
    const activeEl = document.activeElement;
    if (activeEl && (activeEl.tagName === "INPUT" || activeEl.tagName === "TEXTAREA" || activeEl.isContentEditable)) {
      return;
    }
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
      e.preventDefault();
      // Only toggle when dashboard is visible
      if (!dashboard.classList.contains("hidden")) {
        toggleSidebarDrawer();
      }
    }
  });

  if (collapseBtn) {
    collapseBtn.addEventListener("click", () => toggleSidebarDrawer(true));
  }
  if (edgeBtn) {
    edgeBtn.addEventListener("click", () => toggleSidebarDrawer(false));
  }
}

document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  updateModelVariants("resnext_generator");
  initAllCustomSelects();
  loadMangaPresets();
  initSidebarCollapsibleCards();
  initSidebarDrawer();

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
          subscribeToProgressStream(data.session_id, true);
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
            exportBannerDismissed = false;
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
      const folderModal = document.getElementById("folder-import-modal-overlay");
      const browserModal = document.getElementById("folder-browser-modal-overlay");
      const confirmModal = document.getElementById("custom-confirm-modal-overlay");
      if ((folderModal && !folderModal.classList.contains("hidden")) ||
          (browserModal && !browserModal.classList.contains("hidden")) ||
          (confirmModal && !confirmModal.classList.contains("hidden"))) return;
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
    const folderModal = document.getElementById("folder-import-modal-overlay");
    const browserModal = document.getElementById("folder-browser-modal-overlay");
    const confirmModal = document.getElementById("custom-confirm-modal-overlay");
    if ((folderModal && !folderModal.classList.contains("hidden")) ||
        (browserModal && !browserModal.classList.contains("hidden")) ||
        (confirmModal && !confirmModal.classList.contains("hidden"))) {
      e.preventDefault();
      return;
    }
    e.preventDefault();
    const dropzone = document.getElementById("dropzone");
    if (dropzone) dropzone.classList.remove("dragover");
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelection(e.dataTransfer.files);
    }
  });

  // Folder Import Modal Dropzone & Path listeners
  const folderDropzone = document.getElementById("folder-import-dropzone");
  if (folderDropzone) {
    ["dragenter", "dragover"].forEach(eventName => {
      folderDropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        folderDropzone.classList.add("dragover");
      });
    });

    ["dragleave", "dragend"].forEach(eventName => {
      folderDropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        folderDropzone.classList.remove("dragover");
      });
    });

    folderDropzone.addEventListener("drop", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      folderDropzone.classList.remove("dragover");
      await handleFolderDropzoneDrop(e);
    });
  }

  const folderPathInput = document.getElementById("folder-import-path");
  if (folderPathInput) {
    folderPathInput.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.stopPropagation();
    });
    folderPathInput.addEventListener("drop", (e) => {
      e.stopPropagation();
      const text = e.dataTransfer.getData("text/plain") || e.dataTransfer.getData("text/uri-list");
      if (text) {
        e.preventDefault();
        folderPathInput.value = text.trim();
        onFolderInputChanged(folderPathInput.value);
      } else if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        const f = e.dataTransfer.files[0];
        if (f.path) {
          e.preventDefault();
          folderPathInput.value = f.path;
          onFolderInputChanged(folderPathInput.value);
        }
      }
    });
  }

  // Keyboard navigation for split comparator & modal dismissal (Escape, ArrowLeft, ArrowRight)
  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      const confirmOverlay = document.getElementById("custom-confirm-modal-overlay");
      if (confirmOverlay && !confirmOverlay.classList.contains("hidden")) {
        resolveCustomConfirm(false);
        return;
      }
      const browserOverlay = document.getElementById("folder-browser-modal-overlay");
      if (browserOverlay && !browserOverlay.classList.contains("hidden")) {
        closeFolderBrowserModal();
        return;
      }
      const folderOverlay = document.getElementById("folder-import-modal-overlay");
      if (folderOverlay && !folderOverlay.classList.contains("hidden")) {
        closeFolderImportModal();
        return;
      }
      const histOverlay = document.getElementById("history-modal-overlay");
      if (histOverlay && !histOverlay.classList.contains("hidden")) {
        closeHistoryModal();
        return;
      }
      const exemplarOverlay = document.getElementById("exemplar-gallery-modal-overlay");
      if (exemplarOverlay && !exemplarOverlay.classList.contains("hidden")) {
        closeExemplarGalleryModal();
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
      const openZoomMenu = document.querySelector(".zoom-dropdown-wrapper.open");
      if (openZoomMenu) {
        closeAllZoomMenus();
        return;
      }
      const card = document.getElementById("split-preview-card");
      if (card && (card.classList.contains("is-fullscreen") || document.fullscreenElement)) {
        toggleComparatorFullscreen();
      } else {
        closeSplitPreview();
      }
    } else if (e.key === "f" || e.key === "F") {
      e.preventDefault();
      toggleComparatorFullscreen();
    } else if (e.key === "+" || e.key === "=") {
      e.preventDefault();
      changeComparatorZoom(0.25);
    } else if (e.key === "-" || e.key === "_") {
      e.preventDefault();
      changeComparatorZoom(-0.25);
    } else if (e.key === "0") {
      e.preventDefault();
      resetComparatorZoom();
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

  // Combined Export Preset & Grayscale sync
  const combinedPreset = document.getElementById("combined-preset-select");
  const combinedGray = document.getElementById("combined-grayscale-check");
  if (combinedPreset && combinedGray) {
    combinedPreset.addEventListener("change", () => {
      if (combinedPreset.value === "colorsoft" && combinedGray.checked) {
        combinedGray.checked = false;
      }
    });
    combinedGray.addEventListener("change", () => {
      if (combinedGray.checked && combinedPreset.value === "colorsoft") {
        combinedPreset.value = "kindle";
        combinedPreset.dispatchEvent(new Event("change", { bubbles: true }));
      }
    });
  }

  // Combined Export Original Versions toggle
  const combinedOriginal = document.getElementById("combined-original-check");
  const combinedTitleInput = document.getElementById("combined-title-input");
  if (combinedOriginal && combinedTitleInput) {
    combinedOriginal.addEventListener("change", () => {
      if (combinedOriginal.checked) {
        if (combinedTitleInput.value === "Colorized Manga Collection") {
          combinedTitleInput.value = "Manga Collection";
        }
        if (combinedPreset && combinedPreset.value === "colorsoft") {
          combinedPreset.value = "original";
          combinedPreset.dispatchEvent(new Event("change", { bubbles: true }));
        }
      } else {
        if (combinedTitleInput.value === "Manga Collection") {
          combinedTitleInput.value = "Colorized Manga Collection";
        }
      }
    });
  }

  // Combined Chunk & Custom Size sync
  const combinedChunk = document.getElementById("combined-chunk-select");
  const customSizeBox = document.getElementById("combined-custom-size-box");
  if (combinedChunk && customSizeBox) {
    combinedChunk.addEventListener("change", () => {
      if (combinedChunk.value === "size_custom") {
        customSizeBox.classList.remove("hidden");
      } else {
        customSizeBox.classList.add("hidden");
      }
    });
  }

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

  updateSidebarConfigSummary(provider);
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
  const allowed = ["pdf", "epub", "png", "jpg", "jpeg", "webp", "bmp", "gif", "tiff", "zip", "cbz"];
  const fileList = Array.from(fileOrFiles instanceof FileList ? fileOrFiles : (Array.isArray(fileOrFiles) ? fileOrFiles : [fileOrFiles]));

  const validFiles = fileList.filter(f => {
    const ext = f.name.split(".").pop().toLowerCase();
    return allowed.includes(ext);
  });

  if (validFiles.length === 0) {
    showToast("Supported formats: .pdf, .epub, .cbz, images (.png, .jpg, .webp) & .zip", "error");
    return;
  }

  // If selecting more than 5 files (or large batch up to +1076 files), use chunked batch uploader
  if (validFiles.length > 5) {
    if (addBtn) {
      addBtn.disabled = false;
      addBtn.innerHTML = origAddBtnHTML;
    }
    await handleBulkChunkedUpload(validFiles);
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

// Optimized chunked uploader for importing large numbers of files (+1076 files)
async function handleBulkChunkedUpload(files) {
  isImportCancelled = false;
  const totalFiles = files.length;
  const chunkSize = 8; // Upload 8 files per chunk to avoid browser payload timeouts
  const totalChunks = Math.ceil(totalFiles / chunkSize);
  const startTime = Date.now();

  openImportProgressModal(totalFiles);

  let successCount = 0;
  let failCount = 0;
  let firstUploadedSessionId = null;

  for (let i = 0; i < totalChunks; i++) {
    if (isImportCancelled) {
      showToast("Batch import cancelled by user.", "info");
      break;
    }

    const chunk = files.slice(i * chunkSize, (i + 1) * chunkSize);
    const chunkNames = chunk.map(f => f.name).join(", ");
    updateImportProgressModal(
      successCount + failCount,
      totalFiles,
      chunkNames,
      i + 1,
      totalChunks,
      successCount,
      failCount,
      startTime
    );

    const formData = new FormData();
    if (currentBatchId) {
      formData.append("batch_id", currentBatchId);
    }
    chunk.forEach(f => formData.append("files", f));

    try {
      const resp = await fetch("/api/upload", {
        method: "POST",
        body: formData
      });
      const data = await resp.json();
      if (resp.ok && data.status === "success") {
        successCount += chunk.length;
        if (!firstUploadedSessionId && data.session_id) {
          firstUploadedSessionId = data.session_id;
        }
        if (data.batch_id) {
          currentBatchId = data.batch_id;
          sessionStorage.setItem("active_batch_id", currentBatchId);
        }
      } else {
        failCount += chunk.length;
        console.error("Chunk upload error:", data.detail);
      }
    } catch (err) {
      failCount += chunk.length;
      console.error("Chunk upload fetch error:", err);
    }

    updateImportProgressModal(
      successCount + failCount,
      totalFiles,
      chunkNames,
      i + 1,
      totalChunks,
      successCount,
      failCount,
      startTime
    );
  }

  // Refresh sessions after upload finishes
  try {
    const sessRes = await fetch("/api/sessions");
    if (sessRes.ok) {
      const sessData = await sessRes.json();
      if (sessData && sessData.sessions) {
        activeSessions = sessData.sessions;
      }
    }

    if (firstUploadedSessionId && (!currentSession || !activeSessions.some(s => s.session_id === currentSession.session_id))) {
      const fullSessRes = await fetch(`/api/session/${firstUploadedSessionId}`);
      if (fullSessRes.ok) {
        currentSession = await fullSessRes.json();
        sessionStorage.setItem("active_session_id", currentSession.session_id);
      }
    }
  } catch (err) {
    console.error("Error refreshing sessions after bulk upload:", err);
  }

  renderDashboard();
  renderDocumentQueue();

  setTimeout(() => {
    closeImportProgressModal();
    if (successCount > 0) {
      showToast(`Successfully imported ${successCount} document(s)!${failCount > 0 ? ` (${failCount} failed)` : ""}`, "success");
    } else {
      showToast("Bulk import completed with errors.", "error");
    }
  }, 1000);

  const addMore = document.getElementById("add-more-input");
  if (addMore) addMore.value = "";
  const fileInput = document.getElementById("file-input");
  if (fileInput) fileInput.value = "";
}

// Bulk Import Progress Modal Controls
function openImportProgressModal(totalCount) {
  const overlay = document.getElementById("import-progress-modal-overlay");
  const fill = document.getElementById("bulk-import-progress-fill");
  const statusText = document.getElementById("bulk-import-status-text");
  const etaText = document.getElementById("bulk-import-eta");
  const curFile = document.getElementById("bulk-import-current-file");
  const chunkText = document.getElementById("bulk-import-chunk");
  const successText = document.getElementById("bulk-import-success-count");
  const failText = document.getElementById("bulk-import-fail-count");
  const cancelBtn = document.getElementById("btn-cancel-bulk-import");

  if (fill) fill.style.width = "0%";
  if (statusText) statusText.innerText = `Importing 0 of ${totalCount} files (0%)`;
  if (etaText) etaText.innerText = "Calculating ETA...";
  if (curFile) curFile.innerText = "Starting batch upload...";
  if (chunkText) chunkText.innerText = "1 / 1";
  if (successText) successText.innerText = "0";
  if (failText) failText.innerText = "0";
  if (cancelBtn) {
    cancelBtn.disabled = false;
    cancelBtn.innerHTML = '<i class="ri-close-circle-line"></i> Cancel Import';
  }

  if (overlay) overlay.classList.remove("hidden");
}

function updateImportProgressModal(processed, total, currentFile, chunkNum, totalChunks, successCount, failCount, startTime) {
  const fill = document.getElementById("bulk-import-progress-fill");
  const statusText = document.getElementById("bulk-import-status-text");
  const etaText = document.getElementById("bulk-import-eta");
  const curFile = document.getElementById("bulk-import-current-file");
  const chunkText = document.getElementById("bulk-import-chunk");
  const successText = document.getElementById("bulk-import-success-count");
  const failText = document.getElementById("bulk-import-fail-count");

  const pct = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;
  if (fill) fill.style.width = `${pct}%`;
  if (statusText) statusText.innerText = `Importing ${processed} of ${total} files (${pct}%)`;

  if (startTime && processed > 0 && processed < total) {
    const elapsedSec = (Date.now() - startTime) / 1000;
    const secPerItem = elapsedSec / processed;
    const remSec = Math.round(secPerItem * (total - processed));
    if (etaText) {
      if (remSec > 60) {
        etaText.innerText = `~${Math.ceil(remSec / 60)} min remaining`;
      } else {
        etaText.innerText = `~${remSec}s remaining`;
      }
    }
  } else if (processed >= total && etaText) {
    etaText.innerText = "Complete!";
  }

  if (curFile && currentFile) curFile.innerText = currentFile;
  if (chunkText) chunkText.innerText = `${chunkNum} / ${totalChunks}`;
  if (successText) successText.innerText = successCount;
  if (failText) failText.innerText = failCount;
}

function closeImportProgressModal() {
  const overlay = document.getElementById("import-progress-modal-overlay");
  if (overlay) overlay.classList.add("hidden");
}

function cancelBatchImport() {
  isImportCancelled = true;
  const cancelBtn = document.getElementById("btn-cancel-bulk-import");
  if (cancelBtn) {
    cancelBtn.disabled = true;
    cancelBtn.innerHTML = '<i class="ri-loader-4-line spin"></i> Cancelling...';
  }
  showToast("Cancelling import...", "info");
}

// Custom Confirmation Modal
let confirmModalResolver = null;

function showConfirmModal({ title = "Confirm Action", message = "Are you sure?", confirmText = "Confirm", isDanger = true } = {}) {
  return new Promise((resolve) => {
    confirmModalResolver = resolve;
    const overlay = document.getElementById("custom-confirm-modal-overlay");
    const titleEl = document.getElementById("confirm-modal-title");
    const msgEl = document.getElementById("confirm-modal-message");
    const okBtn = document.getElementById("btn-confirm-modal-ok");
    const iconEl = document.getElementById("confirm-modal-icon");

    if (titleEl) titleEl.innerText = title;
    if (msgEl) msgEl.innerText = message;
    if (okBtn) {
      okBtn.innerText = confirmText;
      okBtn.className = isDanger ? "btn btn-danger btn-sm" : "btn btn-primary btn-sm";
    }
    if (iconEl) {
      iconEl.style.background = isDanger ? "rgba(239, 68, 68, 0.15)" : "rgba(6, 182, 212, 0.15)";
      iconEl.style.color = isDanger ? "#ef4444" : "var(--accent-cyan)";
      iconEl.innerHTML = isDanger ? '<i class="ri-error-warning-line"></i>' : '<i class="ri-information-line"></i>';
    }
    if (overlay) overlay.classList.remove("hidden");
  });
}

function resolveCustomConfirm(result) {
  const overlay = document.getElementById("custom-confirm-modal-overlay");
  if (overlay) overlay.classList.add("hidden");
  if (confirmModalResolver) {
    confirmModalResolver(result);
    confirmModalResolver = null;
  }
}

function handleCustomConfirmOverlayClick(event) {
  if (event.target.id === "custom-confirm-modal-overlay") {
    resolveCustomConfirm(false);
  }
}

// Custom Local Folder Browser Modal Controls & State
let browserCurrentPath = "";
let browserParentPath = null;
let browserSelectedPath = "";
let browserSubdirectories = [];

async function openFolderBrowserModal(startPath = null) {
  const overlay = document.getElementById("folder-browser-modal-overlay");
  if (overlay) overlay.classList.remove("hidden");

  let initial = startPath;
  if (!initial) {
    const pathInput = document.getElementById("folder-import-path");
    if (pathInput && pathInput.value && !pathInput.value.startsWith("[Browser Selected]")) {
      initial = pathInput.value.trim();
    }
  }

  await loadBrowserDirectory(initial);
}

function closeFolderBrowserModal() {
  const overlay = document.getElementById("folder-browser-modal-overlay");
  if (overlay) overlay.classList.add("hidden");
}

function handleFolderBrowserOverlayClick(event) {
  if (event.target.id === "folder-browser-modal-overlay") {
    closeFolderBrowserModal();
  }
}

async function loadBrowserDirectory(dirPath = null) {
  const listEl = document.getElementById("folder-browser-list");
  if (listEl) {
    listEl.innerHTML = '<div class="folder-browser-empty"><i class="ri-loader-4-line spin" style="font-size: 1.5rem; color: var(--accent-cyan);"></i><span>Loading directories...</span></div>';
  }

  try {
    const url = dirPath ? `/api/import/browse-directory?path=${encodeURIComponent(dirPath)}` : "/api/import/browse-directory";
    const res = await fetch(url);
    if (!res.ok) {
      if (listEl) {
        listEl.innerHTML = '<div class="folder-browser-empty"><i class="ri-error-warning-line" style="font-size: 1.5rem; color: #ef4444;"></i><span>Failed to load directory</span></div>';
      }
      return;
    }

    const data = await res.json();
    browserCurrentPath = data.current_path;
    browserParentPath = data.parent_path;
    browserSubdirectories = data.directories || [];
    browserSelectedPath = data.current_path;

    updateBrowserSelectedDisplay(browserCurrentPath, data.ebooks_here_count);
    renderBrowserQuickRoots(data.quick_roots || []);
    renderBrowserBreadcrumbs(data.breadcrumbs || []);
    renderBrowserSubdirectories(browserSubdirectories);
    renderBrowserInfoBar(data);

    const filterInput = document.getElementById("folder-browser-filter-input");
    if (filterInput) filterInput.value = "";

    const upBtn = document.getElementById("btn-browser-up");
    if (upBtn) upBtn.disabled = !browserParentPath || browserParentPath === browserCurrentPath;
  } catch (err) {
    if (listEl) {
      listEl.innerHTML = `<div class="folder-browser-empty"><i class="ri-error-warning-line" style="font-size: 1.5rem; color: #ef4444;"></i><span>${escapeHtml(err.message)}</span></div>`;
    }
  }
}

function renderBrowserQuickRoots(roots) {
  const container = document.getElementById("folder-browser-quick-roots");
  if (!container) return;
  container.innerHTML = "";

  roots.forEach(r => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = `browser-root-chip ${browserCurrentPath === r.path ? "active" : ""}`;
    chip.innerHTML = `<i class="${r.icon || 'ri-folder-line'}"></i> ${escapeHtml(r.name)}`;
    chip.onclick = () => loadBrowserDirectory(r.path);
    container.appendChild(chip);
  });
}

function renderBrowserBreadcrumbs(breadcrumbs) {
  const container = document.getElementById("folder-browser-breadcrumbs");
  if (!container) return;
  container.innerHTML = "";

  breadcrumbs.forEach((crumb, idx) => {
    if (idx > 0) {
      const sep = document.createElement("span");
      sep.className = "breadcrumb-separator";
      sep.innerText = "/";
      container.appendChild(sep);
    }
    const item = document.createElement("span");
    const isLast = idx === breadcrumbs.length - 1;
    item.className = `breadcrumb-item ${isLast ? "active" : ""}`;
    item.innerText = crumb.name;
    if (!isLast) {
      item.onclick = () => loadBrowserDirectory(crumb.path);
    }
    container.appendChild(item);
  });

  container.scrollLeft = container.scrollWidth;
}

function renderBrowserSubdirectories(dirs) {
  const listEl = document.getElementById("folder-browser-list");
  if (!listEl) return;
  listEl.innerHTML = "";

  if (!dirs || dirs.length === 0) {
    listEl.innerHTML = '<div class="folder-browser-empty"><i class="ri-folder-info-line" style="font-size: 1.5rem;"></i><span>No subfolders in this directory</span></div>';
    return;
  }

  dirs.forEach(d => {
    const item = document.createElement("div");
    item.className = `folder-browser-item ${browserSelectedPath === d.path ? "selected" : ""}`;
    item.dataset.path = d.path;

    const badgeHtml = d.ebook_count > 0 ? `<span class="folder-ebook-badge">${d.ebook_count} ebook${d.ebook_count > 1 ? 's' : ''}</span>` : '';

    item.innerHTML = `
      <div class="folder-browser-item-icon">
        <i class="ri-folder-fill"></i>
      </div>
      <div class="folder-browser-item-details">
        <div class="folder-browser-item-name" title="${escapeHtml(d.name)}">${escapeHtml(d.name)}</div>
        <div class="folder-browser-item-meta">
          ${badgeHtml || '<span style="color: var(--text-muted);">folder</span>'}
        </div>
      </div>
      <button type="button" class="btn-icon" style="padding: 2px; color: var(--text-muted);" title="Open folder">
        <i class="ri-arrow-right-s-line"></i>
      </button>
    `;

    item.onclick = (e) => {
      if (e.target.closest(".btn-icon")) {
        loadBrowserDirectory(d.path);
        return;
      }
      selectBrowserItem(d.path, d.ebook_count, item);
    };

    item.ondblclick = () => {
      loadBrowserDirectory(d.path);
    };

    listEl.appendChild(item);
  });
}

function selectBrowserItem(path, ebookCount, element) {
  browserSelectedPath = path;
  document.querySelectorAll(".folder-browser-item").forEach(el => el.classList.remove("selected"));
  if (element) element.classList.add("selected");
  updateBrowserSelectedDisplay(path, ebookCount);
}

function updateBrowserSelectedDisplay(path, ebookCount = null) {
  const display = document.getElementById("folder-browser-selected-path");
  if (display) {
    const countText = typeof ebookCount === "number" && ebookCount > 0 ? ` (${ebookCount} ebook files)` : "";
    display.innerText = `${path}${countText}`;
  }
}

function renderBrowserInfoBar(data) {
  const bar = document.getElementById("folder-browser-info-bar");
  if (!bar) return;
  const count = data.ebooks_here_count || 0;
  if (count > 0) {
    const sample = data.sample_ebooks && data.sample_ebooks.length > 0 ? ` (e.g. ${data.sample_ebooks.slice(0, 3).join(", ")})` : "";
    bar.innerHTML = `<i class="ri-checkbox-circle-fill" style="color: var(--accent-cyan);"></i> <span>Current directory contains <strong>${count}</strong> ebook file${count > 1 ? 's' : ''}${sample}.</span>`;
  } else {
    bar.innerHTML = '<i class="ri-information-line" style="color: var(--text-muted);"></i> <span>Navigate into a manga folder or choose one above.</span>';
  }
}

function filterBrowserFolders(query) {
  const q = (query || "").toLowerCase().trim();
  const items = document.querySelectorAll(".folder-browser-item");
  items.forEach(item => {
    const nameEl = item.querySelector(".folder-browser-item-name");
    const name = nameEl ? nameEl.innerText.toLowerCase() : "";
    if (!q || name.includes(q)) {
      item.style.display = "";
    } else {
      item.style.display = "none";
    }
  });
}

function navigateBrowserUp() {
  if (browserParentPath && browserParentPath !== browserCurrentPath) {
    loadBrowserDirectory(browserParentPath);
  }
}

function confirmFolderBrowserSelection() {
  const selectedPath = browserSelectedPath || browserCurrentPath;
  if (!selectedPath) return;

  const pathInput = document.getElementById("folder-import-path");
  if (pathInput) {
    pathInput.value = selectedPath;
    validateAndDisplayFolderPath(selectedPath);
  }

  closeFolderBrowserModal();
}

// Local Folder Import Modal Controls & State
let chosenFolderFiles = [];
let folderValidationTimeout = null;

function triggerFolderPicker() {
  openFolderBrowserModal();
}

function handleFolderPickerSelection(event) {
  const files = event.target.files ? Array.from(event.target.files) : [];
  processChosenFiles(files);
}

function processChosenFiles(files) {
  if (!files || files.length === 0) return;

  const ALLOWED_EXTS = [".pdf", ".epub", ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".zip", ".cbz"];
  const validFiles = files.filter(f => {
    const ext = "." + f.name.split(".").pop().toLowerCase();
    return ALLOWED_EXTS.includes(ext);
  });

  chosenFolderFiles = validFiles;

  let folderName = "";
  let detectedPath = "";

  if (files[0]) {
    if (files[0].path) {
      const p = files[0].path;
      const rel = files[0].webkitRelativePath || files[0].name;
      if (p.endsWith(rel)) {
        const rootDirName = rel.split("/")[0];
        detectedPath = p.substring(0, p.length - rel.length) + rootDirName;
      } else {
        detectedPath = p.substring(0, p.lastIndexOf("/"));
      }
    }

    if (files[0].webkitRelativePath && files[0].webkitRelativePath.includes("/")) {
      folderName = files[0].webkitRelativePath.split("/")[0];
    } else {
      folderName = files[0].name ? files[0].name.split("/")[0] : "Selected Folder";
    }
  }

  const dropLabel = document.getElementById("folder-dropzone-label");
  const dropSub = document.getElementById("folder-dropzone-sub");
  const pathInput = document.getElementById("folder-import-path");

  if (dropLabel) {
    dropLabel.innerHTML = `<i class="ri-folder-check-line" style="color: var(--accent-cyan); margin-right: 6px;"></i> Selected: <strong>${escapeHtml(folderName || "Folder")}</strong> (${validFiles.length} ebook files)`;
  }
  if (dropSub) {
    dropSub.innerText = `${validFiles.length} file(s) ready for import. Click "Start Import" below.`;
  }

  if (detectedPath) {
    if (pathInput) {
      pathInput.value = detectedPath;
      validateAndDisplayFolderPath(detectedPath);
    }
  } else {
    if (pathInput && !pathInput.value.trim()) {
      pathInput.value = folderName ? folderName : "";
    }
    const valDiv = document.getElementById("folder-path-validation");
    if (valDiv) {
      valDiv.innerHTML = `<span class="folder-validation-success"><i class="ri-checkbox-circle-fill"></i> Selected folder ready (${validFiles.length} ebook file(s) queued for import)</span>`;
    }
  }
}

async function handleFolderDropzoneDrop(e) {
  const text = e.dataTransfer.getData("text/plain") || e.dataTransfer.getData("text/uri-list");
  if (text && (text.startsWith("/") || text.startsWith("file://") || text.startsWith("~") || text.startsWith('"'))) {
    const pathInput = document.getElementById("folder-import-path");
    if (pathInput) {
      pathInput.value = text.trim();
      validateAndDisplayFolderPath(text.trim());
    }
  }

  const files = await scanFilesFromDataTransfer(e.dataTransfer);
  if (files && files.length > 0) {
    processChosenFiles(files);
  }
}

async function scanFilesFromDataTransfer(dataTransfer) {
  const files = [];
  if (dataTransfer.items && dataTransfer.items.length > 0) {
    const entries = [];
    for (let i = 0; i < dataTransfer.items.length; i++) {
      const item = dataTransfer.items[i];
      if (item.webkitGetAsEntry) {
        const entry = item.webkitGetAsEntry();
        if (entry) entries.push(entry);
      }
    }

    if (entries.length > 0) {
      async function readAllDirEntries(dirReader) {
        let allEntries = [];
        let batch;
        do {
          batch = await new Promise((resolve) => {
            dirReader.readEntries(resolve, () => resolve([]));
          });
          if (batch && batch.length > 0) {
            allEntries = allEntries.concat(batch);
          }
        } while (batch && batch.length > 0);
        return allEntries;
      }

      async function traverse(entry) {
        if (!entry) return;
        if (entry.isFile) {
          try {
            const file = await new Promise((res, rej) => entry.file(res, rej));
            files.push(file);
          } catch (err) {
            console.warn("Could not read file entry:", err);
          }
        } else if (entry.isDirectory) {
          try {
            const reader = entry.createReader();
            const children = await readAllDirEntries(reader);
            for (const child of children) {
              await traverse(child);
            }
          } catch (err) {
            console.warn("Could not read directory entry:", err);
          }
        }
      }

      for (const entry of entries) {
        await traverse(entry);
      }
      if (files.length > 0) {
        return files;
      }
    }
  }

  return Array.from(dataTransfer.files || []);
}

function setFolderPath(path) {
  const pathInput = document.getElementById("folder-import-path");
  if (pathInput) {
    pathInput.value = path;
    validateAndDisplayFolderPath(path);
    pathInput.focus();
  }
}

function onFolderInputChanged(val) {
  if (folderValidationTimeout) clearTimeout(folderValidationTimeout);
  folderValidationTimeout = setTimeout(() => {
    validateAndDisplayFolderPath(val);
  }, 300);
}

async function validateAndDisplayFolderPath(rawVal) {
  const statusEl = document.getElementById("folder-path-validation");
  if (!statusEl) return;
  const pathVal = (rawVal || "").trim();
  if (!pathVal) {
    statusEl.innerHTML = "";
    return;
  }

  statusEl.innerHTML = '<span style="color: var(--text-muted);"><i class="ri-loader-4-line spin"></i> Checking path...</span>';

  try {
    const res = await fetch(`/api/import/validate-directory?path=${encodeURIComponent(pathVal)}`);
    if (!res.ok) {
      statusEl.innerHTML = '<span class="folder-validation-error"><i class="ri-close-circle-line"></i> Validation request failed</span>';
      return;
    }
    const data = await res.json();
    if (data.valid) {
      const count = data.total_files || 0;
      const fileText = count === 1 ? "1 ebook file" : `${count} ebook files`;
      statusEl.innerHTML = `<span class="folder-validation-success"><i class="ri-checkbox-circle-fill"></i> Valid folder: <code>${escapeHtml(data.resolved_path)}</code> (${fileText} found)</span>`;
      const dropLabel = document.getElementById("folder-dropzone-label");
      if (dropLabel && (!chosenFolderFiles || chosenFolderFiles.length === 0)) {
        dropLabel.innerHTML = `<i class="ri-folder-check-line" style="color: var(--accent-cyan); margin-right: 6px;"></i> ${escapeHtml(data.name)} (${count} files)`;
      }
    } else {
      if (chosenFolderFiles && chosenFolderFiles.length > 0) {
        statusEl.innerHTML = `<span class="folder-validation-success"><i class="ri-checkbox-circle-fill"></i> Ready to import ${chosenFolderFiles.length} file(s) from browser selection</span>`;
      } else {
        statusEl.innerHTML = `<span class="folder-validation-error"><i class="ri-error-warning-line"></i> ${escapeHtml(data.error || "Directory not found on host")}</span>`;
      }
    }
  } catch (err) {
    if (chosenFolderFiles && chosenFolderFiles.length > 0) {
      statusEl.innerHTML = `<span class="folder-validation-success"><i class="ri-checkbox-circle-fill"></i> Ready to import ${chosenFolderFiles.length} file(s) from browser selection</span>`;
    } else {
      statusEl.innerHTML = `<span class="folder-validation-error"><i class="ri-error-warning-line"></i> Check failed: ${escapeHtml(err.message)}</span>`;
    }
  }
}

function openFolderImportModal() {
  chosenFolderFiles = [];
  const overlay = document.getElementById("folder-import-modal-overlay");
  const progressArea = document.getElementById("folder-import-progress-area");
  const runBtn = document.getElementById("btn-run-folder-import");
  const dropLabel = document.getElementById("folder-dropzone-label");
  const dropSub = document.getElementById("folder-dropzone-sub");
  const valDiv = document.getElementById("folder-path-validation");
  const pathInput = document.getElementById("folder-import-path");

  if (progressArea) progressArea.classList.add("hidden");
  if (runBtn) {
    runBtn.disabled = false;
    runBtn.innerHTML = '<i class="ri-folder-download-line"></i> Start Import';
  }
  if (dropLabel) {
    dropLabel.innerHTML = 'Click to Choose Folder or Drag & Drop Folder Here';
  }
  if (dropSub) {
    dropSub.innerText = 'Choose any folder from your machine with .cbz, .epub, .pdf, or .zip files';
  }
  if (valDiv) valDiv.innerHTML = "";

  if (overlay) overlay.classList.remove("hidden");
  if (pathInput) {
    pathInput.focus();
    if (pathInput.value.trim()) {
      validateAndDisplayFolderPath(pathInput.value);
    }
  }
}

function closeFolderImportModal() {
  const overlay = document.getElementById("folder-import-modal-overlay");
  if (overlay) overlay.classList.add("hidden");
  if (folderImportPoller) {
    clearInterval(folderImportPoller);
    folderImportPoller = null;
  }
}

function handleFolderImportOverlayClick(event) {
  if (event.target.id === "folder-import-modal-overlay") {
    closeFolderImportModal();
  }
}

async function startFolderImport() {
  const pathInput = document.getElementById("folder-import-path");
  const recursiveCb = document.getElementById("folder-import-recursive");
  const maxInput = document.getElementById("folder-import-max");
  const progressArea = document.getElementById("folder-import-progress-area");
  const runBtn = document.getElementById("btn-run-folder-import");

  const rawDirPath = pathInput ? pathInput.value.trim() : "";
  const recursive = recursiveCb ? recursiveCb.checked : true;
  const maxFiles = maxInput ? parseInt(maxInput.value, 10) || 5000 : 5000;

  if (!rawDirPath) {
    if (chosenFolderFiles && chosenFolderFiles.length > 0) {
      closeFolderImportModal();
      await handleBulkChunkedUpload(chosenFolderFiles);
      return;
    }
    showToast("Please enter a valid directory path or choose a folder.", "error");
    if (pathInput) pathInput.focus();
    return;
  }

  if (runBtn) {
    runBtn.disabled = true;
    runBtn.innerHTML = '<i class="ri-loader-4-line spin"></i> Scanning...';
  }
  if (progressArea) progressArea.classList.remove("hidden");

  try {
    const resp = await fetch("/api/import/directory", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        directory_path: rawDirPath,
        recursive: recursive,
        max_files: maxFiles,
        batch_id: currentBatchId || undefined
      })
    });

    const data = await resp.json();
    if (!resp.ok) {
      if (chosenFolderFiles && chosenFolderFiles.length > 0) {
        showToast("Path not found on host; importing chosen folder files via browser upload...", "info");
        closeFolderImportModal();
        await handleBulkChunkedUpload(chosenFolderFiles);
        return;
      }
      showToast(data.detail || "Folder import failed to start.", "error");
      if (runBtn) {
        runBtn.disabled = false;
        runBtn.innerHTML = '<i class="ri-folder-download-line"></i> Start Import';
      }
      return;
    }

    currentImportId = data.import_id;
    if (data.batch_id) {
      currentBatchId = data.batch_id;
      sessionStorage.setItem("active_batch_id", currentBatchId);
    }
    showToast(`Scanning directory: found ${data.total_scanned_files} ebook file(s)...`, "info");
    pollFolderImport(currentImportId);
  } catch (err) {
    if (chosenFolderFiles && chosenFolderFiles.length > 0) {
      showToast("Path not found on host; importing chosen folder files via browser upload...", "info");
      closeFolderImportModal();
      await handleBulkChunkedUpload(chosenFolderFiles);
      return;
    }
    showToast(`Failed to start folder import: ${err.message}`, "error");
    if (runBtn) {
      runBtn.disabled = false;
      runBtn.innerHTML = '<i class="ri-folder-download-line"></i> Start Import';
    }
  }
}

function pollFolderImport(importId) {
  if (folderImportPoller) clearInterval(folderImportPoller);

  const fill = document.getElementById("folder-progress-fill");
  const progressText = document.getElementById("folder-progress-text");
  const progressPct = document.getElementById("folder-progress-pct");
  const progressFile = document.getElementById("folder-progress-file");
  const runBtn = document.getElementById("btn-run-folder-import");

  folderImportPoller = setInterval(async () => {
    try {
      const resp = await fetch(`/api/import/status/${importId}`);
      if (!resp.ok) return;

      const data = await resp.json();
      const pct = data.progress_percent || 0;
      if (fill) fill.style.width = `${pct}%`;
      if (progressPct) progressPct.innerText = `${pct}%`;
      if (progressText) {
        progressText.innerText = `Imported ${data.processed_files} of ${data.total_scanned_files} files`;
      }
      if (progressFile) {
        progressFile.innerText = data.current_file ? `Current: ${data.current_file}` : "";
      }

      if (data.status === "completed") {
        clearInterval(folderImportPoller);
        folderImportPoller = null;
        showToast(`Imported ${data.processed_files} documents successfully!`, "success");

        // Refresh sessions
        const sessRes = await fetch("/api/sessions");
        if (sessRes.ok) {
          const sessData = await sessRes.json();
          if (sessData && sessData.sessions) {
            activeSessions = sessData.sessions;
          }
        }
        if (data.created_session_ids && data.created_session_ids.length > 0 && !currentSession) {
          const firstSess = await fetch(`/api/session/${data.created_session_ids[0]}`);
          if (firstSess.ok) {
            currentSession = await firstSess.json();
            sessionStorage.setItem("active_session_id", currentSession.session_id);
          }
        }

        renderDashboard();
        renderDocumentQueue();

        setTimeout(() => {
          closeFolderImportModal();
        }, 1200);
      } else if (data.status === "cancelled" || data.status === "error") {
        clearInterval(folderImportPoller);
        folderImportPoller = null;
        showToast(data.error_message || "Folder import stopped.", data.status === "error" ? "error" : "info");
        if (runBtn) {
          runBtn.disabled = false;
          runBtn.innerHTML = '<i class="ri-folder-download-line"></i> Start Import';
        }
      }
    } catch (err) {
      console.error("Error polling folder import:", err);
    }
  }, 600);
}

// Queue search and filter helpers
function filterDocumentQueue(query) {
  queueSearchQuery = (query || "").trim();
  queueRenderLimit = 50; // Reset render window on filter change
  const clearBtn = document.getElementById("doc-queue-filter-clear") || document.getElementById("doc-queue-clear-btn");
  if (clearBtn) {
    if (queueSearchQuery) clearBtn.classList.remove("hidden");
    else clearBtn.classList.add("hidden");
  }
  renderDocumentQueue();
}

function clearQueueFilter() {
  const input = document.getElementById("doc-queue-search") || document.getElementById("doc-queue-filter-input");
  if (input) {
    input.value = "";
    input.focus();
  }
  filterDocumentQueue("");
}


function renderDocumentQueue() {
  const queueList = document.getElementById("doc-queue-list");
  const queueBadge = document.getElementById("doc-queue-badge");
  const batchColorizeBtn = document.getElementById("btn-start-batch-colorize");
  const batchCountText = document.getElementById("batch-count-text");
  const sidebarBatchExport = document.getElementById("sidebar-batch-export");
  const bannerBatchBtn = document.getElementById("btn-export-batch-banner");
  const bannerBatchCount = document.getElementById("banner-batch-count");
  const queueFilterWrap = document.getElementById("doc-queue-filter-wrap");

  if (!queueList) return;

  const count = activeSessions.length;
  const hasMultiple = count > 1;

  if (queueFilterWrap) {
    if (count > 5) {
      queueFilterWrap.classList.remove("hidden");
    } else {
      queueFilterWrap.classList.add("hidden");
    }
  }

  // Filter sessions according to search query
  let filteredSessions = activeSessions;
  if (queueSearchQuery) {
    const q = queueSearchQuery.toLowerCase();
    filteredSessions = activeSessions.filter(s => (s.filename || "").toLowerCase().includes(q));
  }

  if (queueBadge) {
    queueBadge.title = `${count} document${count === 1 ? "" : "s"} in queue`;
    if (queueSearchQuery) {
      queueBadge.innerText = `${filteredSessions.length}/${count} docs`;
    } else {
      queueBadge.innerText = `${count} ${count === 1 ? "doc" : "docs"}`;
    }
  }

  if (hasMultiple) {
    queueList.classList.remove("hidden");
    if (batchColorizeBtn) {
      batchColorizeBtn.classList.remove("hidden");
      const pendingCount = activeSessions.filter(s => s.status !== "completed").length;
      if (pendingCount > 0 && pendingCount < count) {
        batchColorizeBtn.innerHTML = `<i class="ri-play-list-2-line"></i> Continue Pending (<span id="batch-count-text">${pendingCount}</span>)`;
        batchColorizeBtn.title = `Continue colorizing ${pendingCount} pending document${pendingCount === 1 ? "" : "s"}`;
      } else {
        batchColorizeBtn.innerHTML = `<i class="ri-magic-line"></i> Colorize All (<span id="batch-count-text">${count}</span>)`;
        batchColorizeBtn.title = `Colorize all ${count} documents`;
      }
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

  // Windowed rendering: render up to queueRenderLimit items to prevent DOM lag on 1000+ files
  const itemsToRender = filteredSessions.slice(0, queueRenderLimit);

  itemsToRender.forEach((sess) => {
    const item = document.createElement("div");
    const isActive = currentSession && currentSession.session_id === sess.session_id;
    const isQueueSelected = selectedQueueSessions.has(sess.session_id);
    item.className = `doc-queue-item ${isActive ? "active" : ""} ${isQueueSelected ? "is-selected" : ""}`;
    item.onclick = () => switchActiveDocument(sess.session_id);

    const fn = (sess.filename || "").toLowerCase();
    let iconHTML = '<i class="ri-image-fill" style="color: #06b6d4;"></i>';
    if (fn.endsWith(".epub")) {
      iconHTML = '<i class="ri-book-2-fill" style="color: #8b5cf6;"></i>';
    } else if (fn.endsWith(".pdf")) {
      iconHTML = '<i class="ri-file-pdf-fill" style="color: #ef4444;"></i>';
    } else if (fn.endsWith(".zip") || fn.endsWith(".cbz")) {
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
      <input type="checkbox" class="doc-queue-item-cb" data-session-id="${sess.session_id}" ${isQueueSelected ? "checked" : ""} onclick="event.stopPropagation()" onchange="toggleQueueSelection('${sess.session_id}', this.checked)" title="Select document" />
      <div class="doc-queue-icon">${iconHTML}</div>
      <div class="doc-queue-info">
        <div class="doc-queue-name" title="${sess.filename}">${sess.filename}</div>
        <div class="doc-queue-meta" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">
          <span>${sess.total_pages} pages</span>
          ${sess.preset_title ? `<span class="queue-preset-pill" title="Manga Preset: ${sess.preset_title}"><i class="ri-palette-line"></i> ${sess.preset_title}</span>` : ""}
        </div>
      </div>
      <div class="doc-queue-top-actions">
        <span class="page-status-badge doc-queue-status-badge ${statusBadgeClass}" id="doc-queue-badge-${sess.session_id}">${statusHTML}</span>
        ${(sess.status === "processing" || sess.is_active) ? `
          <button class="btn-icon doc-pause-btn" title="Pause / Cancel colorization for ${sess.filename}" onclick="cancelDocumentColorization(event, '${sess.session_id}')">
            <i class="ri-pause-line"></i>
          </button>
        ` : (sess.status !== "completed" && sess.total_pages > 0) ? `
          <button class="btn-icon doc-resume-btn" title="Resume / Continue colorizing ${sess.filename}" onclick="resumeDocument(event, '${sess.session_id}')">
            <i class="ri-play-line"></i>
          </button>
        ` : ""}
        <button class="btn-icon doc-delete-btn" title="Delete ${sess.filename}" onclick="deleteDocument(event, '${sess.session_id}')">
          <i class="ri-delete-bin-line"></i>
        </button>
      </div>
    `;
    queueList.appendChild(item);
  });

  // Append a "Show more" button if there are more items than queueRenderLimit
  if (filteredSessions.length > queueRenderLimit) {
    const moreBar = document.createElement("div");
    moreBar.className = "doc-queue-more-bar";
    moreBar.innerHTML = `<i class="ri-arrow-down-s-line"></i> Showing ${itemsToRender.length} of ${filteredSessions.length} — click to show more (+50)`;
    moreBar.onclick = () => {
      queueRenderLimit += 50;
      renderDocumentQueue();
    };
    queueList.appendChild(moreBar);
  }

  updateQueueSelectionUI();
}



function toggleQueueSelection(sessionId, isChecked) {
  if (isChecked) {
    selectedQueueSessions.add(sessionId);
  } else {
    selectedQueueSessions.delete(sessionId);
  }
  updateQueueSelectionUI();
  const queueItem = document.querySelector(`.doc-queue-item-cb[data-session-id="${sessionId}"]`)?.closest(".doc-queue-item");
  if (queueItem) {
    if (isChecked) queueItem.classList.add("is-selected");
    else queueItem.classList.remove("is-selected");
  }
}

function updateQueueSelectionUI() {
  const btn = document.getElementById("btn-delete-selected-queue");
  const countSpan = document.getElementById("queue-selected-count");
  const count = selectedQueueSessions.size;
  if (btn) {
    if (count > 0) {
      btn.classList.remove("hidden");
      if (countSpan) countSpan.innerText = count;
    } else {
      btn.classList.add("hidden");
    }
  }
}

async function deleteSelectedQueueDocuments(event) {
  if (event) event.stopPropagation();
  const count = selectedQueueSessions.size;
  if (count === 0) return;

  const sessionIdsToDelete = Array.from(selectedQueueSessions);
  const confirmed = await showConfirmModal({
    title: "Delete Selected Documents",
    message: `Are you sure you want to delete ${count} selected document(s)? This will permanently delete the files and all pages.`,
    confirmText: "Delete Documents",
    isDanger: true
  });
  if (!confirmed) return;

  showToast(`Deleting ${count} document(s)...`, "info");
  await executeBulkDeletion(sessionIdsToDelete);
}

async function resumeDocument(event, sessionId) {
  if (event) event.stopPropagation();
  try {
    showToast("Resuming colorization...", "info");
    const resp = await fetch(`/api/colorize/resume/${sessionId}`, { method: "POST" });
    const data = await resp.json();
    if (resp.ok) {
      if (!currentSession || currentSession.session_id !== sessionId) {
        await switchActiveDocument(sessionId);
      }
      document.getElementById("progress-card")?.classList.remove("hidden");
      document.getElementById("export-card")?.classList.add("hidden");
      const btnStart = document.getElementById("btn-start-colorize");
      if (btnStart) btnStart.disabled = true;
      subscribeToProgressStream(sessionId, true);
      renderDocumentQueue();
    } else {
      showToast(data.detail || "Could not resume colorization", "error");
    }
  } catch (err) {
    showToast(`Error resuming: ${err.message}`, "error");
  }
}
window.resumeDocument = resumeDocument;

async function cancelDocumentColorization(event, sessionId) {
  if (event) event.stopPropagation();
  try {
    const resp = await fetch(`/api/colorize/cancel/${sessionId}`, { method: "POST" });
    if (resp.ok) {
      showToast("Colorization paused/cancelled", "info");
      if (eventSource && currentSession && currentSession.session_id === sessionId) {
        eventSource.close();
        eventSource = null;
      }
      const s = activeSessions.find(x => x.session_id === sessionId);
      if (s) {
        s.status = "cancelled";
        s.is_active = false;
      }
      if (currentSession && currentSession.session_id === sessionId) {
        currentSession.status = "cancelled";
        document.getElementById("progress-card")?.classList.add("hidden");
        const btnStart = document.getElementById("btn-start-colorize");
        if (btnStart) btnStart.disabled = false;
        updateSelectionUI();
      }
      renderDocumentQueue();
    }
  } catch (err) {
    showToast(`Error cancelling: ${err.message}`, "error");
  }
}
window.cancelDocumentColorization = cancelDocumentColorization;

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
        subscribeToProgressStream(sessionId, true);
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
  if (isSidebarDrawerCollapsed()) {
    const edgeBtn = document.getElementById("btn-sidebar-edge-expand");
    if (edgeBtn) edgeBtn.classList.remove("hidden");
  }

  document.getElementById("doc-filename").innerText = currentSession.filename;
  document.getElementById("doc-total-pages").innerText = currentSession.total_pages;

  // Default to none selected as requested
  selectedPages = new Set();
  exportBannerDismissed = false;

  const iconBox = document.getElementById("file-type-icon");
  const fn = currentSession.filename.toLowerCase();
  if (fn.endsWith(".epub")) {
    iconBox.innerHTML = '<i class="ri-book-2-fill" style="color: #8b5cf6;"></i>';
  } else if (fn.endsWith(".pdf")) {
    iconBox.innerHTML = '<i class="ri-file-pdf-fill" style="color: #ef4444;"></i>';
  } else if (fn.endsWith(".zip") || fn.endsWith(".cbz")) {
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
    if (exportCard && !exportBannerDismissed) exportCard.classList.remove("hidden");
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

function closeExportBanner() {
  exportBannerDismissed = true;
  const exportCard = document.getElementById("export-card");
  if (exportCard) {
    exportCard.classList.add("hidden");
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
        <span class="page-status-badge ${page.skipped_colored ? 'status-skipped-colored' : ('status-' + page.status)}" id="page-badge-${idx}" ${page.skipped_colored ? 'title="Already contained color — original artwork preserved"' : ''}>
          ${page.skipped_colored ? '<i class="ri-palette-line"></i> ORIGINAL COLOR' : page.status.toUpperCase()}
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
      selectedTextElem.innerText = `Select All`;
    } else {
      selectedTextElem.innerText = `${count} of ${total} Selected`;
    }
  }

  // Update Recolorize Selected button state dynamically
  const btnRecolorizeSelected = document.getElementById("btn-recolorize-selected");
  if (btnRecolorizeSelected) {
    if (count === 0) {
      btnRecolorizeSelected.disabled = true;
      btnRecolorizeSelected.title = "Select one or more pages to recolorize";
      btnRecolorizeSelected.style.opacity = "0.55";
      btnRecolorizeSelected.style.cursor = "not-allowed";
    } else {
      btnRecolorizeSelected.disabled = false;
      btnRecolorizeSelected.title = `Recolorize ${count} selected page(s)`;
      btnRecolorizeSelected.style.opacity = "1";
      btnRecolorizeSelected.style.cursor = "pointer";
    }
  }

  const btnStart = document.getElementById("btn-start-colorize");
  if (btnStart) {
    const totalPages = currentSession ? (currentSession.total_pages || (currentSession.pages ? currentSession.pages.length : 0)) : 0;
    const processedPages = currentSession ? (currentSession.processed_count || 0) : 0;
    const remainingPages = Math.max(0, totalPages - processedPages);

    if (isBatchColorizing) {
      btnStart.disabled = true;
    } else if (count === 0) {
      btnStart.innerHTML = '<i class="ri-checkbox-blank-line"></i> Select Pages to Colorize';
      btnStart.disabled = true;
    } else if (processedPages > 0 && count === total && remainingPages > 0) {
      btnStart.innerHTML = `<i class="ri-play-circle-line"></i> Continue Colorizing (${remainingPages} Remaining Pages)`;
      btnStart.disabled = false;
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
    skip_if_colored: document.getElementById("chk-skip-colored")?.checked || false,
    denoise_screentone: document.getElementById("chk-denoise-screentone") ? document.getElementById("chk-denoise-screentone").checked : true
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

function subscribeToProgressStream(sessionId = null, autoResume = false) {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }

  const targetId = sessionId || (currentSession ? currentSession.session_id : null);
  if (!targetId) return;

  const streamUrl = `/api/colorize/stream/${targetId}${autoResume ? "?auto_resume=true" : ""}`;
  eventSource = new EventSource(streamUrl);

  eventSource.onmessage = (e) => {
    const data = JSON.parse(e.data);

    if (data.type === "init") {
      // If the session was already completed or skipped before connecting, finish immediately
      if (data.session && (data.session.status === "completed" || (data.session.total_pages > 0 && data.session.processed_count >= data.session.total_pages))) {
        if (eventSource) {
          eventSource.close();
          eventSource = null;
        }
        document.getElementById("progress-card")?.classList.add("hidden");
        document.getElementById("export-card")?.classList.remove("hidden");
        const btnStart = document.getElementById("btn-start-colorize");
        if (btnStart) btnStart.disabled = false;
        if (currentSession && currentSession.session_id === targetId) {
          currentSession.status = "completed";
          currentSession.processed_count = currentSession.total_pages;
        }
        renderDocumentQueue();
        updateColorizedCount();
        return;
      }
      // If session is idle or pending and not actively running
      if (!data.is_active && data.session && data.session.status !== "processing") {
        document.getElementById("progress-card")?.classList.add("hidden");
        const btnStart = document.getElementById("btn-start-colorize");
        if (btnStart) btnStart.disabled = false;
        updateSelectionUI();
        renderDocumentQueue();
      }
    }

    if (data.type === "idle") {
      if (eventSource) {
        eventSource.close();
        eventSource = null;
      }
      document.getElementById("progress-card")?.classList.add("hidden");
      const btnStart = document.getElementById("btn-start-colorize");
      if (btnStart) btnStart.disabled = false;
      updateSelectionUI();
      renderDocumentQueue();
      return;
    }

    if (data.type === "page_update") {
      const idx = data.page_index;
      if (currentSession && currentSession.session_id === targetId && currentSession.pages && currentSession.pages[idx]) {
        const pageInfo = currentSession.pages[idx];
        pageInfo.status = data.status;
        if (data.skipped_colored) {
          pageInfo.skipped_colored = true;
        }

        if (data.colorized_url) {
          pageInfo.colorized_url = data.colorized_url;
          const imgElem = document.getElementById(`page-img-${idx}`);
          if (imgElem) imgElem.src = `${data.colorized_url}?t=${Date.now()}`;
        }

        const badge = document.getElementById(`page-badge-${idx}`);
        if (badge) {
          if (data.skipped_colored || pageInfo.skipped_colored) {
            badge.className = "page-status-badge status-skipped-colored";
            badge.innerHTML = '<i class="ri-palette-line"></i> ORIGINAL COLOR';
            badge.title = "Page already contained color — original artwork preserved";
          } else {
            badge.className = `page-status-badge status-${data.status}`;
            badge.innerText = data.status.toUpperCase();
          }
        }

        if (data.message) {
          const progSub = document.getElementById("progress-subtext");
          if (progSub) progSub.innerText = data.message;
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

        if (data.exemplar_used) {
          pageInfo.exemplar_used = data.exemplar_used;
        }
        if (data.exemplars_used) {
          pageInfo.exemplars_used = data.exemplars_used;
        }
        if (data.quality_score) {
          pageInfo.quality_score = data.quality_score;
        }
        if (data.auto_harvested) {
          pageInfo.auto_harvested = true;
        }
        if (currentPreviewPageIndex === idx) {
          if (typeof updateExemplarPreviewChip === "function") {
            updateExemplarPreviewChip(pageInfo);
          }
          if (typeof updateQualityPreviewChip === "function") {
            updateQualityPreviewChip(pageInfo);
          }
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
    } else if (data.type === "adapter_training_progress") {
      if (typeof updateAdapterTrainingProgressUI === "function") {
        updateAdapterTrainingProgressUI(data);
      }
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
    line_preserve: linePreserve,
    denoise_screentone: document.getElementById("chk-denoise-screentone") ? document.getElementById("chk-denoise-screentone").checked : true,
    active_character_names: activePageCharacterNames && activePageCharacterNames.size > 0 ? Array.from(activePageCharacterNames) : null,
    recognition_mode: document.getElementById("recognition-mode-select") ? document.getElementById("recognition-mode-select").value : "auto"
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
      if (data.recognized_characters) {
        page.recognized_characters = data.recognized_characters;
        if (currentPreviewPageIndex === pageIdx && typeof renderPageCharacterChips === "function") {
          renderPageCharacterChips(data.recognized_characters);
        }
      }
      if (data.exemplar_used) {
        page.exemplar_used = data.exemplar_used;
      }
      if (data.exemplars_used) {
        page.exemplars_used = data.exemplars_used;
      }
      const ts = Date.now();
      
      // Update gallery thumbnail
      const imgElem = document.getElementById(`page-img-${pageIdx}`);
      if (imgElem) imgElem.src = `${data.colorized_url}?t=${ts}`;

      const badge = document.getElementById(`page-badge-${pageIdx}`);
      if (badge) {
        badge.className = "page-status-badge status-colorized";
        badge.innerText = "COLORIZED";
      }

      updateColorizedCount();
      updateSelectionUI();

      const styleSelect = document.getElementById("style-select");
      const selectedStyleText = styleSelect.options[styleSelect.selectedIndex]?.text?.split(" ")[1] || style;
      if (titleBadge) {
        titleBadge.innerText = `${page.display_name} • ${selectedStyleText}`;
      }

      // Open split comparator — openSplitPreview owns loading colorImg.src
      // to ensure the onload callback fires after the container is fully set up.
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

  if (!preventScroll) {
    splitCard.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' });
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
  resetComparatorZoom();

  // Set initial view: if page is colorized, show split; if not, show B&W
  if (page.colorized_url) {
    setComparatorView("split", false);
  } else {
    setComparatorView("bw", false);
  }

  // Reset handle with container dimensions applied
  requestAnimationFrame(() => setSplitPosition(currentSplitPct));

  if (typeof updatePageCharacterChips === "function") {
    updatePageCharacterChips(pageIdx);
  }

  const learnBtn = document.getElementById("btn-learn-page-memory");
  if (learnBtn) {
    learnBtn.disabled = !page.colorized_url || page.status !== "colorized";
  }
  if (typeof fetchSeriesMemory === "function") {
    fetchSeriesMemory(currentSession?.session_id);
  }
  if (typeof updateExemplarPreviewChip === "function") {
    updateExemplarPreviewChip(page);
  }
  if (typeof updateQualityPreviewChip === "function") {
    updateQualityPreviewChip(page);
  }
}

// --- Comparator Zoom & Pan Engine ---
let currentZoom = 1.0;
const MIN_ZOOM = 0.15;
const MAX_ZOOM = 5.0;
let panX = 0;
let panY = 0;
let isPanning = false;
let startPanX = 0;
let startPanY = 0;
let initialPanX = 0;
let initialPanY = 0;

const ZOOM_PRESETS = [
  { label: "Fit Window", value: 1.0, isFit: true },
  { label: "20%", value: 0.2 },
  { label: "35%", value: 0.35 },
  { label: "50%", value: 0.5 },
  { label: "70%", value: 0.7 },
  { label: "100%", value: 1.0 },
  { label: "125%", value: 1.25 },
  { label: "150%", value: 1.5 },
  { label: "200%", value: 2.0 },
  { label: "300%", value: 3.0 },
  { label: "400%", value: 4.0 },
];

function changeComparatorZoom(delta) {
  applyZoom(currentZoom + delta);
}
window.changeComparatorZoom = changeComparatorZoom;

function resetComparatorZoom() {
  currentZoom = 1.0;
  panX = 0;
  panY = 0;
  closeAllZoomMenus();
  updateZoomTransform(true);
}
window.resetComparatorZoom = resetComparatorZoom;

function applyZoom(newZoom, clientX = null, clientY = null) {
  const clampedZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Math.round(newZoom * 100) / 100));
  if (clampedZoom === currentZoom) return;

  const container = document.getElementById("split-container");
  if (!container) return;

  if (clientX !== null && clientY !== null) {
    const rect = container.getBoundingClientRect();
    const cursorOffsetX = clientX - (rect.left + rect.width / 2);
    const cursorOffsetY = clientY - (rect.top + rect.height / 2);
    const zoomRatio = clampedZoom / currentZoom;
    panX -= cursorOffsetX * (zoomRatio - 1);
    panY -= cursorOffsetY * (zoomRatio - 1);
  } else if (clampedZoom === 1.0) {
    panX = 0;
    panY = 0;
  }

  currentZoom = clampedZoom;
  clampPan();
  updateZoomTransform(clientX === null);
}
window.applyZoom = applyZoom;

function clampPan() {
  const container = document.getElementById("split-container");
  const wrapper = document.querySelector(".split-slider-wrapper");
  if (!container || !wrapper) return;

  if (currentZoom <= 1.0) {
    panX = 0;
    panY = 0;
    return;
  }

  const containerW = container.offsetWidth * currentZoom;
  const containerH = container.offsetHeight * currentZoom;
  const wrapperW = wrapper.clientWidth;
  const wrapperH = wrapper.clientHeight;

  const maxPanX = Math.max(0, (containerW - wrapperW) / 2 + 100);
  const maxPanY = Math.max(0, (containerH - wrapperH) / 2 + 100);

  panX = Math.max(-maxPanX, Math.min(maxPanX, panX));
  panY = Math.max(-maxPanY, Math.min(maxPanY, panY));
}

function updateZoomTransform(smooth = false) {
  const container = document.getElementById("split-container");
  if (!container) return;

  if (smooth) {
    container.style.transition = "transform 0.22s cubic-bezier(0.16, 1, 0.3, 1)";
    setTimeout(() => {
      if (container) container.style.transition = "";
    }, 240);
  } else {
    container.style.transition = "";
  }

  container.style.transform = `translate(${panX}px, ${panY}px) scale(${currentZoom})`;
  container.style.transformOrigin = "center center";

  if (currentZoom > 1.0) {
    container.classList.add("is-zoomed");
  } else {
    container.classList.remove("is-zoomed");
  }

  const pctStr = `${Math.round(currentZoom * 100)}%`;
  const headerText = document.getElementById("header-zoom-text");
  if (headerText) headerText.innerText = pctStr;
  const btnReset = document.getElementById("btn-zoom-reset");
  if (btnReset && !headerText) btnReset.innerText = pctStr;

  const floatLabel = document.getElementById("float-zoom-label");
  if (floatLabel) floatLabel.innerText = pctStr;
  const floatText = document.getElementById("float-zoom-text");
  if (floatText && !floatLabel) floatText.innerText = pctStr;

  const btnZoomOut = document.getElementById("btn-zoom-out");
  if (btnZoomOut) btnZoomOut.disabled = currentZoom <= MIN_ZOOM;
  const btnZoomIn = document.getElementById("btn-zoom-in");
  if (btnZoomIn) btnZoomIn.disabled = currentZoom >= MAX_ZOOM;
}

// --- Zoom Presets Menu Engine ---
function toggleZoomMenu(type, event) {
  if (event) {
    event.stopPropagation();
  }
  const wrapperId = type === "float" ? "float-zoom-wrapper" : "header-zoom-wrapper";
  const wrapper = document.getElementById(wrapperId);
  if (!wrapper) return;

  const wasOpen = wrapper.classList.contains("open");
  closeAllZoomMenus();

  if (!wasOpen) {
    renderZoomMenuItems(type);
    wrapper.classList.add("open");
    setTimeout(() => {
      const input = document.getElementById(`${type}-zoom-custom-input`);
      if (input) input.select();
    }, 50);
  }
}
window.toggleZoomMenu = toggleZoomMenu;

function closeAllZoomMenus() {
  document.querySelectorAll(".zoom-dropdown-wrapper.open").forEach(w => {
    w.classList.remove("open");
  });
}
window.closeAllZoomMenus = closeAllZoomMenus;

function renderZoomMenuItems(type) {
  const menuId = type === "float" ? "float-zoom-menu" : "header-zoom-menu";
  const menu = document.getElementById(menuId);
  if (!menu) return;

  const currentPct = Math.round(currentZoom * 100);

  let html = `
    <div class="zoom-custom-row" onclick="event.stopPropagation()">
      <input type="number" class="zoom-custom-input" id="${type}-zoom-custom-input" min="15" max="500" placeholder="${currentPct}%" value="${currentPct}" onkeydown="if(event.key==='Enter') applyCustomZoomInput('${type}')" />
      <button class="zoom-custom-apply" type="button" onclick="applyCustomZoomInput('${type}')">Set</button>
    </div>
    <div class="zoom-preset-options">
  `;

  ZOOM_PRESETS.forEach(item => {
    const isSelected = Math.abs(currentZoom - item.value) < 0.03;
    html += `
      <button type="button" class="zoom-menu-item ${isSelected ? 'active' : ''}" onclick="selectZoomPreset(${item.value})">
        <span>${item.label}</span>
        ${item.isFit ? '<span class="zoom-menu-hint">Fit</span>' : ''}
        <i class="ri-check-line"></i>
      </button>
    `;
  });

  html += `</div>`;
  menu.innerHTML = html;
}

function selectZoomPreset(val) {
  closeAllZoomMenus();
  if (val === 1.0) {
    resetComparatorZoom();
  } else {
    applyZoom(val);
  }
}
window.selectZoomPreset = selectZoomPreset;

function applyCustomZoomInput(type) {
  const input = document.getElementById(`${type}-zoom-custom-input`);
  if (!input) return;
  const num = parseFloat(input.value);
  if (!isNaN(num) && num >= 15 && num <= 500) {
    closeAllZoomMenus();
    if (num === 100) {
      resetComparatorZoom();
    } else {
      applyZoom(num / 100);
    }
  }
}
window.applyCustomZoomInput = applyCustomZoomInput;

// Dismiss zoom menus when clicking outside
document.addEventListener("click", (e) => {
  if (!e.target.closest(".zoom-dropdown-wrapper")) {
    closeAllZoomMenus();
  }
});

// --- Fullscreen Engine ---
function toggleComparatorFullscreen() {
  const card = document.getElementById("split-preview-card");
  if (!card) return;

  const isFs = Boolean(document.fullscreenElement || document.webkitFullscreenElement || card.classList.contains("is-fullscreen"));

  if (!isFs) {
    if (card.requestFullscreen) {
      card.requestFullscreen().catch(() => {
        card.classList.add("is-fullscreen");
        document.body.classList.add("comparator-fullscreen-active");
        updateFullscreenUI(true);
      });
    } else if (card.webkitRequestFullscreen) {
      card.webkitRequestFullscreen();
    } else {
      card.classList.add("is-fullscreen");
      document.body.classList.add("comparator-fullscreen-active");
      updateFullscreenUI(true);
    }
  } else {
    if (document.fullscreenElement || document.webkitFullscreenElement) {
      if (document.exitFullscreen) document.exitFullscreen();
      else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
    }
    card.classList.remove("is-fullscreen");
    document.body.classList.remove("comparator-fullscreen-active");
    updateFullscreenUI(false);
  }
}
window.toggleComparatorFullscreen = toggleComparatorFullscreen;

function updateFullscreenUI(isFullscreen) {
  const icon = document.getElementById("fullscreen-icon");
  const floatIcon = document.getElementById("float-fullscreen-icon");
  const btn = document.getElementById("btn-toggle-fullscreen");

  const iconClass = isFullscreen ? "ri-fullscreen-exit-line" : "ri-fullscreen-line";
  const titleText = isFullscreen ? "Exit Full Screen (F)" : "Full Screen (F)";

  if (icon) icon.className = iconClass;
  if (floatIcon) floatIcon.className = iconClass;
  if (btn) {
    btn.title = titleText;
    btn.classList.toggle("active", isFullscreen);
  }
}

document.addEventListener("fullscreenchange", () => {
  const card = document.getElementById("split-preview-card");
  const isFs = Boolean(document.fullscreenElement);
  if (card) card.classList.toggle("is-fullscreen", isFs);
  document.body.classList.toggle("comparator-fullscreen-active", isFs);
  updateFullscreenUI(isFs);
  setTimeout(() => {
    setSplitPosition(currentSplitPct);
    clampPan();
    updateZoomTransform();
  }, 100);
});

document.addEventListener("webkitfullscreenchange", () => {
  const card = document.getElementById("split-preview-card");
  const isFs = Boolean(document.webkitFullscreenElement);
  if (card) card.classList.toggle("is-fullscreen", isFs);
  document.body.classList.toggle("comparator-fullscreen-active", isFs);
  updateFullscreenUI(isFs);
  setTimeout(() => {
    setSplitPosition(currentSplitPct);
    clampPan();
    updateZoomTransform();
  }, 100);
});

function closeSplitPreview() {
  if (document.fullscreenElement || document.webkitFullscreenElement) {
    if (document.exitFullscreen) document.exitFullscreen();
    else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
  }
  const card = document.getElementById("split-preview-card");
  if (card) card.classList.remove("is-fullscreen");
  document.body.classList.remove("comparator-fullscreen-active");
  updateFullscreenUI(false);
  closeAllZoomMenus();
  resetComparatorZoom();
  document.getElementById("split-preview-card").classList.add("hidden");
}

let currentSplitPct = 50;
let isSplitSliderInitialized = false;

function setupSplitSlider() {
  const container = document.getElementById("split-container");
  const handle = document.getElementById("split-handle");
  const wrapper = document.querySelector(".split-slider-wrapper");
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

  // Modern Pointer Events API (supports Mouse, Touch, and Stylus)
  container.addEventListener("pointerdown", (e) => {
    if (e.button !== undefined && e.button !== 0) return;
    if (e.target.closest(".split-label")) return;

    const isHandle = e.target.closest("#split-handle") || e.target.closest(".split-handle-button");

    if (currentZoom > 1.0 && !isHandle) {
      // Pan mode when zoomed
      isPanning = true;
      startPanX = e.clientX;
      startPanY = e.clientY;
      initialPanX = panX;
      initialPanY = panY;
      container.classList.add("is-grabbing");
      try { container.setPointerCapture(e.pointerId); } catch (err) {}
      e.preventDefault();
      return;
    }

    // Split handle dragging
    isDragging = true;
    if (handle) handle.classList.add("active");
    try {
      container.setPointerCapture(e.pointerId);
    } catch (err) {}
    updateFromPointer(e.clientX);
    e.preventDefault();
  });

  container.addEventListener("pointermove", (e) => {
    if (isPanning) {
      panX = initialPanX + (e.clientX - startPanX);
      panY = initialPanY + (e.clientY - startPanY);
      clampPan();
      updateZoomTransform(false);
      e.preventDefault();
      return;
    }
    if (!isDragging) return;
    updateFromPointer(e.clientX);
    e.preventDefault();
  });

  const stopDrag = (e) => {
    if (isPanning) {
      isPanning = false;
      container.classList.remove("is-grabbing");
      try { container.releasePointerCapture(e.pointerId); } catch (err) {}
    }
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

  // Double-click to toggle Zoom (100% <-> 200%)
  container.addEventListener("dblclick", (e) => {
    if (e.target.closest(".split-label") || e.target.closest("#split-handle")) return;
    if (currentZoom > 1.0) {
      resetComparatorZoom();
    } else {
      applyZoom(2.0, e.clientX, e.clientY);
    }
  });

  // Prevent browser native image dragging and selection
  container.addEventListener("dragstart", (e) => e.preventDefault());
  container.addEventListener("selectstart", (e) => e.preventDefault());

  // Mouse Wheel & Trackpad Pinch Zoom Support
  const handleWheel = (e) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const zoomDelta = e.deltaY < 0 ? 0.15 : -0.15;
      applyZoom(currentZoom + zoomDelta, e.clientX, e.clientY);
      return;
    }

    if (currentZoom > 1.0) {
      e.preventDefault();
      panX -= e.deltaX;
      panY -= e.deltaY;
      clampPan();
      updateZoomTransform(false);
      return;
    }

    // Normal horizontal wheel swipe for split divider when not zoomed
    const isHorizontal = Math.abs(e.deltaX) > Math.abs(e.deltaY);
    const delta = isHorizontal ? e.deltaX : (e.shiftKey ? e.deltaY : 0);
    if (delta !== 0) {
      e.preventDefault();
      const step = (delta / (container.clientWidth || 600)) * 100 * 1.2;
      setSplitPosition(Math.max(0, Math.min(100, currentSplitPct + step)));
    }
  };

  container.addEventListener("wheel", handleWheel, { passive: false });
  if (wrapper) {
    wrapper.addEventListener("wheel", handleWheel, { passive: false });
  }

  // Window resize & ResizeObserver for dynamic image alignment
  window.addEventListener("resize", () => {
    setSplitPosition(currentSplitPct);
    clampPan();
    updateZoomTransform(false);
  });

  if (window.ResizeObserver) {
    const ro = new ResizeObserver(() => {
      setSplitPosition(currentSplitPct);
      clampPan();
      updateZoomTransform(false);
    });
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

  const pendingSessions = activeSessions.filter(s => s.status !== "completed");
  const targetSessions = pendingSessions.length > 0 ? pendingSessions : activeSessions;
  const sessionIds = targetSessions.map(s => s.session_id);
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
        line_preserve: linePreserve,
        skip_if_colored: document.getElementById("chk-skip-colored")?.checked || false,
        denoise_screentone: document.getElementById("chk-denoise-screentone") ? document.getElementById("chk-denoise-screentone").checked : true
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
          subscribeToProgressStream(targetSess.session_id, true);
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
    sessionList = historyData.filter(s => (s.total_pages > 0 || (s.pages && s.pages.length > 0)));
  }

  const sessionIds = sessionList.map(s => s.session_id).filter(Boolean);
  const isOriginal = Boolean(document.getElementById("combined-original-check")?.checked);
  let title = document.getElementById("combined-title-input")?.value?.trim();
  if (!title) {
    title = isOriginal ? "Manga Collection" : "Colorized Manga Collection";
  }

  const chunkVal = document.getElementById("combined-chunk-select")?.value || "size_250";
  let chunkBy = "none";
  let chunkSize = 3;
  if (chunkVal === "none") {
    chunkBy = "none";
    chunkSize = 0;
  } else if (chunkVal.startsWith("volumes_")) {
    chunkBy = "volumes";
    chunkSize = parseInt(chunkVal.replace("volumes_", ""), 10) || 3;
  } else if (chunkVal === "size_custom") {
    chunkBy = "size_mb";
    const customMb = parseInt(document.getElementById("combined-custom-size-input")?.value, 10);
    chunkSize = (!isNaN(customMb) && customMb >= 20) ? customMb : 200;
  } else if (chunkVal.startsWith("size_")) {
    chunkBy = "size_mb";
    chunkSize = parseInt(chunkVal.replace("size_", ""), 10) || 250;
  }

  const presetVal = document.getElementById("combined-preset-select")?.value || "colorsoft";
  let maxDim = 1600;
  let jpegQual = 80;
  let colorsoftTune = false;
  if (presetVal === "colorsoft") {
    maxDim = 1600;
    jpegQual = 80;
    colorsoftTune = !isOriginal;
  } else if (presetVal === "kindle") {
    maxDim = 1600;
    jpegQual = 80;
  } else if (presetVal === "tablet") {
    maxDim = 1920;
    jpegQual = 85;
  } else if (presetVal === "original") {
    maxDim = 0;
    jpegQual = 90;
  }

  const isGrayscale = Boolean(document.getElementById("combined-grayscale-check")?.checked);

  const fmtLabel = format === "pdf" ? "Single PDF" : (format === "mobi" ? "Kindle MOBI" : "Single EPUB");
  const origTag = isOriginal ? " (Original)" : "";

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
  if (progressTitle) progressTitle.innerText = `Exporting ${fmtLabel}${origTag}...`;
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
  if (progStatus) progStatus.innerText = `Assembling ${fmtLabel}${origTag}...`;
  if (progSub) progSub.innerText = `Preparing ${sessionIds.length || 'all'} volumes: "${title}"`;
  if (progCounter) progCounter.innerText = "0%";
  if (progFill) progFill.style.width = "0%";

  showToast(`Preparing ${fmtLabel}${origTag} (${sessionIds.length || 'all'} volumes)...`, "info");

  try {
    const resp = await fetch("/api/export/combined", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_ids: sessionIds,
        format,
        title,
        chunk_by: chunkBy,
        chunk_size: chunkSize,
        max_dimension: maxDim,
        jpeg_quality: jpegQual,
        grayscale: isGrayscale,
        colorsoft_tune: colorsoftTune,
        export_original: isOriginal
      })
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

  const confirmed = await showConfirmModal({
    title: "Delete Document",
    message: `Are you sure you want to delete "${docName}"? This will permanently delete the file and all its pages.`,
    confirmText: "Delete",
    isDanger: true
  });
  if (!confirmed) return;

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

async function executeBulkDeletion(sessionIds) {
  if (!sessionIds || sessionIds.length === 0) return;

  try {
    const resp = await fetch("/api/sessions/bulk-delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_ids: sessionIds })
    });
    const data = await resp.json();

    if (resp.ok) {
      const deletedSet = new Set(data.deleted_session_ids || sessionIds);

      activeSessions = activeSessions.filter(s => !deletedSet.has(s.session_id));
      historyData = historyData.filter(s => !deletedSet.has(s.session_id));

      sessionIds.forEach(id => {
        selectedHistorySessions.delete(id);
        selectedQueueSessions.delete(id);
      });

      updateQueueSelectionUI();
      updateHistorySelectionUI();
      updateHistoryBadges();
      updateHistoryStatsBar();

      if (currentSession && deletedSet.has(currentSession.session_id)) {
        if (activeSessions.length > 0) {
          await switchActiveDocument(activeSessions[0].session_id);
          showToast(`Deleted ${deletedSet.size} document(s). Switched to "${activeSessions[0].filename}".`, "success");
        } else {
          resetUpload();
          showToast(`Deleted ${deletedSet.size} document(s). All documents removed.`, "success");
        }
      } else {
        renderDocumentQueue();
        showToast(`Deleted ${deletedSet.size} document(s) successfully.`, "success");
      }

      renderHistoryList();
    } else {
      showToast(`Failed to delete documents: ${data.detail || "Error"}`, "error");
    }
  } catch (err) {
    showToast(`Error deleting documents: ${err.message}`, "error");
  }
}

async function deletePage(event, pageIdx) {
  if (event) event.stopPropagation();
  if (!currentSession || !currentSession.pages || !currentSession.pages[pageIdx]) return;

  const page = currentSession.pages[pageIdx];
  const pageName = page.display_name || `Page ${pageIdx + 1}`;

  const confirmed = await showConfirmModal({
    title: "Delete Page",
    message: `Delete ${pageName}? This will remove it from the document.`,
    confirmText: "Delete Page",
    isDanger: true
  });
  if (!confirmed) return;

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
  const confirmed = await showConfirmModal({
    title: "Delete All Documents",
    message: `Are you sure you want to delete all ${count} document(s) and files? This cannot be undone.`,
    confirmText: "Delete All",
    isDanger: true
  });
  if (!confirmed) return;

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
  selectedQueueSessions.clear();
  updateQueueSelectionUI();
  document.getElementById("dashboard-section").classList.add("hidden");
  const edgeBtn = document.getElementById("btn-sidebar-edge-expand");
  if (edgeBtn) edgeBtn.classList.add("hidden");
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

    // Prune selections for any sessions that no longer exist
    const existingIds = new Set(historyData.map(s => s.session_id));
    selectedHistorySessions.forEach(id => {
      if (!existingIds.has(id)) selectedHistorySessions.delete(id);
    });

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

function getFilteredHistoryItems() {
  return historyData.filter(item => {
    if (currentHistoryFilter === "completed" && item.status !== "completed") return false;
    if (currentHistoryFilter === "processing" && item.status !== "processing") return false;
    if (currentHistoryFilter === "idle" && (item.status === "completed" || item.status === "processing")) return false;

    if (currentHistorySearch) {
      const name = (item.filename || "").toLowerCase();
      if (!name.includes(currentHistorySearch)) return false;
    }

    return true;
  });
}

function updateHistorySelectionUI() {
  const visible = getFilteredHistoryItems();
  const count = selectedHistorySessions.size;

  const selectAllCb = document.getElementById("hist-select-all-cb");
  const selectAllText = document.getElementById("hist-select-all-text");
  const badge = document.getElementById("hist-selected-badge");
  const countSpan = document.getElementById("hist-selected-count");
  const topDeleteBtn = document.getElementById("btn-hist-bulk-delete");
  const btnCountSpan = document.getElementById("hist-btn-count");
  const footerDeleteBtn = document.getElementById("btn-footer-bulk-delete");
  const footerCountSpan = document.getElementById("footer-bulk-delete-count");

  if (selectAllText) {
    selectAllText.innerText = visible.length > 0 ? `Select All (${visible.length})` : "Select All";
  }

  if (selectAllCb) {
    if (visible.length > 0 && visible.every(item => selectedHistorySessions.has(item.session_id))) {
      selectAllCb.checked = true;
      selectAllCb.indeterminate = false;
    } else if (visible.some(item => selectedHistorySessions.has(item.session_id))) {
      selectAllCb.checked = false;
      selectAllCb.indeterminate = true;
    } else {
      selectAllCb.checked = false;
      selectAllCb.indeterminate = false;
    }
  }

  if (badge && countSpan) {
    if (count > 0) {
      badge.classList.remove("hidden");
      countSpan.innerText = count;
    } else {
      badge.classList.add("hidden");
    }
  }

  if (topDeleteBtn && btnCountSpan) {
    topDeleteBtn.disabled = count === 0;
    btnCountSpan.innerText = count;
  }

  if (footerDeleteBtn && footerCountSpan) {
    if (count > 0) {
      footerDeleteBtn.classList.remove("hidden");
      footerCountSpan.innerText = count;
    } else {
      footerDeleteBtn.classList.add("hidden");
    }
  }
}

function toggleHistorySessionSelection(sessionId, isChecked) {
  if (isChecked) {
    selectedHistorySessions.add(sessionId);
  } else {
    selectedHistorySessions.delete(sessionId);
  }
  updateHistorySelectionUI();
  const row = document.getElementById(`history-item-${sessionId}`);
  if (row) {
    if (isChecked) row.classList.add("is-selected");
    else row.classList.remove("is-selected");
  }
}

function toggleSelectAllHistory(isChecked) {
  const visible = getFilteredHistoryItems();
  visible.forEach(item => {
    if (isChecked) {
      selectedHistorySessions.add(item.session_id);
    } else {
      selectedHistorySessions.delete(item.session_id);
    }
  });
  updateHistorySelectionUI();
  renderHistoryList();
}

function selectHistoryByStatus(status) {
  const matching = historyData.filter(s => s.status === status);
  if (matching.length === 0) {
    showToast(`No documents found with status "${status}".`, "info");
    return;
  }
  matching.forEach(item => selectedHistorySessions.add(item.session_id));
  updateHistorySelectionUI();
  renderHistoryList();
  showToast(`Selected ${matching.length} ${status} document(s).`, "info");
}

function clearHistorySelection() {
  selectedHistorySessions.clear();
  updateHistorySelectionUI();
  renderHistoryList();
}

async function bulkDeleteHistory() {
  const count = selectedHistorySessions.size;
  if (count === 0) return;

  const sessionIdsToDelete = Array.from(selectedHistorySessions);
  const confirmed = await showConfirmModal({
    title: "Delete History Sessions",
    message: `Are you sure you want to permanently delete ${count} selected document session(s)? All extracted pages and colorized files will be deleted.`,
    confirmText: "Delete Sessions",
    isDanger: true
  });
  if (!confirmed) return;

  showToast(`Deleting ${count} document session(s)...`, "info");
  await executeBulkDeletion(sessionIdsToDelete);
}

function changeHistoryPage(delta) {
  currentHistoryPage += delta;
  renderHistoryList();
}

function renderHistoryList() {
  const container = document.getElementById("history-list-container");
  const summaryEl = document.getElementById("history-footer-summary");
  const paginationWrap = document.getElementById("history-pagination-wrap");
  const pageIndicator = document.getElementById("history-page-indicator");
  const prevBtn = document.getElementById("btn-hist-prev");
  const nextBtn = document.getElementById("btn-hist-next");

  if (!container) return;

  const filtered = getFilteredHistoryItems();

  if (filtered.length === 0) {
    if (paginationWrap) paginationWrap.classList.add("hidden");
    if (summaryEl) {
      summaryEl.innerText = `Showing 0 of ${historyData.length} documents`;
    }

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
    updateHistorySelectionUI();
    return;
  }

  // Calculate pagination
  const totalPages = Math.ceil(filtered.length / historyPageSize) || 1;
  if (currentHistoryPage > totalPages) currentHistoryPage = totalPages;
  if (currentHistoryPage < 1) currentHistoryPage = 1;

  if (paginationWrap) {
    if (filtered.length > historyPageSize) {
      paginationWrap.classList.remove("hidden");
      if (pageIndicator) pageIndicator.innerText = `Page ${currentHistoryPage} of ${totalPages}`;
      if (prevBtn) prevBtn.disabled = currentHistoryPage <= 1;
      if (nextBtn) nextBtn.disabled = currentHistoryPage >= totalPages;
    } else {
      paginationWrap.classList.add("hidden");
    }
  }

  const startIdx = (currentHistoryPage - 1) * historyPageSize;
  const pageItems = filtered.slice(startIdx, startIdx + historyPageSize);

  if (summaryEl) {
    summaryEl.innerText = `Showing ${pageItems.length} of ${filtered.length} documents${filtered.length !== historyData.length ? ` (filtered from ${historyData.length})` : ""}`;
  }

  container.innerHTML = "";

  pageItems.forEach(item => {
    const isCurrent = currentSession && currentSession.session_id === item.session_id;
    const isSelected = selectedHistorySessions.has(item.session_id);
    const totalPages = item.total_pages || 0;
    const processedPages = item.processed_count || 0;
    const pct = totalPages > 0 ? Math.min(100, Math.round((processedPages / totalPages) * 100)) : 0;

    const fn = (item.filename || "").toLowerCase();
    let iconHTML = '<i class="ri-image-fill" style="color: #06b6d4;"></i>';
    if (fn.endsWith(".epub")) {
      iconHTML = '<i class="ri-book-2-fill" style="color: #8b5cf6;"></i>';
    } else if (fn.endsWith(".pdf")) {
      iconHTML = '<i class="ri-file-pdf-fill" style="color: #ef4444;"></i>';
    } else if (fn.endsWith(".zip") || fn.endsWith(".cbz")) {
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
    row.className = `history-item ${isCurrent ? "is-current" : ""} ${isSelected ? "is-selected" : ""}`;
    row.id = `history-item-${item.session_id}`;

    row.innerHTML = `
      <div class="history-item-checkbox-cell" onclick="event.stopPropagation();">
        <input type="checkbox" class="history-item-cb" data-session-id="${item.session_id}" ${isSelected ? "checked" : ""} onchange="toggleHistorySessionSelection('${item.session_id}', this.checked)" title="Select document" />
      </div>
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

  updateHistorySelectionUI();
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
window.toggleHistorySessionSelection = toggleHistorySessionSelection;
window.toggleSelectAllHistory = toggleSelectAllHistory;
window.selectHistoryByStatus = selectHistoryByStatus;
window.clearHistorySelection = clearHistorySelection;
window.bulkDeleteHistory = bulkDeleteHistory;
window.toggleQueueSelection = toggleQueueSelection;
window.deleteSelectedQueueDocuments = deleteSelectedQueueDocuments;
window.executeBulkDeletion = executeBulkDeletion;
window.changeHistoryPage = changeHistoryPage;
window.handleBulkChunkedUpload = handleBulkChunkedUpload;
window.openImportProgressModal = openImportProgressModal;
window.closeImportProgressModal = closeImportProgressModal;
window.cancelBatchImport = cancelBatchImport;
window.openFolderImportModal = openFolderImportModal;
window.closeFolderImportModal = closeFolderImportModal;
window.handleFolderImportOverlayClick = handleFolderImportOverlayClick;
window.startFolderImport = startFolderImport;
window.filterDocumentQueue = filterDocumentQueue;
window.clearQueueFilter = clearQueueFilter;




// ─────────────────────────────────────────────────────────────────────
//  Character Palette & Manga Presets Manager
// ─────────────────────────────────────────────────────────────────────

/** In-memory palette state for the active session. */
let paletteCharacters = [];
let allMangaPresets = [];
let currentPresetId = "";

/**
 * Loads registered manga presets from the backend to populate the dropdown.
 */
async function loadMangaPresets() {
  try {
    const resp = await fetch("/api/palette/presets");
    if (!resp.ok) return;
    const data = await resp.json();
    allMangaPresets = data.presets || [];
    populatePresetDropdown();
  } catch (err) {
    console.warn("Could not load manga presets:", err);
  }
}

/**
 * Populates the #palette-preset-select dropdown with all available presets.
 */
function populatePresetDropdown() {
  const select = document.getElementById("palette-preset-select");
  if (!select) return;

  const currentVal = select.value;
  select.innerHTML = '<option value="">Custom / None</option>';

  const group = document.createElement("optgroup");
  group.label = "Popular Manga Presets";

  allMangaPresets.forEach(p => {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = `${p.title} (${p.characters.length} characters)`;
    group.appendChild(opt);
  });

  select.appendChild(group);
  if (currentVal) select.value = currentVal;
  if (select.refreshCustomSelect) {
    select.refreshCustomSelect();
  }
}

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
    currentPresetId = data.preset_id || data.palette?.preset_id || currentSession.detected_preset || "";
    const presetTitle = data.preset_title || data.palette?.preset_title || currentSession.preset_title || "";

    // Sync dropdown
    const select = document.getElementById("palette-preset-select");
    if (select) {
      if (currentPresetId && !Array.from(select.options).some(o => o.value === currentPresetId)) {
        // Preset might be custom or online-fetched, append if not present
        const opt = document.createElement("option");
        opt.value = currentPresetId;
        opt.textContent = presetTitle || currentPresetId;
        select.appendChild(opt);
      }
      select.value = currentPresetId || "";
      if (select.refreshCustomSelect) {
        select.refreshCustomSelect();
      }
    }

    // Auto-detected badge
    const badge = document.getElementById("palette-detected-badge");
    const desc = document.getElementById("palette-preset-desc");
    if (badge) {
      if (currentPresetId && presetTitle) {
        badge.style.display = "inline-flex";
        badge.title = `Preset: ${presetTitle}`;
        badge.innerHTML = `<i class="ri-sparkling-fill" style="margin-right:2px;"></i> ${presetTitle}`;
      } else {
        badge.style.display = "none";
      }
    }

    // Preset description
    if (desc) {
      const presetObj = allMangaPresets.find(p => p.id === currentPresetId);
      if (presetObj && presetObj.description) {
        desc.style.display = "block";
        desc.textContent = presetObj.description;
      } else {
        desc.style.display = "none";
      }
    }

    paletteRender();
    if (typeof fetchSeriesMemory === "function") {
      fetchSeriesMemory(currentSession?.session_id);
    }
  } catch (_) {
    // Silent — palette is optional
  }
}

/**
 * Handles user selecting a manga preset from the dropdown.
 */
async function onMangaPresetSelected(presetId) {
  if (!currentSession) {
    showToast("No active session selected.", "warning");
    return;
  }

  const select = document.getElementById("palette-preset-select");
  if (select && select.refreshCustomSelect) {
    select.refreshCustomSelect();
  }

  if (!presetId) {
    // User picked "Custom / None"
    currentPresetId = "";
    const badge = document.getElementById("palette-detected-badge");
    if (badge) badge.style.display = "none";
    const desc = document.getElementById("palette-preset-desc");
    if (desc) desc.style.display = "none";
    return;
  }

  try {
    const resp = await fetch("/api/palette/apply-preset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: currentSession.session_id,
        preset_id: presetId
      })
    });
    if (!resp.ok) throw new Error((await resp.json()).detail || "Failed to apply preset");
    const data = await resp.json();
    paletteCharacters = data.palette?.characters || [];
    currentPresetId = presetId;
    currentSession.detected_preset = presetId;
    currentSession.preset_title = data.preset_title;

    // Update active style recommendation if applicable
    const presetObj = allMangaPresets.find(p => p.id === presetId);
    if (presetObj && presetObj.recommended_style) {
      const styleSelect = document.getElementById("style-select");
      if (styleSelect) styleSelect.value = presetObj.recommended_style;
    }

    // Refresh preset info & palette list
    paletteLoadFromServer();
    renderDocumentQueue();
    showToast(`✨ Applied "${data.preset_title}" preset (${paletteCharacters.length} characters loaded).`, "success");
  } catch (err) {
    showToast(`Error applying preset: ${err.message}`, "error");
  }
}

/**
 * Opens the online preset search modal. Pre-fills input with clean series title.
 */
function openSearchPresetModal() {
  const modal = document.getElementById("preset-search-modal");
  const input = document.getElementById("preset-search-input");
  const results = document.getElementById("preset-search-results");
  const loading = document.getElementById("preset-search-loading");

  if (results) { results.style.display = "none"; results.innerHTML = ""; }
  if (loading) loading.style.display = "none";

  if (input && currentSession && currentSession.filename) {
    // Derive a clean series name suggestion from filename
    let clean = currentSession.filename
      .replace(/\.(pdf|epub|cbz|cbr|zip|tar|gz|png|jpg|jpeg|webp)$/i, "")
      .replace(/[\-_]+/g, " ")
      .replace(/vol(ume)?\.?\s*\d+/i, "")
      .replace(/ch(apter)?\.?\s*\d+/i, "")
      .replace(/\b(part|omnibus|colored|colorized|c2c)\b/gi, "")
      .trim();
    input.value = clean || currentSession.filename;
  }

  if (modal) modal.classList.remove("hidden");
  if (input) input.focus();
}

/**
 * Closes the online preset search modal.
 */
function closeSearchPresetModal() {
  const modal = document.getElementById("preset-search-modal");
  if (modal) modal.classList.add("hidden");
}

function handlePresetSearchOverlayClick(event) {
  if (event.target && event.target.id === "preset-search-modal") {
    closeSearchPresetModal();
  }
}

/**
 * Executes online lookup for manga color palette via backend /api/palette/search-online.
 */
async function executePresetOnlineSearch() {
  const input = document.getElementById("preset-search-input");
  const query = (input?.value || "").trim();
  if (!query) {
    showToast("Please enter a manga title to search.", "warning");
    return;
  }

  const loading = document.getElementById("preset-search-loading");
  const results = document.getElementById("preset-search-results");
  const btn = document.getElementById("btn-run-preset-search");

  if (loading) loading.style.display = "block";
  if (results) { results.style.display = "none"; results.innerHTML = ""; }
  if (btn) btn.disabled = true;

  try {
    const resp = await fetch("/api/palette/search-online", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query,
        session_id: currentSession ? currentSession.session_id : null
      })
    });

    if (!resp.ok) {
      const errData = await resp.json();
      throw new Error(errData.detail || "No character color palette found online.");
    }

    const data = await resp.json();
    const preset = data.preset;

    // Refresh preset list in memory
    await loadMangaPresets();

    if (results) {
      results.style.display = "block";
      const charChips = (preset.characters || []).map(c => `
        <div class="preset-swatch-chip" title="${c.name}: hair ${c.hair_hex}, costume ${c.costume_hex}">
          <span class="preset-swatch-dot" style="background:${c.costume_hex || c.hair_hex || '#1565c0'};"></span>
          <span>${c.name}</span>
        </div>
      `).join("");

      results.innerHTML = `
        <div class="preset-search-result-card">
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <div style="font-weight:600; font-size:0.9rem; color:#fff;">
              <i class="ri-check-line" style="color:var(--accent-green);"></i> ${preset.title}
            </div>
            <span class="badge badge-accent" style="font-size:0.7rem;">${(preset.characters || []).length} characters</span>
          </div>
          <p style="font-size:0.78rem; color:var(--text-secondary); margin:4px 0 8px;">
            ${preset.description || "Extracted from online sources"}
          </p>
          <div class="preset-swatch-list" style="margin-bottom:10px;">
            ${charChips}
          </div>
          <button class="btn btn-primary btn-sm btn-block" onclick="applyOnlineSearchResult('${preset.id}')">
            <i class="ri-sparkling-line"></i> Apply to Current Document
          </button>
        </div>
      `;
    }
  } catch (err) {
    if (results) {
      results.style.display = "block";
      results.innerHTML = `
        <div style="padding:10px; background:rgba(239,68,68,0.1); border:1px solid rgba(239,68,68,0.25); border-radius:6px; font-size:0.8rem; color:#ef4444;">
          <i class="ri-error-warning-line"></i> ${err.message}
        </div>
      `;
    }
  } finally {
    if (loading) loading.style.display = "none";
    if (btn) btn.disabled = false;
  }
}

async function applyOnlineSearchResult(presetId) {
  closeSearchPresetModal();
  await onMangaPresetSelected(presetId);
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
      No characters yet. Pick a preset above or add one below.
    </p>`;
    return;
  }

  list.innerHTML = paletteCharacters.map((ch, i) => {
    const swatches = [ch.hair_hex, ch.eye_hex, ch.skin_hex, ch.costume_hex, ch.extra_hex]
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

  if (typeof updatePageCharacterChips === "function") {
    updatePageCharacterChips(currentPreviewPageIndex);
  }
}

/**
 * Updates ONLY the palette character list UI (badge + rows) without touching the chips section.
 * Use this when you need to sync paletteCharacters without triggering updatePageCharacterChips.
 */
function paletteRenderListOnly() {
  const list = document.getElementById("palette-character-list");
  const badge = document.getElementById("palette-badge-count");
  if (!list) return;

  if (badge) badge.innerText = `${paletteCharacters.length} Character${paletteCharacters.length !== 1 ? "s" : ""}`;

  if (paletteCharacters.length === 0) {
    list.innerHTML = `<p style="font-size:0.78rem;color:var(--text-secondary);text-align:center;padding:0.5rem 0;">
      No characters yet. Pick a preset above or add one below.
    </p>`;
    return;
  }

  list.innerHTML = paletteCharacters.map((ch, i) => {
    const swatches = [ch.hair_hex, ch.eye_hex, ch.skin_hex, ch.costume_hex, ch.extra_hex]
      .filter(Boolean)
      .map(hx => `<span title="${hx}" style="display:inline-block;width:14px;height:14px;border-radius:3px;background:${hx};border:1px solid rgba(255,255,255,0.2);vertical-align:middle;"></span>`)
      .join(" ");

    return `
      <div style="display:flex;align-items:center;justify-content:space-between;background:var(--card-bg,#1e1e2e);border:1px solid var(--border-color);border-radius:6px;padding:6px 10px;gap:6px;">
        <span style="font-size:0.82rem;font-weight:500;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${ch.name}">${ch.name}</span>
        <span style="display:flex;gap:3px;align-items:center;">${swatches}</span>
        <button class="btn-icon" title="Remove ${ch.name}" onclick="paletteDeleteCharacter(${i})" style="padding:2px 5px;opacity:0.6;flex-shrink:0;">
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
  const eyeHex     = document.getElementById("pal-eye")?.value     || "";
  const skinHex    = document.getElementById("pal-skin")?.value    || "";
  const costumeHex = document.getElementById("pal-costume")?.value || "";
  const extraHex   = document.getElementById("pal-extra")?.value   || "";

  try {
    const resp = await fetch("/api/palette/upsert", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: currentSession.session_id,
        character: { name, hair_hex: hairHex, eye_hex: eyeHex, skin_hex: skinHex, costume_hex: costumeHex, extra_hex: extraHex }
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

window.loadMangaPresets              = loadMangaPresets;
window.onMangaPresetSelected         = onMangaPresetSelected;
window.openSearchPresetModal         = openSearchPresetModal;
window.closeSearchPresetModal        = closeSearchPresetModal;
window.handlePresetSearchOverlayClick = handlePresetSearchOverlayClick;
window.executePresetOnlineSearch     = executePresetOnlineSearch;
window.applyOnlineSearchResult       = applyOnlineSearchResult;
window.paletteAddCharacter           = paletteAddCharacter;
window.paletteDeleteCharacter        = paletteDeleteCharacter;
window.paletteLoadFromServer         = paletteLoadFromServer;


// ─────────────────────────────────────────────────────────────────────
//  Page Character Recognition & Optimization UI
// ─────────────────────────────────────────────────────────────────────

let activePageCharacterNames = new Set();

/**
 * Finds the canonical character from the palette using exact, substring, or keyword matching.
 */
function findCanonicalPaletteCharacter(name) {
  if (!name || !paletteCharacters || !paletteCharacters.length) return null;
  const nLow = name.trim().toLowerCase();
  // 1. Exact match
  let found = paletteCharacters.find(c => c.name.trim().toLowerCase() === nLow);
  if (found) return found;
  // 2. Substring match
  found = paletteCharacters.find(c => {
    const cLow = c.name.trim().toLowerCase();
    return cLow.includes(nLow) || nLow.includes(cLow);
  });
  if (found) return found;
  // 3. Keyword / alias match
  found = paletteCharacters.find(c => {
    if (!c.keywords) return false;
    return c.keywords.some(kw => nLow.includes(kw.toLowerCase()) || kw.toLowerCase().includes(nLow));
  });
  return found || null;
}

/**
 * Finds if a character was matched in the recognized list.
 */
function findMatchingRecognized(ch, recognizedList) {
  if (!recognizedList || !recognizedList.length) return null;
  const chLow = ch.name.trim().toLowerCase();
  for (const r of recognizedList) {
    const rLow = (r.name || "").trim().toLowerCase();
    if (rLow === chLow || chLow.includes(rLow) || rLow.includes(chLow)) return r;
    if (ch.keywords && ch.keywords.some(kw => rLow.includes(kw.toLowerCase()))) return r;
  }
  return null;
}

/**
 * Scans the current page with character recognition and renders active chips.
 */
async function recognizeCurrentPageCharacters() {
  if (!currentSession || !currentSession.pages || currentPreviewPageIndex < 0) {
    showToast("No active page selected to scan.", "warning");
    return;
  }

  const page = currentSession.pages[currentPreviewPageIndex];
  const btn = document.getElementById("btn-recognize-page");
  const origBtnHtml = btn ? btn.innerHTML : "";
  const pageNum = currentPreviewPageIndex + 1;
  if (btn) {
    btn.disabled = true;
    btn.title = `Scanning page ${pageNum}…`;
    btn.innerHTML = `<i class="ri-loader-4-line spinner"></i><span class="btn-label-scan">Scanning…</span>`;
  }

  try {
    const apiKey = typeof getActiveApiKey === "function" ? getActiveApiKey() : (document.getElementById("api-key-input")?.value || "");
    const modeSelect = document.getElementById("recognition-mode-select");
    const recognitionMode = modeSelect ? modeSelect.value : "auto";
    const resp = await fetch(`/api/session/${currentSession.session_id}/page/${currentPreviewPageIndex}/recognize`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_key: apiKey || "",
        model_name: "gemini-2.5-flash",
        recognition_mode: recognitionMode
      })
    });

    if (!resp.ok) {
      throw new Error((await resp.json()).detail || "Recognition request failed");
    }

    const data = await resp.json();
    const recognized = data.recognized || [];

    console.log("[MangaColorizer] Recognition response:", {
      recognized,
      paletteFromServer: data.palette?.characters?.map(c => c.name),
      currentPaletteChars: paletteCharacters.map(c => c.name)
    });

    // Store recognized characters on the page object
    page.recognized_characters = recognized;

    // Synchronize paletteCharacters FIRST if returned by server — update in-memory state only.
    // Do NOT call paletteRender() here to avoid a double-render race condition where
    // updatePageCharacterChips() inside paletteRender() fires before we set activePageCharacterNames.
    if (data.palette && data.palette.characters && data.palette.characters.length > 0) {
      paletteCharacters = data.palette.characters;
      // Refresh just the character list UI without touching the chips section
      if (typeof paletteRenderListOnly === "function") {
        paletteRenderListOnly();
      } else if (typeof paletteRender === "function") {
        // Safe fallback: paletteRender calls updatePageCharacterChips which uses page.recognized_characters
        paletteRender();
      }
    }

    console.log("[MangaColorizer] About to renderPageCharacterChips with:", {
      recognizedNames: recognized.map(r => r.name),
      paletteNames: paletteCharacters.map(c => c.name)
    });

    // Render chips — single authoritative call after palette is synced
    renderPageCharacterChips(recognized);

    console.log("[MangaColorizer] After renderPageCharacterChips, activePageCharacterNames:", Array.from(activePageCharacterNames));

    if (recognized.length > 0) {
      const names = recognized.map(r => r.name).join(", ");
      showToast(`🎯 Page ${pageNum}: Detected ${names}`, "success");
    } else {
      showToast(`Page ${pageNum}: No specific character detected (all palette colors active).`, "info");
    }
  } catch (err) {
    console.warn("[MangaColorizer] Character scan error:", err);
    showToast(`Scan error: ${err.message}`, "error");
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.title = `Auto-scan page ${pageNum} to detect characters`;
      btn.innerHTML = `<i class="ri-scan-line"></i><span class="btn-label-scan">Scan</span>`;
    }
  }
}

/**
 * Updates chips display when switching pages in preview.
 */
function updatePageCharacterChips(pageIdx) {
  if (!currentSession || !currentSession.pages) return;
  const page = currentSession.pages[pageIdx];
  const pageNum = pageIdx + 1;

  // Update header title and button tooltips with current page number
  const titleText = document.getElementById("palette-page-title-text");
  if (titleText) titleText.textContent = `Page ${pageNum} Characters`;
  const btn = document.getElementById("btn-recognize-page");
  if (btn && !btn.disabled) {
    btn.title = `Auto-scan page ${pageNum} to detect characters`;
    // Keep button label compact — just icon + "Scan"
    btn.innerHTML = `<i class="ri-scan-line"></i><span class="btn-label-scan">Scan</span>`;
  }
  const specBtn = document.getElementById("btn-specify-page-chars");
  if (specBtn) specBtn.title = `Manually pick characters for page ${pageNum}`;


  if (page && page.recognized_characters && page.recognized_characters.length > 0) {
    renderPageCharacterChips(page.recognized_characters);
  } else if (paletteCharacters && paletteCharacters.length > 0) {
    renderPageCharacterChips(null);
  } else {
    renderPageCharacterChips([]);
  }
}

/**
 * Renders interactive character chips for current page.
 */
function renderPageCharacterChips(recognizedList) {
  const container = document.getElementById("palette-page-characters-chips");
  if (!container) return;

  if ((!paletteCharacters || paletteCharacters.length === 0) && currentSession?.preset_characters) {
    paletteCharacters = currentSession.preset_characters;
  }

  if (!paletteCharacters || paletteCharacters.length === 0) {
    container.innerHTML = '<span style="font-size:0.72rem;color:var(--text-secondary);font-style:italic;">No characters in palette yet</span>';
    activePageCharacterNames.clear();
    return;
  }

  // Update activePageCharacterNames with canonical names if recognizedList is provided
  if (recognizedList !== undefined && recognizedList !== null) {
    activePageCharacterNames.clear();
    if (recognizedList.length > 0) {
      recognizedList.forEach(r => {
        const canonical = findCanonicalPaletteCharacter(r.name);
        if (canonical) {
          activePageCharacterNames.add(canonical.name);
        } else if (r.name) {
          activePageCharacterNames.add(r.name);
        }
      });
    } else {
      // Empty recognizedList means scanned with no specific characters found on this page
      activePageCharacterNames.clear();
    }
  } else if (recognizedList === null && activePageCharacterNames.size === 0) {
    activePageCharacterNames = new Set(paletteCharacters.map(c => c.name));
  }

  // Build lookup map for confidence badges
  const recMap = {};
  if (recognizedList && recognizedList.length > 0) {
    recognizedList.forEach(r => {
      const canonical = findCanonicalPaletteCharacter(r.name);
      const key = (canonical ? canonical.name : r.name).trim().toLowerCase();
      recMap[key] = r;
    });
  }

  const chipsHtml = paletteCharacters.map(ch => {
    const isSelected = activePageCharacterNames.has(ch.name);
    const rec = recMap[ch.name.trim().toLowerCase()] || findMatchingRecognized(ch, recognizedList);
    const dotColor = ch.costume_hex || ch.hair_hex || "#a855f7";
    const confBadge = rec && rec.confidence ? `<span class="chip-conf">${Math.round(rec.confidence * 100)}%</span>` : "";

    return `
      <div class="page-char-chip ${isSelected ? 'active' : ''}" 
           title="${isSelected ? 'Active on this page (click to exclude)' : 'Excluded from this page (click to include)'}"
           onclick="togglePageCharacterChip('${encodeURIComponent(ch.name)}')">
        <span class="chip-dot" style="background:${dotColor};"></span>
        <span>${escapeHtml(ch.name)}</span>
        ${confBadge}
      </div>
    `;
  }).join("");

  const pageNum = (currentPreviewPageIndex >= 0 ? currentPreviewPageIndex + 1 : 1);
  const statusNote = (recognizedList && recognizedList.length > 0)
    ? `<span style="font-size:0.68rem;color:#22c55e;width:100%;margin-top:2px;display:flex;align-items:center;gap:3px;"><i class="ri-check-line"></i> ${recognizedList.length} character${recognizedList.length > 1 ? 's' : ''} detected on page ${pageNum}. Click to toggle.</span>`
    : `<span style="font-size:0.68rem;color:var(--text-secondary);width:100%;margin-top:2px;display:block;">All palette characters active on page ${pageNum}. Click any to exclude.</span>`;

  container.innerHTML = chipsHtml + statusNote;
}

/**
 * Toggles a character on or off for the active page.
 */
function togglePageCharacterChip(encodedName) {
  const name = decodeURIComponent(encodedName);
  const canonical = findCanonicalPaletteCharacter(name);
  const targetName = canonical ? canonical.name : name;

  if (activePageCharacterNames.has(targetName)) {
    activePageCharacterNames.delete(targetName);
  } else {
    activePageCharacterNames.add(targetName);
  }
  const page = currentSession?.pages?.[currentPreviewPageIndex];
  if (page) {
    page.recognized_characters = Array.from(activePageCharacterNames).map(n => {
      const existing = (page.recognized_characters || []).find(r => r.name === n);
      return existing || { name: n, confidence: 1.0, detection_method: "manual" };
    });
  }
  // Re-render chips preserving current manual selection (passing undefined)
  renderPageCharacterChips(undefined);
}

window.recognizeCurrentPageCharacters = recognizeCurrentPageCharacters;
window.togglePageCharacterChip        = togglePageCharacterChip;
window.updatePageCharacterChips       = updatePageCharacterChips;
window.renderPageCharacterChips       = renderPageCharacterChips;


// ─────────────────────────────────────────────────────────────────────
//  Character Picker Modal — manually specify page characters
// ─────────────────────────────────────────────────────────────────────

/**
 * Escapes a string for safe insertion into HTML content / attributes.
 */
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Opens the character picker modal pre-populated with all palette characters.
 * Currently active characters are pre-checked.
 */
function openCharacterPickerModal() {
  if (!currentSession) {
    showToast("No active session. Load a document first.", "warning");
    return;
  }

  // Fallback 1: pull from session.preset_characters if paletteCharacters is empty
  if ((!paletteCharacters || paletteCharacters.length === 0) && currentSession.preset_characters) {
    paletteCharacters = currentSession.preset_characters;
  }

  // Fallback 2: if still empty, fetch palette from server then re-open
  if (!paletteCharacters || paletteCharacters.length === 0) {
    fetch(`/api/palette/${currentSession.session_id}`)
      .then(r => r.json())
      .then(data => {
        paletteCharacters = data.palette?.characters || [];
        if (paletteCharacters.length > 0) {
          openCharacterPickerModal(); // retry after palette is loaded
        } else {
          showToast("No characters in palette yet. Add characters or load a preset first.", "warning");
        }
      })
      .catch(() => showToast("Could not load palette. Try again.", "error"));
    return;
  }

  const modal = document.getElementById("char-picker-modal");
  const subtitle = document.getElementById("char-picker-subtitle");
  const list = document.getElementById("char-picker-list");
  const empty = document.getElementById("char-picker-empty");
  if (!modal || !list) {
    console.error("[MangaColorizer] char-picker-modal or char-picker-list element not found in DOM");
    showToast("UI error: character picker not found. Try refreshing the page.", "error");
    return;
  }

  // Update subtitle with current page number
  const pageNum = currentPreviewPageIndex >= 0 ? currentPreviewPageIndex + 1 : 1;
  if (subtitle) subtitle.textContent = `Choose which characters appear on page ${pageNum}`;

  list.innerHTML = "";
  empty.style.display = "none";

  if (paletteCharacters.length === 0) {
    empty.style.display = "block";
  } else {
    paletteCharacters.forEach(ch => {
      const isChecked = activePageCharacterNames.has(ch.name);
      const dotColor = ch.costume_hex || ch.hair_hex || "#a855f7";
      const swatches = [ch.hair_hex, ch.eye_hex, ch.skin_hex, ch.costume_hex, ch.extra_hex]
        .filter(Boolean)
        .map(hx => `<span title="${hx}" style="display:inline-block;width:12px;height:12px;border-radius:2px;background:${hx};border:1px solid rgba(255,255,255,0.2);flex-shrink:0;"></span>`)
        .join("");

      const row = document.createElement("label");
      row.style.cssText = "display:flex;align-items:center;gap:10px;padding:7px 10px;border-radius:7px;cursor:pointer;border:1px solid transparent;transition:background 0.15s,border-color 0.15s;user-select:none;";
      row.dataset.charName = ch.name;
      row.innerHTML = `
        <input type="checkbox" class="char-picker-cb" data-name="${escapeHtml(ch.name)}"
               style="width:15px;height:15px;accent-color:var(--accent-purple,#a855f7);cursor:pointer;flex-shrink:0;"
               ${isChecked ? "checked" : ""}>
        <span class="chip-dot" style="background:${dotColor};width:10px;height:10px;border-radius:50%;flex-shrink:0;"></span>
        <span style="font-size:0.82rem;font-weight:500;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${escapeHtml(ch.name)}</span>
        <span style="display:flex;gap:3px;align-items:center;flex-shrink:0;">${swatches}</span>
      `;

      // Highlight row on check change
      const updateRowStyle = (checked) => {
        row.style.background = checked ? "rgba(168,85,247,0.1)" : "";
        row.style.borderColor = checked ? "rgba(168,85,247,0.3)" : "transparent";
      };
      updateRowStyle(isChecked);

      row.querySelector(".char-picker-cb").addEventListener("change", (e) => {
        updateRowStyle(e.target.checked);
        _charPickerUpdateCount();
      });

      list.appendChild(row);
    });
  }

  _charPickerUpdateCount();
  modal.classList.remove("hidden");

  // Escape key to close
  document._charPickerEscHandler = (e) => { if (e.key === "Escape") closeCharacterPickerModal(); };
  document.addEventListener("keydown", document._charPickerEscHandler);
}

/**
 * Closes the character picker modal without applying.
 */
function closeCharacterPickerModal() {
  const modal = document.getElementById("char-picker-modal");
  if (modal) modal.classList.add("hidden");
  if (document._charPickerEscHandler) {
    document.removeEventListener("keydown", document._charPickerEscHandler);
    delete document._charPickerEscHandler;
  }
}

/**
 * Closes modal when clicking the dark overlay behind the dialog.
 */
function handleCharPickerOverlayClick(e) {
  const dialog = e.currentTarget.querySelector(".folder-import-dialog");
  if (dialog && !dialog.contains(e.target)) closeCharacterPickerModal();
}

/**
 * Checks all character checkboxes in the picker.
 */
function charPickerSelectAll() {
  document.querySelectorAll(".char-picker-cb").forEach(cb => {
    cb.checked = true;
    const row = cb.closest("label");
    if (row) {
      row.style.background = "rgba(168,85,247,0.1)";
      row.style.borderColor = "rgba(168,85,247,0.3)";
    }
  });
  _charPickerUpdateCount();
}

/**
 * Unchecks all character checkboxes in the picker.
 */
function charPickerSelectNone() {
  document.querySelectorAll(".char-picker-cb").forEach(cb => {
    cb.checked = false;
    const row = cb.closest("label");
    if (row) { row.style.background = ""; row.style.borderColor = "transparent"; }
  });
  _charPickerUpdateCount();
}

/**
 * Updates the "X of N selected" counter in the picker header.
 */
function _charPickerUpdateCount() {
  const total = document.querySelectorAll(".char-picker-cb").length;
  const checked = document.querySelectorAll(".char-picker-cb:checked").length;
  const label = document.getElementById("char-picker-count-label");
  if (label) label.textContent = `${checked} of ${total} selected`;
}

/**
 * Applies the checkbox selection to activePageCharacterNames and the current page's
 * recognized_characters list (with detection_method = "manual"), then refreshes chips.
 */
function applyCharacterPickerSelection() {
  const checkboxes = document.querySelectorAll(".char-picker-cb");
  if (!checkboxes.length) { closeCharacterPickerModal(); return; }

  // Build the new active set from checked boxes
  const selectedNames = new Set();
  checkboxes.forEach(cb => { if (cb.checked) selectedNames.add(cb.dataset.name); });

  // Commit to global state
  activePageCharacterNames = selectedNames;

  // Update page object so it persists when switching pages
  const page = currentSession?.pages?.[currentPreviewPageIndex];
  if (page) {
    page.recognized_characters = paletteCharacters
      .filter(ch => selectedNames.has(ch.name))
      .map(ch => {
        const existing = (page.recognized_characters || []).find(r => r.name === ch.name);
        return existing || { name: ch.name, confidence: 1.0, detection_method: "manual" };
      });
  }

  // Refresh chips without resetting the selection (pass undefined = preserve activePageCharacterNames)
  renderPageCharacterChips(undefined);

  closeCharacterPickerModal();

  const pageNum = currentPreviewPageIndex >= 0 ? currentPreviewPageIndex + 1 : 1;
  const count = selectedNames.size;
  if (count === 0) {
    showToast(`Page ${pageNum}: No characters selected — all palette colors will be used.`, "info");
  } else {
    const names = Array.from(selectedNames).join(", ");
    showToast(`✔ Page ${pageNum}: ${count} character${count > 1 ? "s" : ""} set (${names})`, "success");
  }
}

window.openCharacterPickerModal      = openCharacterPickerModal;
window.closeCharacterPickerModal     = closeCharacterPickerModal;
window.handleCharPickerOverlayClick  = handleCharPickerOverlayClick;
window.charPickerSelectAll           = charPickerSelectAll;
window.charPickerSelectNone          = charPickerSelectNone;
window.applyCharacterPickerSelection = applyCharacterPickerSelection;



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
        denoise_screentone: document.getElementById("chk-denoise-screentone") ? document.getElementById("chk-denoise-screentone").checked : true,
        active_character_names: activePageCharacterNames && activePageCharacterNames.size > 0 ? Array.from(activePageCharacterNames) : null,
        recognition_mode: document.getElementById("recognition-mode-select") ? document.getElementById("recognition-mode-select").value : "auto",
      })
    });

    const data = await resp.json();
    if (resp.ok && data.status === "success") {
      page.status = "colorized";
      page.colorized_url = data.colorized_url;
      if (data.recognized_characters) {
        page.recognized_characters = data.recognized_characters;
        if (currentPreviewPageIndex === pageIdx && typeof renderPageCharacterChips === "function") {
          renderPageCharacterChips(data.recognized_characters);
        }
      }
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

      if (data.exemplar_used) {
        showToast(`✨ ${page.display_name} recolorized with series exemplar (${data.exemplar_used})!`, "success");
      } else {
        showToast(`${page.display_name} recolorized!`, "success");
      }
      updateColorizedCount();
      // Re-render gallery so card recolorize button refreshes
      renderGalleryGrid();
      const learnBtn = document.getElementById("btn-learn-page-memory");
      if (learnBtn) learnBtn.disabled = false;
      if (typeof fetchSeriesMemory === "function") {
        fetchSeriesMemory(currentSession?.session_id);
      }
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

// ── Series Memory Active Learning Engine ─────────────────────────
let currentSeriesMemory = null;

async function fetchSeriesMemory(sessionId) {
  if (!sessionId && currentSession) sessionId = currentSession.session_id;
  if (!sessionId) return;
  try {
    const resp = await fetch(`/api/series-memory/${sessionId}`);
    if (!resp.ok) return;
    const data = await resp.json();
    currentSeriesMemory = data.memory || null;

    const box = document.getElementById("series-memory-status-box");
    const learnedCountEl = document.getElementById("series-memory-learned-count");
    const exemplarCountEl = document.getElementById("series-memory-exemplar-count");
    const previewBadge = document.getElementById("series-memory-preview-badge");

    const learnedCount = currentSeriesMemory && currentSeriesMemory.characters
      ? Object.keys(currentSeriesMemory.characters).length
      : 0;
    const exemplarCount = currentSeriesMemory && currentSeriesMemory.exemplar_pages
      ? currentSeriesMemory.exemplar_pages.length
      : 0;

    if (box) {
      if (currentSeriesMemory && (learnedCount > 0 || exemplarCount > 0)) {
        box.style.display = "flex";
        if (learnedCountEl) learnedCountEl.textContent = learnedCount;
        if (exemplarCountEl) exemplarCountEl.textContent = exemplarCount;
      } else {
        box.style.display = "none";
      }
    }

    if (previewBadge) {
      if (currentSeriesMemory && (learnedCount > 0 || exemplarCount > 0)) {
        previewBadge.style.display = "inline-flex";
        previewBadge.title = `Series Memory Active: ${learnedCount} learned character prior(s), ${exemplarCount} visual exemplar(s)`;
      } else {
        previewBadge.style.display = "none";
      }
    }

    if (typeof updateExemplarPreviewChip === "function") {
      updateExemplarPreviewChip(currentSession?.pages?.[currentPreviewPageIndex]);
    }
    if (typeof updateQualityPreviewChip === "function") {
      updateQualityPreviewChip(currentSession?.pages?.[currentPreviewPageIndex]);
    }
    if (typeof fetchSeriesAdapterStatus === "function") {
      fetchSeriesAdapterStatus(sessionId);
    }
    if (typeof fetchSeriesAutoRefineStatus === "function") {
      fetchSeriesAutoRefineStatus(sessionId);
    }
  } catch (err) {
    console.warn("Failed to fetch series memory:", err);
  }
}

async function learnCurrentPreviewPage() {
  if (!currentSession) {
    showToast("No active session.", "warning");
    return;
  }
  if (currentPreviewPageIndex < 0 || !currentSession.pages[currentPreviewPageIndex]) {
    showToast("No page selected in preview.", "warning");
    return;
  }
  const page = currentSession.pages[currentPreviewPageIndex];
  if (page.status !== "colorized") {
    showToast("Please colorize this page first before saving to Series Memory.", "warning");
    return;
  }

  const btn = document.getElementById("btn-learn-page-memory");
  const origHtml = btn ? btn.innerHTML : "";
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="ri-loader-4-line spinner"></i> Learning…';
  }

  try {
    const resp = await fetch("/api/series-memory/learn-page", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: currentSession.session_id,
        page_index: currentPreviewPageIndex,
        exemplar: true
      })
    });
    const data = await resp.json();
    if (resp.ok && data.status === "ok") {
      showToast(`🧠 ${data.message || "Page learned into Series Memory!"}`, "success");
      if (btn) {
        btn.innerHTML = '<i class="ri-check-line"></i> Learned!';
        setTimeout(() => {
          if (btn) {
            btn.disabled = false;
            btn.innerHTML = origHtml || '<i class="ri-brain-line"></i> Learn Page';
          }
        }, 2000);
      }
      await fetchSeriesMemory(currentSession.session_id);
      await paletteLoadFromServer();
    } else {
      showToast(data.detail || "Failed to learn page into series memory.", "error");
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = origHtml || '<i class="ri-brain-line"></i> Learn Page';
      }
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = origHtml || '<i class="ri-brain-line"></i> Learn Page';
    }
  }
}

async function resetCurrentSeriesMemory(event) {
  if (event) event.stopPropagation();
  if (!currentSession) return;
  const seriesKey = currentSeriesMemory?.series_key || currentSession.detected_preset || "";
  if (!seriesKey) {
    showToast("No series key identified for this manga.", "warning");
    return;
  }

  const confirmed = await showConfirmModal({
    title: "Reset Series Memory",
    message: `Reset learned Series Memory and exemplars for "${currentSeriesMemory?.title || seriesKey}"? This will clear active cross-page learning priors for this series.`,
    confirmText: "Reset Memory",
    confirmClass: "btn-danger"
  });

  if (!confirmed) return;

  try {
    const resp = await fetch(`/api/series-memory/reset/${seriesKey}`, { method: "POST" });
    const data = await resp.json();
    if (resp.ok && data.status === "ok") {
      showToast("Series Memory reset successfully.", "info");
      await fetchSeriesMemory(currentSession.session_id);
      await paletteLoadFromServer();
    } else {
      showToast(data.detail || "Reset failed.", "error");
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

// ── Visual Exemplars & Cross-Page Color Transfer ───────────────────

function updateExemplarPreviewChip(page) {
  const chip = document.getElementById("preview-exemplar-chip");
  const label = document.getElementById("preview-exemplar-label");
  if (!chip || !label) return;

  if (!page) {
    chip.style.display = "none";
    return;
  }

  const exemplars = page.exemplars_used || (page.exemplar_used ? [page.exemplar_used] : []);
  if (exemplars.length > 0) {
    chip.style.display = "inline-flex";
    if (exemplars.length === 1) {
      const match = String(exemplars[0]).match(/p(\d+)_/);
      const refPage = match ? `Page ${parseInt(match[1], 10) + 1}` : "Ref Page";
      label.textContent = `Ref: ${refPage}`;
      chip.title = `Visual exemplar used: ${refPage}. Click to view or manage all series exemplars.`;
    } else {
      label.textContent = `Refs: ${exemplars.length} Pages`;
      chip.title = `${exemplars.length} visual exemplars applied for color harmony. Click to manage.`;
    }
  } else if (currentSeriesMemory && currentSeriesMemory.exemplar_pages && currentSeriesMemory.exemplar_pages.length > 0) {
    chip.style.display = "inline-flex";
    label.textContent = `Refs: ${currentSeriesMemory.exemplar_pages.length} Saved`;
    chip.title = `${currentSeriesMemory.exemplar_pages.length} visual exemplar(s) in Series Memory. Click to view or manage.`;
  } else {
    chip.style.display = "none";
  }
}

function updateQualityPreviewChip(page) {
  const chip = document.getElementById("preview-quality-chip");
  const label = document.getElementById("preview-quality-label");
  const icon = document.getElementById("preview-quality-icon");
  if (!chip || !label || !icon) return;

  if (!page || !page.quality_score || page.status !== "colorized") {
    chip.style.display = "none";
    return;
  }

  const q = page.quality_score;
  const scorePct = Math.round((q.overall_score || 0) * 100);
  const grade = q.grade || (scorePct >= 82 ? "high" : scorePct >= 65 ? "moderate" : "review_suggested");
  const m = q.metrics || {};

  chip.style.display = "inline-flex";

  const metricsDesc = `Linework: ${Math.round((m.linework_integrity || 0) * 100)}% | White Purity: ${Math.round((m.white_purity || 0) * 100)}% | Richness: ${Math.round((m.color_richness || 0) * 100)}%`;

  if (grade === "high") {
    chip.style.background = "rgba(34, 197, 94, 0.18)";
    chip.style.color = "#4ade80";
    chip.style.borderColor = "rgba(34, 197, 94, 0.35)";
    icon.className = "ri-shield-check-line";
    label.textContent = `Quality: ${scorePct}%`;
    chip.title = `High Confidence (${scorePct}%): Clean linework & pure bubbles. ${metricsDesc}`;
  } else if (grade === "moderate") {
    chip.style.background = "rgba(234, 179, 8, 0.18)";
    chip.style.color = "#facc15";
    chip.style.borderColor = "rgba(234, 179, 8, 0.35)";
    icon.className = "ri-shield-line";
    label.textContent = `Quality: ${scorePct}%`;
    chip.title = `Moderate Quality (${scorePct}%). ${metricsDesc}`;
  } else {
    chip.style.background = "rgba(239, 68, 68, 0.18)";
    chip.style.color = "#f87171";
    chip.style.borderColor = "rgba(239, 68, 68, 0.35)";
    icon.className = "ri-alert-line";
    label.textContent = `Review Suggested (${scorePct}%)`;
    chip.title = `Review Suggested (${scorePct}%): Potential color bleeding or desaturation. ${metricsDesc}`;
  }
}

async function openExemplarGalleryModal() {
  if (!currentSession) {
    showToast("No active session.", "warning");
    return;
  }

  const overlay = document.getElementById("exemplar-gallery-modal-overlay");
  if (!overlay) return;
  overlay.classList.remove("hidden");

  if (typeof fetchSeriesAdapterStatus === "function") {
    fetchSeriesAdapterStatus(currentSession.session_id);
  }
  if (typeof fetchSeriesAutoRefineStatus === "function") {
    fetchSeriesAutoRefineStatus(currentSession.session_id);
  }

  const loadingEl = document.getElementById("exemplar-gallery-loading");
  const emptyEl = document.getElementById("exemplar-gallery-empty");
  const gridEl = document.getElementById("exemplar-gallery-grid");

  if (loadingEl) loadingEl.style.display = "block";
  if (emptyEl) emptyEl.style.display = "none";
  if (gridEl) gridEl.innerHTML = "";

  try {
    const resp = await fetch(`/api/series-memory/${currentSession.session_id}/exemplars`);
    if (!resp.ok) {
      throw new Error(`Server returned ${resp.status}`);
    }
    const data = await resp.json();
    if (loadingEl) loadingEl.style.display = "none";

    const titleEl = document.getElementById("exemplar-gallery-title");
    if (titleEl && data.title) {
      titleEl.textContent = `Series Color Exemplars: ${data.title}`;
    }

    renderExemplarGallery(data.series_key, data.exemplars || []);
  } catch (err) {
    if (loadingEl) loadingEl.style.display = "none";
    showToast(`Failed to load exemplars: ${err.message}`, "error");
  }
}

function closeExemplarGalleryModal() {
  const overlay = document.getElementById("exemplar-gallery-modal-overlay");
  if (overlay) overlay.classList.add("hidden");
}

function handleExemplarGalleryOverlayClick(event) {
  if (event.target.id === "exemplar-gallery-modal-overlay") {
    closeExemplarGalleryModal();
  }
}

function renderExemplarGallery(seriesKey, exemplars) {
  const emptyEl = document.getElementById("exemplar-gallery-empty");
  const gridEl = document.getElementById("exemplar-gallery-grid");
  if (!gridEl) return;

  if (!exemplars || exemplars.length === 0) {
    if (emptyEl) emptyEl.style.display = "block";
    gridEl.innerHTML = "";
    return;
  }

  if (emptyEl) emptyEl.style.display = "none";

  const safeSeriesKey = escapeHtml(seriesKey || "");

  gridEl.innerHTML = exemplars.map((ex) => {
    const pageNum = (typeof ex.page_index === "number") ? ex.page_index + 1 : 1;
    const isPinned = Boolean(ex.pinned);
    const styleLabel = escapeHtml(ex.style || "manga");
    const lumLabel = (typeof ex.mean_l === "number") ? `L: ${ex.mean_l}` : "";
    const charNames = Array.isArray(ex.character_names) ? ex.character_names : [];
    const charChips = charNames.length > 0
      ? `<div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:2px;">` +
        charNames.slice(0, 3).map(n => `<span style="font-size:0.65rem;background:rgba(168,85,247,0.2);color:#c084fc;padding:1px 5px;border-radius:3px;">${escapeHtml(n)}</span>`).join("") +
        (charNames.length > 3 ? `<span style="font-size:0.65rem;color:var(--text-muted);">+${charNames.length - 3}</span>` : "") +
        `</div>`
      : "";

    const imgUrl = ex.image_url ? `${ex.image_url}?t=${Date.now()}` : "/static/placeholder.png";

    const qScoreVal = (typeof ex.quality_score === "number")
      ? ex.quality_score
      : (typeof ex.overall_score === "number" ? ex.overall_score : null);
    const qualityChip = qScoreVal !== null
      ? `<span style="font-size:0.65rem;background:rgba(34,197,94,0.18);color:#4ade80;padding:1px 5px;border-radius:3px;" title="Quality Confidence Score"><i class="ri-shield-check-line"></i> ${Math.round(qScoreVal * 100)}%</span>`
      : (lumLabel ? `<span style="font-size:0.68rem;color:var(--text-muted);">${lumLabel}</span>` : "");

    return `
      <div class="exemplar-card" style="border:1px solid var(--bg-card-border);border-radius:8px;background:var(--bg-card);display:flex;flex-direction:column;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.2);">
        <div style="position:relative;width:100%;aspect-ratio:3/4;background:#18181b;display:flex;align-items:center;justify-content:center;overflow:hidden;">
          <img src="${imgUrl}" alt="Page ${pageNum}" style="width:100%;height:100%;object-fit:cover;display:block;" loading="lazy">
          <span style="position:absolute;top:6px;left:6px;background:rgba(0,0,0,0.75);color:#fff;font-size:0.7rem;padding:2px 6px;border-radius:4px;font-weight:600;">
            Page ${pageNum}
          </span>
          ${isPinned ? `<span style="position:absolute;top:6px;right:6px;background:rgba(234,179,8,0.95);color:#000;font-size:0.65rem;padding:2px 6px;border-radius:4px;font-weight:700;display:flex;align-items:center;gap:3px;"><i class="ri-pushpin-fill"></i> PINNED</span>` : ""}
        </div>
        <div style="padding:8px 10px;display:flex;flex-direction:column;gap:5px;flex:1;">
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-size:0.72rem;color:var(--text-secondary);text-transform:capitalize;">${styleLabel}</span>
            ${qualityChip}
          </div>
          ${charChips}
          <div style="display:flex;gap:6px;margin-top:auto;padding-top:8px;border-top:1px solid var(--bg-card-border);">
            <button class="btn btn-secondary btn-sm" onclick="pinSeriesExemplar('${safeSeriesKey}', ${ex.page_index}, ${!isPinned})" style="flex:1;font-size:0.72rem;padding:3px 6px;justify-content:center;" title="${isPinned ? 'Unpin exemplar' : 'Pin exemplar as top priority'}">
              <i class="${isPinned ? 'ri-pushpin-line' : 'ri-pushpin-2-line'}"></i> ${isPinned ? 'Unpin' : 'Pin'}
            </button>
            <button class="btn btn-secondary btn-sm" onclick="deleteSeriesExemplar('${safeSeriesKey}', ${ex.page_index})" style="color:#ef4444;font-size:0.72rem;padding:3px 8px;" title="Delete exemplar">
              <i class="ri-delete-bin-line"></i>
            </button>
          </div>
        </div>
      </div>
    `;
  }).join("");
}

async function pinSeriesExemplar(seriesKey, pageIndex, pinned) {
  try {
    const resp = await fetch("/api/series-memory/pin-exemplar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        series_key: seriesKey,
        page_index: pageIndex,
        pinned: pinned
      })
    });
    const data = await resp.json();
    if (resp.ok && data.status === "ok") {
      showToast(pinned ? `📌 Page ${pageIndex + 1} pinned as primary exemplar!` : `Unpinned Page ${pageIndex + 1}.`, "info");
      if (currentSession) {
        await fetchSeriesMemory(currentSession.session_id);
      }
      await openExemplarGalleryModal();
    } else {
      showToast(data.detail || "Failed to update pinned status.", "error");
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

async function deleteSeriesExemplar(seriesKey, pageIndex) {
  const confirmed = await showConfirmModal({
    title: "Delete Exemplar",
    message: `Remove Page ${pageIndex + 1} from Series Memory exemplars? It will no longer serve as a visual color transfer reference.`,
    confirmText: "Delete",
    confirmClass: "btn-danger"
  });

  if (!confirmed) return;

  try {
    const resp = await fetch(`/api/series-memory/${seriesKey}/exemplar/${pageIndex}`, {
      method: "DELETE"
    });
    const data = await resp.json();
    if (resp.ok && data.status === "ok") {
      showToast(`Removed Page ${pageIndex + 1} exemplar from Series Memory.`, "info");
      if (currentSession) {
        await fetchSeriesMemory(currentSession.session_id);
      }
      await openExemplarGalleryModal();
    } else {
      showToast(data.detail || "Failed to delete exemplar.", "error");
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

async function fetchSeriesAdapterStatus(sessionId) {
  if (!sessionId) return;
  try {
    const resp = await fetch(`/api/series-memory/${sessionId}/adapter-status`);
    if (!resp.ok) return;
    const data = await resp.json();

    const badge = document.getElementById("adapter-status-badge");
    const subtext = document.getElementById("adapter-status-subtext");
    const btnTrain = document.getElementById("btn-train-adapter");
    const btnDelete = document.getElementById("btn-delete-adapter");
    const container = document.getElementById("adapter-training-progress-container");
    const sideBadge = document.getElementById("series-adapter-badge");

    if (data.status === "ready") {
      if (badge) {
        badge.textContent = "Ready";
        badge.style.background = "rgba(168,85,247,0.25)";
        badge.style.color = "#c084fc";
      }
      if (subtext) {
        const lossStr = typeof data.loss === "number" ? ` | Loss: ${data.loss.toFixed(4)}` : "";
        const samplesStr = data.samples_count ? ` | ${data.samples_count} sample(s)` : "";
        subtext.textContent = `LoRA active (${data.steps || 100} steps${lossStr}${samplesStr}). Residual generator adapts to series style.`;
      }
      if (btnTrain) {
        btnTrain.disabled = false;
        btnTrain.innerHTML = '<i class="ri-refresh-line"></i> Re-Train LoRA';
      }
      if (btnDelete) {
        btnDelete.style.display = "inline-flex";
      }
      if (container) {
        container.style.display = "none";
      }
      if (sideBadge) {
        sideBadge.style.display = "inline-flex";
        sideBadge.textContent = "LoRA: Active";
        sideBadge.style.background = "rgba(168,85,247,0.2)";
        sideBadge.style.color = "#c084fc";
      }
    } else if (data.status === "training") {
      updateAdapterTrainingProgressUI(data);
    } else {
      // not_trained, failed, or unavailable
      if (badge) {
        badge.textContent = "Not Trained";
        badge.style.background = "rgba(255,255,255,0.08)";
        badge.style.color = "var(--text-muted)";
      }
      if (subtext) {
        subtext.textContent = "Adapts neural generator weights to the artist's shading & linework habits.";
      }
      if (btnTrain) {
        btnTrain.disabled = false;
        btnTrain.innerHTML = '<i class="ri-sparkles-line"></i> Fine-Tune LoRA';
      }
      if (btnDelete) {
        btnDelete.style.display = "none";
      }
      if (container) {
        container.style.display = "none";
      }
      if (sideBadge) {
        sideBadge.style.display = "none";
      }
    }
  } catch (err) {
    console.warn("Failed to fetch adapter status:", err);
  }
}

function updateAdapterTrainingProgressUI(data) {
  const container = document.getElementById("adapter-training-progress-container");
  const stepText = document.getElementById("adapter-training-step-text");
  const lossText = document.getElementById("adapter-training-loss-text");
  const fill = document.getElementById("adapter-training-progress-fill");
  const badge = document.getElementById("adapter-status-badge");
  const subtext = document.getElementById("adapter-status-subtext");
  const btnTrain = document.getElementById("btn-train-adapter");
  const sideBadge = document.getElementById("series-adapter-badge");

  if (data.status === "training") {
    if (container) container.style.display = "block";
    const pct = Math.min(100, Math.max(0, Math.round((data.progress || 0) * 100)));
    if (fill) fill.style.width = `${pct}%`;
    if (stepText) stepText.textContent = `Fine-tuning: Step ${data.step} / ${data.total_steps} (${pct}%)`;
    if (lossText) lossText.textContent = `Loss: ${typeof data.loss === "number" ? data.loss.toFixed(4) : "--"}`;
    if (subtext) subtext.textContent = "Fine-tuning in progress... Adapting generator to series linework & style.";
    if (badge) {
      badge.textContent = "Training…";
      badge.style.background = "rgba(234,179,8,0.2)";
      badge.style.color = "#facc15";
    }
    if (btnTrain) {
      btnTrain.disabled = true;
      btnTrain.innerHTML = '<i class="ri-loader-4-line spinner"></i> Training…';
    }
    if (sideBadge) {
      sideBadge.style.display = "inline-flex";
      sideBadge.textContent = "LoRA: Training…";
      sideBadge.style.background = "rgba(234,179,8,0.2)";
      sideBadge.style.color = "#facc15";
    }
  } else if (data.status === "completed") {
    if (container) {
      if (fill) fill.style.width = "100%";
      setTimeout(() => { if (container) container.style.display = "none"; }, 1500);
    }
    showToast("🎉 Series Style LoRA adapter training complete!", "success");
    if (currentSession) {
      fetchSeriesAdapterStatus(currentSession.session_id);
    }
  }
}

async function triggerSeriesAdapterTraining() {
  if (!currentSession) {
    showToast("No active session.", "warning");
    return;
  }
  const btn = document.getElementById("btn-train-adapter");
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<i class="ri-loader-4-line spinner"></i> Starting…';
  }
  try {
    const resp = await fetch(`/api/series-memory/${currentSession.session_id}/train-adapter`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ steps: 100, lr: 0.0002 })
    });
    const data = await resp.json();
    if (resp.ok && data.status === "training_started") {
      showToast(`⚡ Fine-tuning started (${data.samples_count} sample images, ${data.total_steps} steps).`, "info");
      const container = document.getElementById("adapter-training-progress-container");
      if (container) container.style.display = "block";
    } else {
      showToast(data.detail || "Failed to start adapter training.", "error");
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<i class="ri-sparkles-line"></i> Fine-Tune LoRA';
      }
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
    if (btn) {
      btn.disabled = false;
      btn.innerHTML = '<i class="ri-sparkles-line"></i> Fine-Tune LoRA';
    }
  }
}

async function deleteCurrentSeriesAdapter() {
  if (!currentSession) {
    showToast("No active session.", "warning");
    return;
  }
  const confirmed = await showConfirmModal({
    title: "Delete Series Adapter",
    message: "Delete the trained Series LoRA weights for this manga? Colorization will revert to base neural generator weights.",
    confirmText: "Delete Adapter",
    confirmClass: "btn-danger"
  });
  if (!confirmed) return;

  try {
    const resp = await fetch(`/api/series-memory/${currentSession.session_id}/adapter`, {
      method: "DELETE"
    });
    const data = await resp.json();
    if (resp.ok && data.status === "ok") {
      showToast("🗑️ Series Style LoRA adapter deleted.", "info");
      await fetchSeriesAdapterStatus(currentSession.session_id);
    } else {
      showToast(data.detail || "Failed to delete series adapter.", "error");
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

async function fetchSeriesAutoRefineStatus(sessionId) {
  if (!sessionId) return;
  try {
    const resp = await fetch(`/api/series-memory/${sessionId}/auto-refine`);
    if (!resp.ok) return;
    const data = await resp.json();

    const chk = document.getElementById("chk-auto-refine-adapter");
    const counterText = document.getElementById("auto-refine-counter-text");
    const gateBadge = document.getElementById("auto-harvest-threshold-badge");

    if (chk) {
      chk.checked = Boolean(data.auto_refine_enabled);
    }
    if (counterText) {
      counterText.textContent = `${data.unrefined_pages_count || 0} / ${data.auto_refine_interval || 5} harvested`;
    }
    if (gateBadge && typeof data.auto_harvest_threshold === "number") {
      gateBadge.textContent = `Gate: ≥ ${Math.round(data.auto_harvest_threshold * 100)}% Quality`;
    }
  } catch (err) {
    console.warn("Failed to fetch auto-refine status:", err);
  }
}

async function toggleAutoRefineAdapter(enabled) {
  if (!currentSession) return;
  try {
    const resp = await fetch(`/api/series-memory/${currentSession.session_id}/auto-refine`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: Boolean(enabled) })
    });
    const data = await resp.json();
    if (resp.ok && data.status === "ok") {
      showToast(
        enabled
          ? "🤖 Auto-refine enabled: High-confidence pages will auto-update LoRA."
          : "Auto-refine disabled.",
        "info"
      );
    }
  } catch (err) {
    showToast(`Error: ${err.message}`, "error");
  }
}

window.recolorizePage     = recolorizePage;
window.recolorizeSelected = recolorizeSelected;
window.changeHistoryPage = changeHistoryPage;
window.handleBulkChunkedUpload = handleBulkChunkedUpload;
window.openImportProgressModal = openImportProgressModal;
window.closeImportProgressModal = closeImportProgressModal;
window.cancelBatchImport = cancelBatchImport;
window.openFolderImportModal = openFolderImportModal;
window.closeFolderImportModal = closeFolderImportModal;
window.handleFolderImportOverlayClick = handleFolderImportOverlayClick;
window.startFolderImport = startFolderImport;
window.triggerFolderPicker = triggerFolderPicker;
window.handleFolderPickerSelection = handleFolderPickerSelection;
window.setFolderPath = setFolderPath;
window.onFolderInputChanged = onFolderInputChanged;
window.validateAndDisplayFolderPath = validateAndDisplayFolderPath;
window.filterDocumentQueue = filterDocumentQueue;
window.clearQueueFilter = clearQueueFilter;
window.openFolderBrowserModal = openFolderBrowserModal;
window.closeFolderBrowserModal = closeFolderBrowserModal;
window.handleFolderBrowserOverlayClick = handleFolderBrowserOverlayClick;
window.loadBrowserDirectory = loadBrowserDirectory;
window.navigateBrowserUp = navigateBrowserUp;
window.confirmFolderBrowserSelection = confirmFolderBrowserSelection;
window.filterBrowserFolders = filterBrowserFolders;
window.showConfirmModal = showConfirmModal;
window.resolveCustomConfirm = resolveCustomConfirm;
window.handleCustomConfirmOverlayClick = handleCustomConfirmOverlayClick;
window.fetchSeriesMemory = fetchSeriesMemory;
window.learnCurrentPreviewPage = learnCurrentPreviewPage;
window.resetCurrentSeriesMemory = resetCurrentSeriesMemory;
window.updateExemplarPreviewChip = updateExemplarPreviewChip;
window.openExemplarGalleryModal = openExemplarGalleryModal;
window.closeExemplarGalleryModal = closeExemplarGalleryModal;
window.handleExemplarGalleryOverlayClick = handleExemplarGalleryOverlayClick;
window.renderExemplarGallery = renderExemplarGallery;
window.pinSeriesExemplar = pinSeriesExemplar;
window.deleteSeriesExemplar = deleteSeriesExemplar;
window.fetchSeriesAdapterStatus = fetchSeriesAdapterStatus;
window.triggerSeriesAdapterTraining = triggerSeriesAdapterTraining;
window.deleteCurrentSeriesAdapter = deleteCurrentSeriesAdapter;
window.updateAdapterTrainingProgressUI = updateAdapterTrainingProgressUI;
window.updateQualityPreviewChip = updateQualityPreviewChip;
window.fetchSeriesAutoRefineStatus = fetchSeriesAutoRefineStatus;
window.toggleAutoRefineAdapter = toggleAutoRefineAdapter;

