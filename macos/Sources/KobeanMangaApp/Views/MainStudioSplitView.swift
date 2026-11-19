import AppKit
import KobeanMangaCore
import SwiftUI
import UniformTypeIdentifiers

struct MainStudioSplitView: View {
    @Bindable var store: StudioStore
    @State private var isSidebarVisible: Bool = true
    @State private var isDropTargeted: Bool = false

    var body: some View {
        let theme = store.currentTheme

        VStack(spacing: 0) {
            studioTopHeaderBar(theme: theme)

            HStack(spacing: 6) {
                if !store.isFullscreenComparator && isSidebarVisible {
                    StudioPaneContainer(theme: theme, background: theme.bgHeader, cornerRadius: 10) {
                        DocumentQueueSidebar(store: store)
                    }
                    .frame(width: 268)
                    .transition(
                        .asymmetric(
                            insertion: .move(edge: .leading).combined(with: .opacity),
                            removal: .move(edge: .leading).combined(with: .opacity)
                        )
                    )
                }

                centerWorkspace(theme: theme)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)

                if !store.isFullscreenComparator && store.isInspectorVisible {
                    StudioPaneContainer(theme: theme, background: theme.bgHeader, cornerRadius: 10) {
                        StudioInspectorView(store: store)
                    }
                    .frame(width: 332)
                    .transition(
                        .asymmetric(
                            insertion: .move(edge: .trailing).combined(with: .opacity),
                            removal: .move(edge: .trailing).combined(with: .opacity)
                        )
                    )
                }
            }
            .padding(.horizontal, 6)
            .padding(.bottom, 6)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .animation(.spring(response: 0.28, dampingFraction: 0.84), value: isSidebarVisible)
            .animation(.spring(response: 0.28, dampingFraction: 0.84), value: store.isInspectorVisible)
            .animation(.spring(response: 0.28, dampingFraction: 0.84), value: store.isFullscreenComparator)
        }
        .background(theme.bgDark)
        .animation(.easeInOut(duration: 0.22), value: store.activeThemeID)
        .ignoresSafeArea(.container, edges: .top)
        .overlay {
            if isDropTargeted {
                dropOverlay(theme: theme)
                    .transition(.opacity.combined(with: .scale(scale: 0.98)))
            }
        }
        .animation(.spring(response: 0.22, dampingFraction: 0.82), value: isDropTargeted)
        .onDrop(of: [.fileURL], isTargeted: $isDropTargeted) { providers in
            handleDrop(providers: providers)
        }
        .sheet(isPresented: $store.showExemplarSheet) {
            ExemplarLoRASheetView(store: store)
        }
        .sheet(isPresented: $store.showHistorySheet) {
            HistorySheetView(store: store)
        }
    }

    private func studioTopHeaderBar(theme: StudioTheme) -> some View {
        ZStack {
            // Centered window title & active session status
            HStack(spacing: 6) {
                StudioBrandLogoView(size: 18, style: .markOnly, theme: theme)

                Text(store.activeSession?.filename ?? "Kobean Manga Colorizer")
                    .font(.system(size: 12.5, weight: .semibold))
                    .foregroundStyle(theme.textPrimary)
                    .lineLimit(1)
                    .truncationMode(.middle)

                if !navigationSubtitleText.isEmpty {
                    Text("·")
                        .font(.caption)
                        .foregroundStyle(theme.textMuted)
                    Text(navigationSubtitleText)
                        .font(.system(size: 11, weight: .medium))
                        .monospacedDigit()
                        .foregroundStyle(theme.textSecondary)
                        .lineLimit(1)
                }
            }
            .padding(.horizontal, 260)
            .allowsHitTesting(false)

            HStack(spacing: 8) {
                // Left traffic lights clearance + sidebar toggle
                HStack(spacing: 6) {
                    Color.clear
                        .frame(width: 66, height: 1)

                    if !store.isFullscreenComparator {
                        StudioToolbarIconButton(
                            title: "Toggle Document Queue Sidebar",
                            systemImage: "sidebar.left",
                            isActive: isSidebarVisible,
                            theme: theme
                        ) {
                            withAnimation(.spring(response: 0.28, dampingFraction: 0.84)) {
                                isSidebarVisible.toggle()
                            }
                        }
                        .studioHeaderInteractiveControl()
                    }
                }

                Spacer(minLength: 12)

                // Right Studio action cluster (flat, seamless, zero macOS pill bezel)
                HStack(spacing: 4) {
                    StudioToolbarIconButton(
                        title: "Import Manga Files (⌘O)",
                        systemImage: "doc.badge.plus",
                        theme: theme
                    ) {
                        let urls = StudioFilePanels.pickFiles()
                        if !urls.isEmpty {
                            Task { await store.uploadFiles(urls) }
                        }
                    }

                    StudioToolbarIconButton(
                        title: "Import Manga Folder (⇧⌘O)",
                        systemImage: "folder.badge.plus",
                        theme: theme
                    ) {
                        if let folder = StudioFilePanels.pickFolder() {
                            Task { await store.importDirectory(url: folder) }
                        }
                    }

                    StudioVerticalHairline(theme: theme, height: 14)
                        .padding(.horizontal, 2)

                    Menu {
                        Section("IDE & Classic (VS Code / PyCharm)") {
                            ForEach([
                                StudioTheme.vscodeDarkModern,
                                StudioTheme.vscodeLightModern,
                                StudioTheme.pycharmDarcula,
                                StudioTheme.pycharmLight,
                            ]) { item in
                                themeMenuRow(item)
                            }
                        }

                        Section("Manga Studio Themes") {
                            ForEach([
                                StudioTheme.cyberNeon,
                                StudioTheme.mangaInk,
                                StudioTheme.shonenSunrise,
                                StudioTheme.sakuraTwilight,
                                StudioTheme.emeraldAlchemist,
                                StudioTheme.nordFrost,
                                StudioTheme.paperStudio,
                            ]) { item in
                                themeMenuRow(item)
                            }
                        }
                    } label: {
                        StudioHoverMenuTrigger(theme: theme, cornerRadius: 6) { isHovered in
                            HStack(spacing: 5) {
                                Circle()
                                    .fill(theme.accentPrimary)
                                    .frame(width: 7, height: 7)
                                    .scaleEffect(isHovered ? 1.18 : 1.0)
                                Text(theme.displayName)
                                    .font(.system(size: 11.5, weight: .medium))
                                    .foregroundStyle(isHovered ? theme.textPrimary : theme.textSecondary)
                                Image(systemName: "chevron.down")
                                    .font(.system(size: 8.5, weight: .semibold))
                                    .foregroundStyle(isHovered ? theme.accentPrimary : theme.textMuted)
                                    .offset(y: isHovered ? 1 : 0)
                            }
                            .padding(.horizontal, 8)
                            .frame(height: 24)
                        }
                    }
                    .menuStyle(.button)
                    .buttonStyle(.plain)
                    .menuIndicator(.hidden)
                    .fixedSize()
                    .help("Switch Studio Theme")

                    StudioVerticalHairline(theme: theme, height: 14)
                        .padding(.horizontal, 2)

                    StudioToolbarIconButton(
                        title: "Exemplar Gallery & LoRA Studio",
                        systemImage: "brain.head.profile",
                        isDisabled: store.activeSession == nil,
                        theme: theme
                    ) {
                        store.showExemplarSheet = true
                    }

                    StudioToolbarIconButton(
                        title: "Session History & Library",
                        systemImage: "clock.arrow.circlepath",
                        theme: theme
                    ) {
                        store.showHistorySheet = true
                    }

                    if !store.isFullscreenComparator {
                        StudioToolbarIconButton(
                            title: "Toggle Studio Inspector",
                            systemImage: "sidebar.right",
                            isActive: store.isInspectorVisible,
                            theme: theme
                        ) {
                            withAnimation(.spring(response: 0.28, dampingFraction: 0.84)) {
                                store.isInspectorVisible.toggle()
                            }
                        }
                    }
                }
                .studioHeaderInteractiveControl()
            }
        }
        .padding(.horizontal, 8)
        .frame(height: 36)
        .background(StudioWindowHeaderSurface())
        .background(theme.bgDark)
    }

    private var navigationSubtitleText: String {
        if let active = store.activeSession {
            return "\(active.processedCount)/\(active.totalPages) pages colorized"
        }
        if !store.sessions.isEmpty {
            let totalPages = store.sessions.reduce(0) { $0 + $1.totalPages }
            return "\(store.sessions.count) volume\(store.sessions.count == 1 ? "" : "s") queued · \(totalPages) pages"
        }
        return ""
    }

    private func centerWorkspace(theme: StudioTheme) -> some View {
        VStack(spacing: 6) {
            StudioPaneContainer(theme: theme, background: theme.bgDark, cornerRadius: 10) {
                VStack(spacing: 0) {
                    if store.isColorizing || store.isImporting || store.isTrainingAdapter || store.isExporting {
                        liveActivityBanner(theme: theme)
                        StudioHairline(theme: theme)
                    }

                    if let err = store.errorMessage, !err.isEmpty {
                        feedbackBanner(
                            text: err,
                            isError: true,
                            theme: theme,
                            onRetry: { Task { await store.restartBackend() } },
                            onDismiss: { store.dismissError() }
                        )
                        StudioHairline(theme: theme)
                    } else if let toast = store.statusBannerMessage, !toast.isEmpty {
                        feedbackBanner(
                            text: toast,
                            isError: false,
                            theme: theme,
                            onRetry: nil,
                            onDismiss: { store.dismissStatusBanner() }
                        )
                        StudioHairline(theme: theme)
                    }

                    SplitComparatorCanvasView(store: store)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            if !store.isFullscreenComparator {
                StudioPaneContainer(theme: theme, background: theme.bgHeader, cornerRadius: 10) {
                    PageGalleryGridView(store: store)
                }
            }
        }
    }

    private func liveActivityBanner(theme: StudioTheme) -> some View {
        let info = activeJobProgressInfo()
        return HStack(spacing: 12) {
            ProgressView()
                .controlSize(.small)

            VStack(alignment: .leading, spacing: 3) {
                HStack {
                    Text(info.title)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(theme.textPrimary)
                    Spacer()
                    Text(info.counter)
                        .font(.caption.weight(.bold))
                        .monospacedDigit()
                        .foregroundStyle(theme.accentPrimary)
                }
                ProgressView(value: info.fraction)
                    .tint(theme.accentPrimary)
            }

            if store.isColorizing {
                Button("Cancel") {
                    Task { await store.cancelColorization() }
                }
                .studioButtonStyle(.destructive, theme: theme, size: .small)
            } else if store.isTrainingAdapter {
                Button("Cancel") {
                    Task { await store.cancelAdapterTraining() }
                }
                .studioButtonStyle(.destructive, theme: theme, size: .small)
            } else if store.isExporting && store.combinedExportJob != nil {
                Button("Cancel") {
                    Task { await store.cancelCombinedOmnibusExport() }
                }
                .studioButtonStyle(.destructive, theme: theme, size: .small)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .background(theme.bgHeader)
    }

    private func feedbackBanner(
        text: String,
        isError: Bool,
        theme: StudioTheme,
        onRetry: (() -> Void)?,
        onDismiss: @escaping () -> Void
    ) -> some View {
        HStack(spacing: 10) {
            Image(systemName: isError ? "exclamationmark.octagon.fill" : "checkmark.circle.fill")
                .foregroundStyle(isError ? .red : theme.accentGreen)
            Text(text)
                .font(.caption)
                .foregroundStyle(theme.textPrimary)
                .lineLimit(2)
            Spacer()
            if isError, let onRetry, !store.backendState.isRunning {
                Button("Restart Engine", action: onRetry)
                    .studioButtonStyle(.secondary, theme: theme, size: .small)
            }
            Button(action: onDismiss) {
                Image(systemName: "xmark")
                    .font(.caption)
            }
            .buttonStyle(StudioInlineIconButtonStyle(theme: theme, tint: theme.textMuted))
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 7)
        .background((isError ? Color.red : theme.accentGreen).opacity(0.14))
    }

    private func dropOverlay(theme: StudioTheme) -> some View {
        RoundedRectangle(cornerRadius: 16, style: .continuous)
            .strokeBorder(theme.accentPrimary, style: StrokeStyle(lineWidth: 3, dash: [10, 6]))
            .background(theme.accentPrimary.opacity(0.12), in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay {
                VStack(spacing: 10) {
                    Image(systemName: "arrow.down.doc.fill")
                        .font(.system(size: 44))
                        .foregroundStyle(theme.accentPrimary)
                    Text("Drop Manga Volumes, Images, or Folders")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(theme.textPrimary)
                }
            }
            .padding(20)
            .allowsHitTesting(false)
    }

    private func activeJobProgressInfo() -> (title: String, counter: String, fraction: Double) {
        if store.isImporting {
            return (
                store.importProgressText.isEmpty ? "Importing Manga Files…" : store.importProgressText,
                "Importing",
                0.5
            )
        }
        if store.isTrainingAdapter, let adapter = store.adapterStatus {
            let pct = Int((adapter.progress ?? 0).rounded())
            return (
                "Training Series LoRA Adapter (\(adapter.seriesKey))",
                "Step \(adapter.step ?? 0)/\(adapter.totalSteps ?? 100) · \(pct)%",
                min(1, max(0, (adapter.progress ?? 0) / 100.0))
            )
        }
        if store.isExporting {
            return (
                store.combinedExportStatusText.isEmpty ? "Exporting Manga Package…" : store.combinedExportStatusText,
                "\(store.combinedExportPercent)%",
                min(1, max(0, Double(store.combinedExportPercent) / 100.0))
            )
        }
        let processed = store.activeSession?.processedCount ?? 0
        let total = max(1, store.activeSession?.totalPages ?? 1)
        let pct = Int(((Double(processed) / Double(total)) * 100).rounded())
        return (
            store.colorizeProgressMessage.isEmpty ? "Colorizing Manga Volume…" : store.colorizeProgressMessage,
            "\(processed)/\(total) (\(pct)%)",
            min(1, max(0, Double(processed) / Double(total)))
        )
    }

    private func handleDrop(providers: [NSItemProvider]) -> Bool {
        let group = DispatchGroup()
        let lock = NSLock()
        var urls: [URL] = []

        for provider in providers where provider.hasItemConformingToTypeIdentifier(UTType.fileURL.identifier) {
            group.enter()
            provider.loadItem(forTypeIdentifier: UTType.fileURL.identifier, options: nil) { item, _ in
                defer { group.leave() }
                if let data = item as? Data, let url = URL(dataRepresentation: data, relativeTo: nil) {
                    lock.lock()
                    urls.append(url)
                    lock.unlock()
                } else if let url = item as? URL {
                    lock.lock()
                    urls.append(url)
                    lock.unlock()
                }
            }
        }

        group.notify(queue: .main) {
            let dropped = urls
            if !dropped.isEmpty {
                Task { await store.handleDroppedOrPickedURLs(dropped) }
            }
        }
        return !providers.isEmpty
    }

    @ViewBuilder
    private func themeMenuRow(_ item: StudioTheme) -> some View {
        Button {
            store.setTheme(item.id)
        } label: {
            HStack {
                Image(nsImage: themeDotImage(hex: item.accentPrimaryHex))
                Text("\(item.displayName) (\(item.isLightTheme ? "Light" : "Dark"))")
                if item.id == store.activeThemeID {
                    Image(systemName: "checkmark")
                }
            }
        }
    }

    private func themeDotImage(hex: String) -> NSImage {
        let size = NSSize(width: 10, height: 10)
        let image = NSImage(size: size)
        image.lockFocus()
        let nsColor = NSColor(Color(studioHex: hex))
        nsColor.setFill()
        NSBezierPath(ovalIn: NSRect(origin: .zero, size: size)).fill()
        image.unlockFocus()
        return image
    }
}
