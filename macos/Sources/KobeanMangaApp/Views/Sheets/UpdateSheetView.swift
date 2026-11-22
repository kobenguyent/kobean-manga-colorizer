import AppKit
import KobeanMangaCore
import SwiftUI

struct UpdateSheetView: View {
    @Bindable var store: StudioStore
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        let theme = store.currentTheme

        VStack(alignment: .leading, spacing: 16) {
            HStack(spacing: 12) {
                StudioBrandLogoView(size: 42, style: .appIcon, theme: theme)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Kobean Manga Colorizer Update")
                        .font(.system(size: 16, weight: .bold))
                        .foregroundStyle(theme.textPrimary)
                    Text("Installed v\(AppMetadata.currentVersionString) (Build \(AppMetadata.buildNumber)) · \(store.updateGitHubRepository)")
                        .font(.system(size: 11, design: .monospaced))
                        .foregroundStyle(theme.textSecondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                Spacer()
            }

            StudioHairline(theme: theme)

            ZStack(alignment: .leading) {
                stateBody(theme: theme)
                    .id(updateStatePhase)
                    .transition(reduceMotion ? .opacity : .opacity.combined(with: .scale(scale: 0.98)))
            }
            .animation(StudioMotion.hoverAnimation(reduceMotion: reduceMotion), value: updateStatePhase)

            StudioHairline(theme: theme)

            HStack {
                Button("Check Now") {
                    Task { await store.checkForUpdates(userInitiated: true) }
                }
                .studioButtonStyle(.secondary, theme: theme, size: .regular)
                .disabled(store.isCheckingOrDownloadingUpdate)

                Spacer()

                Button("Close") { dismiss() }
                    .studioButtonStyle(.secondary, theme: theme, size: .regular)
                    .keyboardShortcut(.cancelAction)
                    .disabled(isInstalling)
            }
        }
        .padding(20)
        .frame(width: 520)
        .background(theme.bgHeader)
        .preferredColorScheme(theme.preferredColorScheme)
    }

    private var isInstalling: Bool {
        if case .installing = store.updateState { return true }
        return false
    }

    private var updateStatePhase: String {
        switch store.updateState {
        case .idle: return "idle"
        case .checking: return "checking"
        case .upToDate: return "upToDate"
        case .available: return "available"
        case .downloading: return "downloading"
        case .readyToInstall: return "readyToInstall"
        case .installing: return "installing"
        case .failed: return "failed"
        }
    }

    @ViewBuilder
    private func stateBody(theme: StudioTheme) -> some View {
        switch store.updateState {
        case .idle:
            Text("Click \"Check Now\" to query GitHub Releases for the latest native macOS build.")
                .font(.system(size: 12.5))
                .foregroundStyle(theme.textSecondary)
                .padding(.vertical, 8)

        case .checking:
            HStack(spacing: 10) {
                ProgressView()
                    .controlSize(.small)
                Text("Checking GitHub Releases for \(store.updateGitHubRepository)…")
                    .font(.system(size: 12.5))
                    .foregroundStyle(theme.textSecondary)
            }
            .padding(.vertical, 12)

        case .upToDate(let current, let checkedAt):
            HStack(spacing: 10) {
                Image(systemName: "checkmark.seal.fill")
                    .font(.system(size: 22))
                    .foregroundStyle(theme.accentGreen)
                VStack(alignment: .leading, spacing: 2) {
                    Text("You're up to date (v\(current.description))")
                        .font(.system(size: 13.5, weight: .semibold))
                        .foregroundStyle(theme.textPrimary)
                    Text("Last checked \(checkedAt.formatted(date: .omitted, time: .shortened))")
                        .font(.system(size: 11))
                        .foregroundStyle(theme.textMuted)
                }
            }
            .padding(.vertical, 8)

        case .available(let release, let latestVersion, let asset):
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    HStack(spacing: 5) {
                        Image(systemName: "sparkles")
                            .font(.system(size: 10, weight: .bold))
                        Text("v\(latestVersion.description) Available")
                            .font(.system(size: 11.5, weight: .semibold))
                    }
                    .foregroundStyle(theme.accentPrimary)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 4)
                    .background(theme.accentPrimary.opacity(0.16), in: Capsule())

                    if release.isPrerelease {
                        Text("Pre-release")
                            .font(.system(size: 10.5, weight: .semibold))
                            .foregroundStyle(theme.accentYellow)
                            .padding(.horizontal, 7)
                            .padding(.vertical, 3)
                            .background(theme.accentYellow.opacity(0.16), in: Capsule())
                    }

                    Spacer()

                    if let asset {
                        Text("\(asset.name) (\(asset.formattedSize))")
                            .font(.system(size: 10.5, design: .monospaced))
                            .foregroundStyle(theme.textMuted)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    }
                }

                if let notes = release.body, !notes.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    ScrollView {
                        Text(notes)
                            .font(.system(size: 11.5, design: .monospaced))
                            .foregroundStyle(theme.textSecondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(10)
                    }
                    .frame(height: 150)
                    .background(theme.bgDark.opacity(0.75), in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .overlay {
                        RoundedRectangle(cornerRadius: 8, style: .continuous)
                            .strokeBorder(theme.bgCardBorder, lineWidth: 1)
                    }
                }

                Text("Once downloaded and verified via SHA-256, Kobean Manga Colorizer will close automatically, install the update, and relaunch.")
                    .font(.system(size: 11))
                    .foregroundStyle(theme.textMuted)

                HStack(spacing: 8) {
                    if let asset {
                        Button("Download & Update") {
                            Task {
                                await store.downloadAndInstallUpdate(
                                    release: release,
                                    asset: asset,
                                    autoCloseAndInstall: true
                                )
                            }
                        }
                        .studioButtonStyle(.prominent, theme: theme, size: .regular)
                    }

                    Button("Open Release Page") {
                        NSWorkspace.shared.open(release.htmlURL)
                    }
                    .studioButtonStyle(.secondary, theme: theme, size: .regular)

                    Spacer()

                    Button("Skip Version") {
                        store.skipUpdateVersion(release.tagName)
                    }
                    .studioButtonStyle(.ghost, theme: theme, size: .small)
                }
            }

        case .downloading(let release, let asset, let progress):
            let percent = Int((progress * 100).rounded())
            VStack(alignment: .leading, spacing: 8) {
                Text("Downloading \(release.tagName) — \(asset.name)")
                    .font(.system(size: 12.5, weight: .semibold))
                    .foregroundStyle(theme.textPrimary)
                ProgressView(value: progress, total: 1.0)
                    .tint(theme.accentPrimary)
                HStack(spacing: 4) {
                    Text("\(percent)%")
                        .monospacedDigit()
                        .contentTransition(.numericText())
                    Text("complete · Will verify SHA-256, close current app, and update automatically")
                }
                .font(.system(size: 11, design: .monospaced))
                .foregroundStyle(theme.textMuted)
            }
            .padding(.vertical, 8)

        case .readyToInstall(let release, let artifact):
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 8) {
                    Image(systemName: "checkmark.shield.fill")
                        .font(.system(size: 20))
                        .foregroundStyle(theme.accentGreen)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Ready to Install \(release.tagName)")
                            .font(.system(size: 13.5, weight: .semibold))
                            .foregroundStyle(theme.textPrimary)
                        Text(
                            artifact.verifiedAgainstChecksums
                                ? "SHA-256 verified against release SHA256SUMS.txt"
                                : "Downloaded SHA-256: \(artifact.sha256.prefix(16))…"
                        )
                        .font(.system(size: 10.5, design: .monospaced))
                        .foregroundStyle(theme.accentGreen)
                    }
                }

                Text("Kobean Manga Colorizer will close immediately, atomically replace the installed app bundle, clear macOS quarantine attributes, and relaunch.")
                    .font(.system(size: 11.5))
                    .foregroundStyle(theme.textSecondary)

                HStack(spacing: 8) {
                    Button("Quit & Install Update") {
                        store.installDownloadedUpdateAndQuit(release: release, artifact: artifact)
                    }
                    .studioButtonStyle(.prominent, theme: theme, size: .regular, tint: theme.accentGreen)

                    Button("Reveal Downloaded File") {
                        NSWorkspace.shared.activateFileViewerSelecting([artifact.fileURL])
                    }
                    .studioButtonStyle(.secondary, theme: theme, size: .regular)
                }
            }

        case .installing(let release):
            HStack(spacing: 10) {
                ProgressView()
                    .controlSize(.small)
                Text("Closing Kobean Manga Colorizer and installing \(release.tagName)…")
                    .font(.system(size: 12.5, weight: .medium))
                    .foregroundStyle(theme.textPrimary)
            }
            .padding(.vertical, 10)

        case .failed(let message):
            VStack(alignment: .leading, spacing: 8) {
                Label("Update Check Failed", systemImage: "exclamationmark.triangle.fill")
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.red)
                Text(message)
                    .font(.system(size: 11.5))
                    .foregroundStyle(theme.textSecondary)
                    .textSelection(.enabled)
            }
            .padding(.vertical, 6)
        }
    }
}
