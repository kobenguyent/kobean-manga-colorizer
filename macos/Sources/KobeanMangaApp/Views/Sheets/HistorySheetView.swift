import KobeanMangaCore
import SwiftUI

struct HistorySheetView: View {
    @Bindable var store: StudioStore
    @Environment(\.dismiss) private var dismiss

    @State private var searchText: String = ""
    @State private var statusFilter: String = "all"

    private var filteredHistory: [MangaSessionSummary] {
        store.sessions.filter { item in
            let matchesSearch = searchText.trimmingCharacters(in: .whitespaces).isEmpty
                || item.filename.localizedCaseInsensitiveContains(searchText)
            let isDone = item.status == "completed" || (item.totalPages > 0 && item.processedCount >= item.totalPages)
            let matchesStatus: Bool = {
                switch statusFilter {
                case "completed": return isDone
                case "pending": return !isDone
                default: return true
                }
            }()
            return matchesSearch && matchesStatus
        }
    }

    private var totalPagesCount: Int {
        store.sessions.reduce(0) { $0 + $1.totalPages }
    }

    private var totalColorizedCount: Int {
        store.sessions.reduce(0) { $0 + $1.processedCount }
    }

    var body: some View {
        let theme = store.currentTheme

        VStack(spacing: 0) {
            HStack(spacing: 10) {
                StudioBrandLogoView(size: 30, style: .appIcon, theme: theme)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Session History & Library")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(theme.textPrimary)
                    Text("\(store.sessions.count) volumes · \(totalColorizedCount)/\(totalPagesCount) pages colorized")
                        .font(.caption)
                        .monospacedDigit()
                        .foregroundStyle(theme.textSecondary)
                }
                Spacer()
                Button("Refresh") {
                    Task { await store.refreshSessions() }
                }
                .buttonStyle(.bordered)
                Button("Done") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
            .padding(16)
            .background(theme.bgHeader)

            StudioHairline(theme: theme)

            HStack(spacing: 10) {
                TextField("Search sessions...", text: $searchText)
                    .textFieldStyle(.roundedBorder)

                StudioSegmentedControl(
                    items: [
                        ("all", "All", nil),
                        ("completed", "Completed", nil),
                        ("pending", "In Progress", nil),
                    ],
                    selection: $statusFilter,
                    theme: theme
                )

                if !store.selectedSessionIds.isEmpty {
                    Button("Delete Selected (\(store.selectedSessionIds.count))", role: .destructive) {
                        Task { await store.bulkDeleteSelectedSessions() }
                    }
                    .buttonStyle(.bordered)
                }
            }
            .padding(12)
            .background(theme.bgCardSubtle)

            StudioHairline(theme: theme)

            if filteredHistory.isEmpty {
                VStack(spacing: 10) {
                    Spacer()
                    Image(systemName: "clock.arrow.circlepath")
                        .font(.largeTitle)
                        .foregroundStyle(theme.textMuted)
                    Text("No sessions match your filter")
                        .font(.headline)
                        .foregroundStyle(theme.textSecondary)
                    Spacer()
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(filteredHistory) { item in
                    HStack(spacing: 12) {
                        Button {
                            store.toggleSessionSelection(item.sessionId)
                        } label: {
                            Image(systemName: store.selectedSessionIds.contains(item.sessionId) ? "checkmark.square.fill" : "square")
                                .foregroundStyle(theme.accentPrimary)
                        }
                        .buttonStyle(.plain)

                        VStack(alignment: .leading, spacing: 4) {
                            Text(item.filename)
                                .font(.body.weight(.medium))
                                .foregroundStyle(theme.textPrimary)
                            HStack(spacing: 8) {
                                Text("\(item.processedCount)/\(item.totalPages) pages")
                                    .font(.caption)
                                    .monospacedDigit()
                                    .foregroundStyle(theme.textSecondary)
                                Text(item.status.capitalized)
                                    .font(.caption2.weight(.semibold))
                                    .foregroundStyle(theme.accentPrimary)
                            }
                        }

                        Spacer()

                        Button("Open") {
                            Task {
                                await store.selectSession(id: item.sessionId)
                                dismiss()
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(theme.accentPrimary)
                        .controlSize(.small)

                        Button("Export") {
                            Task {
                                await store.selectSession(id: item.sessionId)
                                await store.exportCurrentSession(format: .auto)
                            }
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)

                        Button(role: .destructive) {
                            Task { await store.deleteSession(id: item.sessionId) }
                        } label: {
                            Image(systemName: "trash")
                        }
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .frame(minWidth: 720, minHeight: 500)
        .background(theme.bgDark)
    }
}
