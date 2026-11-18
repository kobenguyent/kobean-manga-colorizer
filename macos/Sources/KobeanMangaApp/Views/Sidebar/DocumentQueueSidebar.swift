import KobeanMangaCore
import SwiftUI

struct DocumentQueueSidebar: View {
    @Bindable var store: StudioStore

    private var totalQueuedPages: Int {
        store.sessions.reduce(0) { $0 + $1.totalPages }
    }

    var body: some View {
        let theme = store.currentTheme

        VStack(spacing: 0) {
            headerSection(theme: theme)
            StudioHairline(theme: theme)

            if store.filteredSessions.isEmpty {
                emptyQueueState(theme: theme)
            } else {
                sessionList(theme: theme)
            }

            StudioHairline(theme: theme)
            footerBatchBar(theme: theme)
        }
        .background(theme.bgHeader)
    }

    private func headerSection(theme: StudioTheme) -> some View {
        VStack(spacing: 10) {
            HStack {
                Label("Document Queue", systemImage: "books.vertical.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(theme.textPrimary)
                Spacer()
                Text("\(store.sessions.count)")
                    .font(.caption2.weight(.bold))
                    .monospacedDigit()
                    .foregroundStyle(theme.accentPrimary)
                    .padding(.horizontal, 7)
                    .padding(.vertical, 2)
                    .background(theme.accentPrimary.opacity(0.14), in: Capsule())
            }

            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                    .font(.caption)
                    .foregroundStyle(theme.textMuted)
                TextField("Filter volumes...", text: $store.sessionSearchQuery)
                    .textFieldStyle(.plain)
                    .font(.callout)
                    .foregroundStyle(theme.textPrimary)
                if !store.sessionSearchQuery.isEmpty {
                    Button {
                        store.sessionSearchQuery = ""
                    } label: {
                        Image(systemName: "xmark.circle.fill")
                            .font(.caption)
                            .foregroundStyle(theme.textMuted)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 9)
            .padding(.vertical, 6)
            .background(theme.bgInput, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 8, style: .continuous)
                    .strokeBorder(theme.bgCardBorder, lineWidth: 0.75)
            )

            HStack(spacing: 6) {
                Button {
                    let urls = StudioFilePanels.pickFiles()
                    if !urls.isEmpty {
                        Task { await store.uploadFiles(urls) }
                    }
                } label: {
                    Label("Files", systemImage: "plus")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(theme.accentPrimary)
                .controlSize(.small)

                Button {
                    if let folder = StudioFilePanels.pickFolder() {
                        Task { await store.importDirectory(url: folder) }
                    }
                } label: {
                    Label("Folder", systemImage: "folder.badge.plus")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
        .padding(12)
        .background(theme.bgHeader)
    }

    private func emptyQueueState(theme: StudioTheme) -> some View {
        VStack {
            Spacer(minLength: 16)
            VStack(spacing: 12) {
                Image(systemName: "arrow.down.doc")
                    .font(.system(size: 28, weight: .light))
                    .foregroundStyle(theme.accentPrimary)

                Text(store.sessions.isEmpty ? "Queue Empty" : "No Matching Volumes")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(theme.textPrimary)

                Text(
                    store.sessions.isEmpty
                        ? "Drop PDF, EPUB, CBZ, ZIP or Folder"
                        : "Clear the search filter to view all queued volumes."
                )
                .font(.caption)
                .foregroundStyle(theme.textSecondary)
                .multilineTextAlignment(.center)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 24)
            .frame(maxWidth: .infinity)
            .background(
                theme.bgCardSubtle.opacity(0.65),
                in: RoundedRectangle(cornerRadius: 10, style: .continuous)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .strokeBorder(theme.bgCardBorder, lineWidth: 0.75)
            )
            .padding(.horizontal, 12)
            Spacer(minLength: 16)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func sessionList(theme: StudioTheme) -> some View {
        ScrollView {
            LazyVStack(spacing: 8) {
                ForEach(store.filteredSessions) { summary in
                    SessionRowCard(
                        summary: summary,
                        isActive: store.activeSessionId == summary.sessionId,
                        isChecked: store.selectedSessionIds.contains(summary.sessionId),
                        theme: theme,
                        onSelect: {
                            Task { await store.selectSession(id: summary.sessionId) }
                        },
                        onToggleCheck: {
                            store.toggleSessionSelection(summary.sessionId)
                        },
                        onDelete: {
                            Task { await store.deleteSession(id: summary.sessionId) }
                        }
                    )
                }
            }
            .padding(10)
        }
    }

    private func footerBatchBar(theme: StudioTheme) -> some View {
        HStack(spacing: 6) {
            Text("\(store.sessions.count) vol · \(totalQueuedPages) pages")
                .font(.caption2.weight(.medium))
                .monospacedDigit()
                .foregroundStyle(theme.textSecondary)
                .lineLimit(1)

            Spacer(minLength: 4)

            Button(store.selectedSessionIds.count == store.sessions.count && !store.sessions.isEmpty ? "None" : "All") {
                if store.selectedSessionIds.count == store.sessions.count {
                    store.deselectAllSessions()
                } else {
                    store.selectAllSessions()
                }
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .disabled(store.sessions.isEmpty)

            Button {
                Task { await store.startBatchColorization() }
            } label: {
                Label("Batch", systemImage: "play.fill")
            }
            .buttonStyle(.borderedProminent)
            .tint(theme.accentSecondary)
            .controlSize(.small)
            .disabled(store.sessions.isEmpty || store.isColorizing)

            Button(role: .destructive) {
                Task {
                    if store.selectedSessionIds.isEmpty {
                        await store.deleteAllSessions()
                    } else {
                        await store.bulkDeleteSelectedSessions()
                    }
                }
            } label: {
                Image(systemName: "trash")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
            .disabled(store.sessions.isEmpty)
            .help(store.selectedSessionIds.isEmpty ? "Clear All Queued Sessions" : "Delete Checked Sessions")
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 9)
        .background(theme.bgHeader)
    }
}

private struct SessionRowCard: View {
    let summary: MangaSessionSummary
    let isActive: Bool
    let isChecked: Bool
    let theme: StudioTheme
    let onSelect: () -> Void
    let onToggleCheck: () -> Void
    let onDelete: () -> Void

    @State private var isHovered: Bool = false

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 10, style: .continuous)
        HStack(alignment: .top, spacing: 8) {
            Button(action: onToggleCheck) {
                Image(systemName: isChecked ? "checkmark.square.fill" : "square")
                    .font(.body)
                    .foregroundStyle(isChecked ? theme.accentPrimary : theme.textMuted)
            }
            .buttonStyle(.plain)
            .padding(.top, 2)

            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(summary.filename)
                        .font(.callout.weight(.semibold))
                        .foregroundStyle(theme.textPrimary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Spacer(minLength: 4)
                    if !summary.ext.isEmpty {
                        Text(summary.ext.replacingOccurrences(of: ".", with: "").uppercased())
                            .font(.caption2.weight(.bold))
                            .foregroundStyle(theme.textSecondary)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 1)
                            .background(theme.bgInput, in: RoundedRectangle(cornerRadius: 4))
                    }
                }

                ProgressView(value: summary.progressFraction)
                    .tint(statusColor)

                HStack {
                    Text("\(summary.processedCount)/\(summary.totalPages) pages")
                        .font(.caption2)
                        .monospacedDigit()
                        .foregroundStyle(theme.textSecondary)

                    Spacer()

                    Text(statusLabel)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(statusColor)
                }

                if let presetTitle = summary.presetTitle, !presetTitle.isEmpty {
                    Text(presetTitle)
                        .font(.caption2)
                        .foregroundStyle(theme.accentPrimary)
                        .lineLimit(1)
                }
            }
        }
        .padding(10)
        .background {
            ZStack {
                shape.fill(
                    isActive
                        ? theme.accentPrimary.opacity(0.16)
                        : (isHovered ? theme.bgCard.opacity(0.95) : theme.bgCard)
                )
                shape.fill(
                    LinearGradient(
                        colors: [
                            Color.white.opacity(
                                isActive
                                    ? (theme.isLightTheme ? 0.45 : 0.08)
                                    : (isHovered ? (theme.isLightTheme ? 0.35 : 0.05) : 0.02)
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
                        isActive
                            ? theme.accentPrimary
                            : (isHovered ? theme.accentPrimary.opacity(0.45) : Color.white.opacity(theme.isLightTheme ? 0.7 : 0.12)),
                        isActive ? theme.accentPrimary.opacity(0.45) : theme.bgCardBorder,
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                ),
                lineWidth: isActive ? 1.25 : 0.85
            )
        )
        .shadow(
            color: isActive
                ? theme.accentPrimary.opacity(0.18)
                : Color.black.opacity(isHovered ? 0.18 : 0.08),
            radius: isHovered || isActive ? 7 : 3,
            y: isHovered || isActive ? 2 : 1
        )
        .scaleEffect(isHovered ? 1.01 : 1.0)
        .animation(.spring(response: 0.22, dampingFraction: 0.80), value: isHovered)
        .animation(.spring(response: 0.24, dampingFraction: 0.82), value: isActive)
        .contentShape(shape)
        .onHover { hovering in
            isHovered = hovering
        }
        .onTapGesture(perform: onSelect)
        .contextMenu {
            Button("Open in Studio", action: onSelect)
            Button(isChecked ? "Uncheck from Batch" : "Include in Batch", action: onToggleCheck)
            Divider()
            Button("Delete Session", role: .destructive, action: onDelete)
        }
    }

    private var statusLabel: String {
        if summary.isActive || summary.status == "processing" {
            return "Processing"
        }
        if summary.status == "completed" || (summary.totalPages > 0 && summary.processedCount >= summary.totalPages) {
            return "Completed"
        }
        if summary.processedCount > 0 {
            return "In Progress"
        }
        return "Ready"
    }

    private var statusColor: Color {
        if summary.isActive || summary.status == "processing" {
            return theme.accentYellow
        }
        if summary.status == "completed" || (summary.totalPages > 0 && summary.processedCount >= summary.totalPages) {
            return theme.accentGreen
        }
        return theme.accentPrimary
    }
}
