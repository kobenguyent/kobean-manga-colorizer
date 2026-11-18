import KobeanMangaCore
import SwiftUI

struct PageGalleryGridView: View {
    @Bindable var store: StudioStore
    @State private var isExpanded: Bool = true
    @State private var galleryHeight: CGFloat = 196
    @State private var dragStartHeight: CGFloat?

    private let columns = [
        GridItem(.adaptive(minimum: 112, maximum: 148), spacing: 10)
    ]

    var body: some View {
        let theme = store.currentTheme

        VStack(spacing: 0) {
            if store.activeSession == nil {
                collapsedNoSessionBar(theme: theme)
            } else {
                if isExpanded {
                    resizeHandleBar(theme: theme)
                    StudioHairline(theme: theme)
                }

                toolbarHeader(theme: theme)

                if isExpanded {
                    StudioHairline(theme: theme)

                    if store.filteredPages.isEmpty {
                        emptyFilteredState(theme: theme)
                    } else {
                        ScrollView {
                            LazyVGrid(columns: columns, spacing: 10) {
                                ForEach(store.filteredPages) { page in
                                    PageGalleryTile(
                                        page: page,
                                        isCurrent: page.index == store.activePageIndex,
                                        isSelected: store.selectedPageIndices.contains(page.index),
                                        imageURL: store.colorizedImageURL(for: page) ?? store.originalImageURL(for: page),
                                        theme: theme,
                                        onInspect: {
                                            store.selectPage(at: page.index)
                                        },
                                        onToggleSelect: {
                                            store.togglePageSelection(page.index)
                                        },
                                        onPreview: {
                                            store.selectPage(at: page.index)
                                            Task { await store.previewCurrentPage() }
                                        },
                                        onRecolorize: {
                                            store.selectedPageIndices = [page.index]
                                            Task { await store.startColorization(forceRecolorize: true) }
                                        },
                                        onTranslate: {
                                            store.selectPage(at: page.index)
                                            Task { await store.translateCurrentPage() }
                                        },
                                        onLearn: {
                                            store.selectPage(at: page.index)
                                            Task { await store.learnCurrentPage() }
                                        },
                                        onDelete: {
                                            Task { await store.deletePage(at: page.index) }
                                        }
                                    )
                                }
                            }
                            .padding(12)
                        }
                        .frame(height: galleryHeight)
                    }
                }
            }
        }
        .background(theme.bgCardSubtle)
    }

    private func collapsedNoSessionBar(theme: StudioTheme) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "square.grid.2x2")
                .font(.caption)
                .foregroundStyle(theme.textMuted)
            Text("Page Gallery (0) — Load a volume to inspect pages")
                .font(.caption.weight(.medium))
                .monospacedDigit()
                .foregroundStyle(theme.textSecondary)
            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(theme.bgHeader)
    }

    private func resizeHandleBar(theme: StudioTheme) -> some View {
        ZStack {
            Capsule()
                .fill(theme.textMuted.opacity(0.45))
                .frame(width: 38, height: 4)
        }
        .frame(maxWidth: .infinity)
        .frame(height: 10)
        .background(theme.bgHeader)
        .contentShape(Rectangle())
        .gesture(
            DragGesture(minimumDistance: 1)
                .onChanged { value in
                    if dragStartHeight == nil {
                        dragStartHeight = galleryHeight
                    }
                    let base = dragStartHeight ?? galleryHeight
                    let updated = base - value.translation.height
                    galleryHeight = min(360, max(136, updated))
                }
                .onEnded { _ in
                    dragStartHeight = nil
                }
        )
        .help("Drag to resize Page Gallery")
    }

    private func toolbarHeader(theme: StudioTheme) -> some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 10) {
                galleryTitleAndFilter(theme: theme)
                Spacer(minLength: 8)
                galleryActionsCluster(theme: theme)
            }

            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 8) {
                    galleryTitleAndFilter(theme: theme)
                    Spacer(minLength: 0)
                }
                HStack(spacing: 6) {
                    Spacer(minLength: 0)
                    galleryActionsCluster(theme: theme)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(theme.bgHeader)
    }

    private func galleryTitleAndFilter(theme: StudioTheme) -> some View {
        HStack(spacing: 10) {
            Button {
                withAnimation(.spring(response: 0.26, dampingFraction: 0.82)) {
                    isExpanded.toggle()
                }
            } label: {
                Label(
                    "Page Gallery (\(store.activeSession?.pages.count ?? 0))",
                    systemImage: isExpanded ? "chevron.down" : "chevron.right"
                )
                .font(.subheadline.weight(.semibold))
                .monospacedDigit()
                .foregroundStyle(theme.textPrimary)
            }
            .buttonStyle(.plain)

            StudioSegmentedControl(
                items: [
                    (.all, "All", nil),
                    (.colorized, "Colorized", nil),
                    (.uncolorized, "Pending", nil),
                    (.translated, "Translated", nil),
                ],
                selection: $store.pageGalleryFilter,
                theme: theme
            )

            if isExpanded {
                Button {
                    withAnimation(.easeInOut(duration: 0.15)) {
                        galleryHeight = galleryHeight > 240 ? 180 : 280
                    }
                } label: {
                    Image(systemName: galleryHeight > 240 ? "arrow.down.right.and.arrow.up.left" : "arrow.up.left.and.arrow.down.right")
                        .font(.caption2)
                        .foregroundStyle(theme.textSecondary)
                        .padding(5)
                        .background(theme.bgInput, in: RoundedRectangle(cornerRadius: 6, style: .continuous))
                }
                .buttonStyle(.plain)
                .help("Toggle Compact / Tall Gallery")
            }
        }
    }

    private func galleryActionsCluster(theme: StudioTheme) -> some View {
        HStack(spacing: 6) {
            Button("Select All") { store.selectAllPages() }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(store.activeSession?.pages.isEmpty ?? true)

            Button("Uncolorized") { store.selectUncolorizedPages() }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(store.activeSession?.pages.isEmpty ?? true)

            Button("Clear") { store.deselectAllPages() }
                .buttonStyle(.bordered)
                .controlSize(.small)
                .disabled(store.selectedPageIndices.isEmpty)

            Button {
                Task { await store.startColorization(forceRecolorize: false) }
            } label: {
                Label("Colorize (\(store.selectedPageIndices.count))", systemImage: "wand.and.stars")
                    .monospacedDigit()
            }
            .buttonStyle(.borderedProminent)
            .tint(theme.accentPrimary)
            .controlSize(.small)
            .disabled(!store.canStartColorize)

            Button {
                Task { await store.translateSelectedOrAllPages() }
            } label: {
                Label("Translate (\(store.selectedPageIndices.count))", systemImage: "character.bubble")
                    .monospacedDigit()
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .disabled(store.selectedPageIndices.isEmpty || store.isTranslating || store.isColorizing)
        }
    }

    private func emptyFilteredState(theme: StudioTheme) -> some View {
        HStack {
            Spacer()
            Text("No pages match the selected filter.")
                .font(.caption)
                .foregroundStyle(theme.textMuted)
            Spacer()
        }
        .frame(height: 88)
    }
}

private struct PageGalleryTile: View {
    let page: MangaPageInfo
    let isCurrent: Bool
    let isSelected: Bool
    let imageURL: URL?
    let theme: StudioTheme
    let onInspect: () -> Void
    let onToggleSelect: () -> Void
    let onPreview: () -> Void
    let onRecolorize: () -> Void
    let onTranslate: () -> Void
    let onLearn: () -> Void
    let onDelete: () -> Void

    @State private var isHovered: Bool = false

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 10, style: .continuous)
        VStack(spacing: 6) {
            ZStack(alignment: .topLeading) {
                StudioRemoteImageView(
                    url: imageURL,
                    placeholderText: "Page \(page.index + 1)",
                    theme: theme,
                    contentMode: .fill,
                    maxPixelDimension: 240
                )
                .frame(height: 118)
                .frame(maxWidth: .infinity)
                .clipped()
                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))

                HStack {
                    Button(action: onToggleSelect) {
                        Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                            .font(.callout)
                            .foregroundStyle(isSelected ? theme.accentPrimary : .white)
                            .shadow(color: .black.opacity(0.6), radius: 2)
                    }
                    .buttonStyle(.plain)

                    Spacer()

                    if let q = page.qualityScore {
                        Text("\(Int((q.overall * 100).rounded()))%")
                            .font(.caption2.weight(.bold))
                            .monospacedDigit()
                            .foregroundStyle(.white)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(Color.black.opacity(0.65), in: Capsule())
                    }
                }
                .padding(6)
            }

            HStack(spacing: 4) {
                Circle()
                    .fill(statusDotColor)
                    .frame(width: 7, height: 7)
                Text("P\(page.index + 1)")
                    .font(.caption2.weight(.semibold))
                    .monospacedDigit()
                    .foregroundStyle(theme.textPrimary)
                Spacer()
                if page.skippedColored {
                    Text("Orig")
                        .font(.caption2)
                        .foregroundStyle(theme.accentPrimary)
                } else if page.translated {
                    Image(systemName: "captions.bubble.fill")
                        .font(.caption2)
                        .foregroundStyle(theme.accentGreen)
                }
            }
            .padding(.horizontal, 4)
        }
        .padding(6)
        .background {
            ZStack {
                shape.fill(isCurrent ? theme.accentPrimary.opacity(0.16) : theme.bgCard)
                shape.fill(
                    LinearGradient(
                        colors: [
                            Color.white.opacity(
                                isCurrent
                                    ? (theme.isLightTheme ? 0.45 : 0.09)
                                    : (isHovered ? (theme.isLightTheme ? 0.35 : 0.06) : 0.02)
                            ),
                            Color.clear,
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
            }
        }
        .overlay(
            shape.strokeBorder(
                LinearGradient(
                    colors: [
                        isCurrent
                            ? theme.accentPrimary
                            : (isHovered ? theme.accentPrimary.opacity(0.55) : Color.white.opacity(theme.isLightTheme ? 0.7 : 0.12)),
                        isCurrent ? theme.accentPrimary.opacity(0.5) : theme.bgCardBorder,
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ),
                lineWidth: isCurrent ? 1.5 : 0.9
            )
        )
        .shadow(
            color: isCurrent
                ? theme.accentPrimary.opacity(0.22)
                : Color.black.opacity(isHovered ? 0.22 : 0.10),
            radius: isHovered || isCurrent ? 8 : 3,
            y: isHovered || isCurrent ? 3 : 1
        )
        .scaleEffect(isHovered ? 1.025 : 1.0)
        .animation(.spring(response: 0.22, dampingFraction: 0.78), value: isHovered)
        .animation(.spring(response: 0.24, dampingFraction: 0.80), value: isCurrent)
        .contentShape(shape)
        .onHover { hovering in
            isHovered = hovering
        }
        .onTapGesture(perform: onInspect)
        .contextMenu {
            Button("Inspect in Comparator", action: onInspect)
            Button("Preview Page", action: onPreview)
            Button("Recolorize Page", action: onRecolorize)
            Button("Translate Page", action: onTranslate)
            if page.isColorized {
                Button("Learn Page to Series Memory", action: onLearn)
            }
            Divider()
            Button("Delete Page", role: .destructive, action: onDelete)
        }
    }

    private var statusDotColor: Color {
        switch page.status {
        case "colorized": return theme.accentGreen
        case "processing": return theme.accentYellow
        case "error": return .red
        default: return theme.textMuted
        }
    }
}
