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
                    .studioButtonStyle(.destructive, theme: theme, size: .small)
                } else {
                    Button("Resume") {
                        Task { await store.startOrResumeColorization() }
                    }
                    .studioButtonStyle(.prominent, theme: theme, size: .small)
                    .disabled(store.activeSession == nil)
                }

                Button("Output Folder") {
                    store.revealOutputDirectory()
                }
                .studioButtonStyle(.secondary, theme: theme, size: .small)
            }

            Divider()

            HStack {
                if let updateInfo = store.availableUpdateInfo {
                    Button {
                        NSApp.activate(ignoringOtherApps: true)
                        openWindow(id: "studio-main")
                        store.showUpdateSheet = true
                    } label: {
                        Label("Update v\(updateInfo.version.description)", systemImage: "arrow.down.circle.fill")
                    }
                    .studioButtonStyle(.prominent, theme: theme, size: .small, tint: theme.accentGreen)
                } else {
                    Button("Check for Updates…") {
                        NSApp.activate(ignoringOtherApps: true)
                        openWindow(id: "studio-main")
                        Task { await store.checkForUpdates(userInitiated: true) }
                    }
                    .studioButtonStyle(.ghost, theme: theme, size: .small)
                }
                Spacer()
                Text("v\(AppMetadata.currentVersionString)")
                    .font(.caption2)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            }

            HStack {
                Button("Open Studio Window") {
                    NSApp.activate(ignoringOtherApps: true)
                    openWindow(id: "studio-main")
                }
                .studioButtonStyle(.prominent, theme: theme, size: .regular)

                Spacer()

                Button("Quit") {
                    store.shutdownSynchronously()
                    NSApplication.shared.terminate(nil)
                }
                .studioButtonStyle(.secondary, theme: theme, size: .regular)
            }
        }
        .padding(14)
        .frame(width: 320)
    }
}
