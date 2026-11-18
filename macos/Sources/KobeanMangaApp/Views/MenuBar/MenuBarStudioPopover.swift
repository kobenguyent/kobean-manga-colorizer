import AppKit
import KobeanMangaCore
import SwiftUI

struct MenuBarStudioPopover: View {
    @Bindable var store: StudioStore
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        let theme = store.currentTheme

        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                StudioBrandLogoView(size: 24, style: .appIcon, theme: theme)
                Text("Kobean Manga Studio")
                    .font(.headline)
                    .foregroundStyle(theme.textPrimary)
                Spacer()
                Circle()
                    .fill(store.backendState.isRunning ? theme.accentGreen : theme.accentYellow)
                    .frame(width: 8, height: 8)
            }

            Text(store.backendState.isRunning ? "Engine Connected" : "Starting Local Engine…")
                .font(.caption)
                .foregroundStyle(theme.textSecondary)

            Divider()

            if let sess = store.activeSession {
                VStack(alignment: .leading, spacing: 6) {
                    Text(sess.filename)
                        .font(.callout.weight(.semibold))
                        .lineLimit(1)
                        .truncationMode(.middle)
                    ProgressView(value: sess.progressFraction)
                        .tint(theme.accentPrimary)
                    HStack {
                        Text("\(sess.processedCount)/\(sess.totalPages) pages")
                            .font(.caption2)
                            .monospacedDigit()
                            .foregroundStyle(.secondary)
                        Spacer()
                        Text(store.isColorizing ? "Colorizing" : sess.status.capitalized)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(store.isColorizing ? theme.accentYellow : theme.accentGreen)
                    }
                }
            } else {
                Text("No active volume loaded.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if store.isExporting {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Omnibus Export: \(store.combinedExportPercent)%")
                        .font(.caption.weight(.semibold))
                        .monospacedDigit()
                    ProgressView(value: Double(store.combinedExportPercent), total: 100)
                }
            }

            HStack(spacing: 8) {
                if store.isColorizing {
                    Button("Pause / Cancel") {
                        Task { await store.cancelColorization() }
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                } else {
                    Button("Resume") {
                        Task { await store.startOrResumeColorization() }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(theme.accentPrimary)
                    .controlSize(.small)
                    .disabled(store.activeSession == nil)
                }

                Button("Output Folder") {
                    store.revealOutputDirectory()
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }

            Divider()

            HStack {
                Button("Open Studio Window") {
                    NSApp.activate(ignoringOtherApps: true)
                    openWindow(id: "studio-main")
                }
                .buttonStyle(.borderedProminent)
                .tint(theme.accentPrimary)

                Spacer()

                Button("Quit") {
                    store.shutdownSynchronously()
                    NSApplication.shared.terminate(nil)
                }
                .buttonStyle(.bordered)
            }
        }
        .padding(14)
        .frame(width: 320)
    }
}
