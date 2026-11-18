import KobeanMangaCore
import SwiftUI

struct SplitComparatorCanvasView: View {
    @Bindable var store: StudioStore
    @State private var showQualityPopover: Bool = false
    @State private var dragBaseOffset: CGSize = .zero
    @State private var gestureBaseZoom: Double = 1.0
    @State private var isHoveringSplitHandle: Bool = false
    @State private var isDraggingSplitHandle: Bool = false
    @State private var isWelcomeLogoHovered: Bool = false

    var body: some View {
        let theme = store.currentTheme

        VStack(spacing: 0) {
            if store.activeSession != nil {
                comparatorHeaderBar(theme: theme)
                StudioHairline(theme: theme)

                if let page = store.currentPage {
                    statusChipsBar(page: page, theme: theme)
                    StudioHairline(theme: theme)
                }

                HStack(spacing: 0) {
                    if store.showThumbnailStrip, let pages = store.activeSession?.pages, !pages.isEmpty {
                        thumbnailRail(pages: pages, theme: theme)
                        StudioVerticalHairline(theme: theme, height: nil)
                    }

                    comparatorCanvas(theme: theme)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)

                StudioHairline(theme: theme)
                bottomStepperBar(theme: theme)
            } else {
                welcomeEmptyWorkspace(theme: theme)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(theme.bgDark)
    }

    // MARK: - Header Bar (Responsive via ViewThatFits)

    private func comparatorHeaderBar(theme: StudioTheme) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 10) {
                leftControlsCluster(theme: theme)
                Spacer(minLength: 8)
                compactStepperPill(theme: theme)
                pageActionsCluster(theme: theme)
            }

            VStack(spacing: 8) {
                HStack(spacing: 8) {
                    leftControlsCluster(theme: theme)
                    Spacer(minLength: 8)
                    compactStepperPill(theme: theme)
                }
                HStack(spacing: 8) {
                    Spacer(minLength: 0)
                    pageActionsCluster(theme: theme)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(theme.bgHeader)
    }

    private func leftControlsCluster(theme: StudioTheme) -> some View {
        HStack(spacing: 8) {
            StudioSegmentedControl(
                items: [
                    (.split, "Split", "square.split.2x1"),
                    (.originalOnly, "B&W", "doc.richtext"),
                    (.colorizedOnly, "Color", "paintpalette.fill"),
                ],
                selection: $store.comparatorMode,
                theme: theme
            )

            StudioVerticalHairline(theme: theme, height: 18)

            HStack(spacing: 2) {
                Button {
                    store.zoomOut()
                } label: {
                    Image(systemName: "minus.magnifyingglass")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 6)
                .padding(.vertical, 4)
                .help("Zoom Out (⌘-)")

                Menu {
                    ForEach([0.5, 0.75, 1.0, 1.5, 2.0, 3.0], id: \.self) { level in
                        Button("\(Int(level * 100))%") {
                            store.setZoomScale(level)
                        }
                    }
                    Divider()
                    Button("Reset 100%") { store.resetZoom() }
                } label: {
                    Text("\(Int((store.zoomScale * 100).rounded()))%")
                        .font(.caption.weight(.semibold))
                        .monospacedDigit()
                        .foregroundStyle(theme.textPrimary)
                        .frame(minWidth: 42)
                }
                .menuStyle(.button)
                .buttonStyle(.plain)
                .menuIndicator(.hidden)

                Button {
                    store.zoomIn()
                } label: {
                    Image(systemName: "plus.magnifyingglass")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .padding(.horizontal, 6)
                .padding(.vertical, 4)
                .help("Zoom In (⌘+)")
            }
            .background(theme.bgInput, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .strokeBorder(theme.bgCardBorder, lineWidth: 1)
            )

            Button {
                store.toggleThumbnailStrip()
            } label: {
                Image(systemName: "sidebar.left")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(store.showThumbnailStrip ? theme.accentPrimary : theme.textSecondary)
                    .padding(6)
                    .background(
                        store.showThumbnailStrip ? theme.accentPrimary.opacity(0.16) : theme.bgInput,
                        in: RoundedRectangle(cornerRadius: 7, style: .continuous)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .strokeBorder(store.showThumbnailStrip ? theme.accentPrimary.opacity(0.6) : theme.bgCardBorder, lineWidth: 1)
                    )
            }
            .buttonStyle(.plain)
            .help("Toggle Thumbnail Rail (⌃⌘T)")

            Button {
                store.toggleFullscreenComparator()
            } label: {
                Image(systemName: store.isFullscreenComparator ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(store.isFullscreenComparator ? theme.accentPrimary : theme.textSecondary)
                    .padding(6)
                    .background(
                        store.isFullscreenComparator ? theme.accentPrimary.opacity(0.16) : theme.bgInput,
                        in: RoundedRectangle(cornerRadius: 7, style: .continuous)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 7, style: .continuous)
                            .strokeBorder(store.isFullscreenComparator ? theme.accentPrimary.opacity(0.6) : theme.bgCardBorder, lineWidth: 1)
                    )
            }
            .buttonStyle(.plain)
            .help("Toggle Fullscreen Comparator (⌃⌘F)")
        }
    }

    private func compactStepperPill(theme: StudioTheme) -> some View {
        let total = store.activeSession?.pages.count ?? 0
        return HStack(spacing: 4) {
            Button {
                store.previousPage()
            } label: {
                Image(systemName: "chevron.left")
                    .font(.caption.weight(.semibold))
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 6)
            .padding(.vertical, 4)
            .disabled(store.activePageIndex <= 0)

            Text(total > 0 ? "Page \(store.activePageIndex + 1)/\(total)" : "0/0")
                .font(.caption.weight(.semibold))
                .monospacedDigit()
                .foregroundStyle(theme.textPrimary)

            Button {
                store.nextPage()
            } label: {
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
            }
            .buttonStyle(.plain)
            .padding(.horizontal, 6)
            .padding(.vertical, 4)
            .disabled(store.activePageIndex + 1 >= total)
        }
        .background(theme.bgInput, in: Capsule())
        .overlay(
            Capsule().strokeBorder(theme.bgCardBorder, lineWidth: 1)
        )
    }

    @ViewBuilder
    private func pageActionsCluster(theme: StudioTheme) -> some View {
        if store.currentPage != nil {
            HStack(spacing: 6) {
                Button {
                    Task { await store.previewCurrentPage() }
                } label: {
                    Label(store.isPreviewing ? "Previewing…" : "Preview", systemImage: "sparkles")
                }
                .buttonStyle(.borderedProminent)
                .tint(theme.accentPrimary)
                .controlSize(.small)
                .disabled(store.isPreviewing || store.isColorizing)

                Button {
                    Task {
                        if let idx = store.currentPage?.index {
                            store.selectedPageIndices = [idx]
                            await store.startColorization(forceRecolorize: true)
                        }
                    }
                } label: {
                    Label("Recolorize", systemImage: "arrow.triangle.2.circlepath")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(store.isColorizing)

                Button {
                    Task { await store.translateCurrentPage() }
                } label: {
                    Label(store.isTranslating ? "Translating…" : "Translate", systemImage: "character.bubble")
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(store.isTranslating)

                Button {
                    Task { await store.learnCurrentPage() }
                } label: {
                    Label("Learn", systemImage: "brain")
                }
                .buttonStyle(.bordered)
                .tint(theme.accentSecondary)
                .controlSize(.small)
                .disabled(store.currentPage?.isColorized != true)
            }
        }
    }

    // MARK: - Status Chips Bar

    private func statusChipsBar(page: MangaPageInfo, theme: StudioTheme) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                if let q = page.qualityScore {
                    Button {
                        showQualityPopover.toggle()
                    } label: {
                        StudioBadgePill(
                            text: "Quality \(Int((q.overall * 100).rounded()))%",
                            systemImage: q.autoLearnEligible ? "checkmark.seal.fill" : "chart.bar.fill",
                            foreground: q.autoLearnEligible ? theme.accentGreen : theme.accentYellow,
                            background: (q.autoLearnEligible ? theme.accentGreen : theme.accentYellow).opacity(0.14),
                            border: (q.autoLearnEligible ? theme.accentGreen : theme.accentYellow).opacity(0.35)
                        )
                    }
                    .buttonStyle(.plain)
                    .popover(isPresented: $showQualityPopover, arrowEdge: .bottom) {
                        QualityBreakdownPopover(score: q, theme: theme)
                    }
                }

                if let ex = page.exemplarUsed, !ex.isEmpty {
                    StudioBadgePill(
                        text: "Exemplar: \(ex)",
                        systemImage: "photo.stack",
                        foreground: theme.accentPrimary,
                        background: theme.accentPrimary.opacity(0.12),
                        border: theme.accentPrimary.opacity(0.3)
                    )
                }

                if page.adapterUsed {
                    StudioBadgePill(
                        text: "Series LoRA Active",
                        systemImage: "cpu",
                        foreground: theme.accentSecondary,
                        background: theme.accentSecondary.opacity(0.14),
                        border: theme.accentSecondary.opacity(0.35)
                    )
                }

                if page.translated {
                    StudioBadgePill(
                        text: "\(page.translations.count) Bubble\(page.translations.count == 1 ? "" : "s") Translated",
                        systemImage: "captions.bubble.fill",
                        foreground: theme.accentGreen,
                        background: theme.accentGreen.opacity(0.14),
                        border: theme.accentGreen.opacity(0.35)
                    )
                }

                ForEach(page.recognizedCharacters) { char in
                    StudioBadgePill(
                        text: "\(char.name) \(Int((char.confidence * 100).rounded()))%",
                        systemImage: "person.crop.circle",
                        foreground: theme.textPrimary,
                        background: theme.bgCard,
                        border: theme.bgCardBorder
                    )
                }
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
        }
        .background(theme.bgCardSubtle)
    }

    // MARK: - Thumbnail Rail

    private func thumbnailRail(pages: [MangaPageInfo], theme: StudioTheme) -> some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 8) {
                    ForEach(pages) { page in
                        let isCurrent = page.index == store.activePageIndex
                        Button {
                            store.selectPage(at: page.index)
                        } label: {
                            VStack(spacing: 4) {
                                StudioRemoteImageView(
                                    url: store.colorizedImageURL(for: page) ?? store.originalImageURL(for: page),
                                    placeholderText: "P\(page.index + 1)",
                                    theme: theme,
                                    contentMode: .fill,
                                    maxPixelDimension: 180
                                )
                                .frame(width: 68, height: 92)
                                .clipped()
                                .clipShape(RoundedRectangle(cornerRadius: 6, style: .continuous))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 6, style: .continuous)
                                        .strokeBorder(isCurrent ? theme.accentPrimary : theme.bgCardBorder, lineWidth: isCurrent ? 2 : 1)
                                )

                                HStack(spacing: 3) {
                                    Circle()
                                        .fill(page.isColorized ? theme.accentGreen : theme.textMuted)
                                        .frame(width: 6, height: 6)
                                    Text("\(page.index + 1)")
                                        .font(.caption2.weight(isCurrent ? .bold : .regular))
                                        .monospacedDigit()
                                        .foregroundStyle(isCurrent ? theme.accentPrimary : theme.textSecondary)
                                }
                            }
                            .padding(4)
                            .background(
                                isCurrent ? theme.accentPrimary.opacity(0.12) : Color.clear,
                                in: RoundedRectangle(cornerRadius: 8, style: .continuous)
                            )
                        }
                        .buttonStyle(.plain)
                        .id(page.index)
                    }
                }
                .padding(8)
            }
            .frame(width: 92)
            .background(theme.bgCardSubtle)
            .onChange(of: store.activePageIndex) { _, newIdx in
                withAnimation(.easeInOut(duration: 0.2)) {
                    proxy.scrollTo(newIdx, anchor: .center)
                }
            }
        }
    }

    // MARK: - Interactive Split Canvas

    private func comparatorCanvas(theme: StudioTheme) -> some View {
        GeometryReader { geo in
            ZStack {
                theme.bgDark

                if let page = store.currentPage {
                    let origURL = store.originalImageURL(for: page)
                    let colorURL = store.colorizedImageURL(for: page)

                    ZStack {
                        switch store.comparatorMode {
                        case .originalOnly:
                            StudioRemoteImageView(
                                url: origURL,
                                placeholderText: "Original monochrome page",
                                theme: theme
                            )
                        case .colorizedOnly:
                            if let colorURL {
                                StudioRemoteImageView(
                                    url: colorURL,
                                    placeholderText: "Colorized page",
                                    theme: theme
                                )
                            } else {
                                StudioRemoteImageView(
                                    url: origURL,
                                    placeholderText: "Not yet colorized — click Preview or Start Colorize",
                                    theme: theme
                                )
                            }
                        case .split:
                            splitComparisonLayers(
                                width: geo.size.width,
                                height: geo.size.height,
                                origURL: origURL,
                                colorURL: colorURL,
                                theme: theme
                            )
                        }
                    }
                    .frame(width: geo.size.width, height: geo.size.height)
                    .scaleEffect(store.zoomScale)
                    .offset(store.panOffset)
                    .gesture(
                        MagnificationGesture()
                            .onChanged { value in
                                store.setZoomScale(gestureBaseZoom * value)
                            }
                            .onEnded { _ in
                                gestureBaseZoom = store.zoomScale
                            }
                    )
                    .simultaneousGesture(
                        DragGesture()
                            .onChanged { value in
                                guard store.zoomScale > 1.01 else { return }
                                store.panOffset = CGSize(
                                    width: dragBaseOffset.width + value.translation.width,
                                    height: dragBaseOffset.height + value.translation.height
                                )
                            }
                            .onEnded { _ in
                                dragBaseOffset = store.panOffset
                            }
                    )
                    .onTapGesture(count: 2) {
                        store.toggleDoubleClickZoom()
                        gestureBaseZoom = store.zoomScale
                        dragBaseOffset = store.panOffset
                    }

                    if store.comparatorMode == .split && colorURL != nil {
                        splitComparisonCornerPills(theme: theme)
                        splitDividerOverlay(width: geo.size.width, height: geo.size.height, theme: theme)
                    }
                }
            }
            .clipped()
        }
        .focusable()
        .focusEffectDisabled()
        .onKeyPress(.leftArrow) {
            store.previousPage()
            return .handled
        }
        .onKeyPress(.rightArrow) {
            store.nextPage()
            return .handled
        }
    }

    private func splitComparisonLayers(
        width: CGFloat,
        height: CGFloat,
        origURL: URL?,
        colorURL: URL?,
        theme: StudioTheme
    ) -> some View {
        ZStack {
            StudioRemoteImageView(
                url: origURL,
                placeholderText: "Loading original page…",
                theme: theme
            )
            .frame(width: width, height: height)

            if let colorURL {
                let revealWidth = max(0, width * store.splitRatio)
                StudioRemoteImageView(
                    url: colorURL,
                    placeholderText: "Loading colorized page…",
                    theme: theme
                )
                .frame(width: width, height: height)
                .mask(
                    HStack(spacing: 0) {
                        Rectangle().frame(width: revealWidth)
                        Spacer(minLength: 0)
                    }
                )
            }
        }
    }

    private func splitComparisonCornerPills(theme: StudioTheme) -> some View {
        VStack {
            HStack {
                StudioBadgePill(
                    text: "COLORIZED",
                    systemImage: "sparkles",
                    foreground: theme.accentPrimary,
                    background: theme.bgHeader.opacity(0.92),
                    border: theme.accentPrimary.opacity(0.45)
                )
                Spacer()
                StudioBadgePill(
                    text: "ORIGINAL B&W",
                    systemImage: "doc.richtext",
                    foreground: theme.textSecondary,
                    background: theme.bgHeader.opacity(0.92),
                    border: theme.bgCardBorder
                )
            }
            .padding(12)
            Spacer()
        }
        .allowsHitTesting(false)
    }

    private func splitDividerOverlay(width: CGFloat, height: CGFloat, theme: StudioTheme) -> some View {
        let xPos = max(12, min(width - 12, width * store.splitRatio))
        let isHighlighted = isHoveringSplitHandle || isDraggingSplitHandle
        return ZStack {
            Rectangle()
                .fill(
                    LinearGradient(
                        colors: [
                            theme.accentPrimary.opacity(0.65),
                            theme.accentPrimary,
                            theme.accentSecondary,
                            theme.accentPrimary.opacity(0.65),
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                )
                .frame(width: isHighlighted ? 2.5 : 2, height: height)
                .shadow(color: theme.accentPrimary.opacity(isHighlighted ? 0.55 : 0.30), radius: isHighlighted ? 8 : 4)

            Circle()
                .fill(.ultraThinMaterial)
                .overlay(Circle().fill(theme.bgCard.opacity(0.78)))
                .overlay(
                    Circle().fill(
                        LinearGradient(
                            colors: [Color.white.opacity(0.28), Color.clear],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                )
                .frame(width: 34, height: 34)
                .overlay(
                    Circle().strokeBorder(
                        LinearGradient(
                            colors: [theme.accentPrimary, theme.accentSecondary],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        lineWidth: isHighlighted ? 2.2 : 1.75
                    )
                )
                .overlay(
                    Image(systemName: "arrow.left.and.right")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(theme.accentPrimary)
                )
                .scaleEffect(isDraggingSplitHandle ? 1.14 : (isHoveringSplitHandle ? 1.07 : 1.0))
                .shadow(color: theme.accentPrimary.opacity(isHighlighted ? 0.45 : 0.22), radius: isHighlighted ? 10 : 5)
                .shadow(color: .black.opacity(0.35), radius: 4, y: 2)
        }
        .animation(.spring(response: 0.22, dampingFraction: 0.76), value: isHoveringSplitHandle)
        .animation(.spring(response: 0.20, dampingFraction: 0.74), value: isDraggingSplitHandle)
        .position(x: xPos, y: height / 2)
        .onHover { hovering in
            isHoveringSplitHandle = hovering
        }
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { value in
                    isDraggingSplitHandle = true
                    guard width > 0 else { return }
                    store.setSplitRatio(value.location.x / width)
                }
                .onEnded { _ in
                    isDraggingSplitHandle = false
                }
        )
    }

    // MARK: - Studio Welcome & Quick-Start Card (Empty Workspace)

    private func welcomeEmptyWorkspace(theme: StudioTheme) -> some View {
        ZStack {
            RadialGradient(
                colors: [
                    theme.accentPrimary.opacity(theme.isLightTheme ? 0.14 : 0.20),
                    theme.accentSecondary.opacity(theme.isLightTheme ? 0.08 : 0.11),
                    Color.clear
                ],
                center: .center,
                startRadius: 24,
                endRadius: 460
            )
            .ignoresSafeArea()

            StudioCardSurface(theme: theme, padding: 28) {
                VStack(spacing: 18) {
                    StudioBrandLogoView(
                        size: 86,
                        style: .appIcon,
                        showGlow: true,
                        theme: theme
                    )
                    .scaleEffect(isWelcomeLogoHovered ? 1.05 : 1.0)
                    .animation(.spring(response: 0.28, dampingFraction: 0.72), value: isWelcomeLogoHovered)
                    .onHover { hovering in
                        isWelcomeLogoHovered = hovering
                    }

                    VStack(spacing: 8) {
                        Text("Kobean Manga Colorizer Studio")
                            .font(.title2.weight(.bold))
                            .foregroundStyle(theme.textPrimary)
                            .multilineTextAlignment(.center)

                        Text("Drop or import a manga volume or folder to inspect and colorize pages.")
                            .font(.callout)
                            .foregroundStyle(theme.textSecondary)
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: 420)
                    }

                    HStack(spacing: 10) {
                        Button {
                            let urls = StudioFilePanels.pickFiles()
                            if !urls.isEmpty {
                                Task { await store.uploadFiles(urls) }
                            }
                        } label: {
                            Label("Import Manga Files… (⌘O)", systemImage: "doc.badge.plus")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(theme.accentPrimary)
                        .controlSize(.large)

                        Button {
                            if let folder = StudioFilePanels.pickFolder() {
                                Task { await store.importDirectory(url: folder) }
                            }
                        } label: {
                            Label("Import Manga Folder… (⇧⌘O)", systemImage: "folder.badge.plus")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.large)
                    }

                    Text("PDF · EPUB3 · CBZ · ZIP · PNG · JPG")
                        .font(.caption2.weight(.medium))
                        .foregroundStyle(theme.textMuted)

                    if !store.sessions.isEmpty {
                        StudioHairline(theme: theme)
                        VStack(alignment: .leading, spacing: 8) {
                            StudioFieldLabel(
                                title: "Queued Volumes — Click to Open",
                                badgeText: "\(store.sessions.count)",
                                theme: theme
                            )

                            ScrollView {
                                VStack(spacing: 6) {
                                    ForEach(store.sessions.prefix(5)) { summary in
                                        Button {
                                            Task { await store.selectSession(id: summary.sessionId) }
                                        } label: {
                                            HStack(spacing: 10) {
                                                Image(systemName: "book.closed.fill")
                                                    .foregroundStyle(theme.accentPrimary)
                                                Text(summary.filename)
                                                    .font(.callout.weight(.medium))
                                                    .foregroundStyle(theme.textPrimary)
                                                    .lineLimit(1)
                                                    .truncationMode(.middle)
                                                Spacer()
                                                Text("\(summary.processedCount)/\(summary.totalPages)")
                                                    .font(.caption.weight(.semibold))
                                                    .monospacedDigit()
                                                    .foregroundStyle(theme.textSecondary)
                                                Image(systemName: "chevron.right")
                                                    .font(.caption2)
                                                    .foregroundStyle(theme.textMuted)
                                            }
                                            .padding(.horizontal, 10)
                                            .padding(.vertical, 7)
                                            .background(theme.bgInput, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                                            .overlay(
                                                RoundedRectangle(cornerRadius: 8, style: .continuous)
                                                    .strokeBorder(theme.bgCardBorder, lineWidth: 1)
                                            )
                                        }
                                        .buttonStyle(.plain)
                                    }
                                }
                            }
                            .frame(maxHeight: 168)
                        }
                    }
                }
            }
            .frame(maxWidth: 500)
            .padding(24)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)
    }

    // MARK: - Bottom Page Stepper

    private func bottomStepperBar(theme: StudioTheme) -> some View {
        let total = store.activeSession?.pages.count ?? 0
        return HStack(spacing: 12) {
            Button {
                store.previousPage()
            } label: {
                Label("Prev", systemImage: "chevron.left")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .disabled(store.activePageIndex <= 0)

            if total > 1 {
                Slider(
                    value: Binding(
                        get: { Double(store.activePageIndex) },
                        set: { store.selectPage(at: Int($0.rounded())) }
                    ),
                    in: 0...Double(total - 1),
                    step: 1
                )
                .frame(maxWidth: 260)
                .tint(theme.accentPrimary)
            }

            Text(total > 0 ? "Page \(store.activePageIndex + 1) of \(total)" : "No pages")
                .font(.caption.weight(.semibold))
                .monospacedDigit()
                .foregroundStyle(theme.textSecondary)

            Button {
                store.nextPage()
            } label: {
                Label("Next", systemImage: "chevron.right")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .disabled(store.activePageIndex + 1 >= total)

            Spacer()

            if let engine = store.currentPage?.engineUsed, !engine.isEmpty {
                Text(engine)
                    .font(.caption2)
                    .foregroundStyle(theme.textMuted)
                    .lineLimit(1)
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(theme.bgHeader)
    }
}

private struct QualityBreakdownPopover: View {
    let score: PageQualityScore
    let theme: StudioTheme

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Page Quality Breakdown")
                    .font(.headline)
                Spacer()
                Text("\(Int((score.overall * 100).rounded()))%")
                    .font(.headline.monospacedDigit())
                    .foregroundStyle(score.autoLearnEligible ? theme.accentGreen : theme.accentYellow)
            }

            metricRow("Linework Integrity", value: score.lineworkIntegrity, color: theme.accentPrimary)
            metricRow("White Bubble Purity", value: score.whitePurity, color: theme.accentGreen)
            metricRow("Color Richness", value: score.colorRichness, color: theme.accentSecondary)

            Text(score.autoLearnEligible ? "Eligible for Series Memory auto-harvesting" : "Manual review suggested before Series Memory")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(14)
        .frame(width: 260)
    }

    private func metricRow(_ label: String, value: Double, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(label).font(.caption)
                Spacer()
                Text("\(Int((value * 100).rounded()))%")
                    .font(.caption.weight(.semibold))
                    .monospacedDigit()
            }
            ProgressView(value: min(1, max(0, value)))
                .tint(color)
        }
    }
}
