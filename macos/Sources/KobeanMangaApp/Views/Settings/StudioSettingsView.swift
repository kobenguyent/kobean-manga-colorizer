import KobeanMangaCore
import SwiftUI

struct StudioSettingsView: View {
    @Bindable var store: StudioStore
    @State private var apiKeyInput: String = ""
    @State private var showLocalUpdateSheet: Bool = false

    var body: some View {
        let theme = store.currentTheme

        Form {
            Section {
                HStack(spacing: 12) {
                    StudioBrandLogoView(size: 36, style: .appIcon, theme: theme)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Kobean Manga Colorizer Studio")
                            .font(.headline)
                        Text("Native macOS Colorization & Series Memory Engine")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                .padding(.vertical, 2)
            }

            Section("Local Backend Engine") {
                TextField("Preferred Local Port", value: $store.preferredPort, format: .number)
                    .monospacedDigit()
                HStack {
                    TextField("Workspace Root (containing main.py)", text: $store.workspacePathOverride)
                    Button("Browse…") {
                        if let folder = StudioFilePanels.pickFolder() {
                            store.workspacePathOverride = folder.path
                        }
                    }
                }
                HStack {
                    Button("Reconnect / Restart Engine") {
                        Task { await store.restartBackend() }
                    }
                    Spacer()
                    Text(store.backendState.isRunning ? "Connected on 127.0.0.1:\(store.preferredPort)" : "Disconnected")
                        .font(.caption)
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                }
            }

            Section("Google Gemini API Key (macOS Keychain)") {
                HStack {
                    SecureField("AIzaSy...", text: $apiKeyInput)
                    Button("Save to Keychain") {
                        store.saveGeminiAPIKey(apiKeyInput)
                    }
                    .buttonStyle(.borderedProminent)
                }
                Text("Stored securely in macOS Keychain under service \(KeychainHelper.defaultService), never in UserDefaults or session files.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Section("Studio Theme") {
                Picker("Theme", selection: Binding(
                    get: { store.activeThemeID },
                    set: { store.setTheme($0) }
                )) {
                    ForEach(StudioTheme.allThemes) { theme in
                        Text("\(theme.displayName) — \(theme.tagline)").tag(theme.id)
                    }
                }
            }

            Section("Software Updates (GitHub Releases)") {
                Toggle("Automatically check for updates on launch", isOn: $store.autoCheckForUpdates)
                Toggle("Include pre-release builds", isOn: $store.includePrereleaseUpdates)
                TextField("GitHub Repository (owner/repo)", text: $store.updateGitHubRepository)
                    .font(.system(.body, design: .monospaced))
                HStack {
                    Button("Check for Updates…") {
                        showLocalUpdateSheet = true
                        Task { await store.checkForUpdates(userInitiated: true, presentSheet: false) }
                    }
                    .disabled(store.isCheckingOrDownloadingUpdate)
                    Spacer()
                    Text(updateSummaryText)
                        .font(.caption)
                        .monospacedDigit()
                        .foregroundStyle(.secondary)
                }
            }
        }
        .formStyle(.grouped)
        .frame(width: 540, height: 500)
        .onAppear {
            apiKeyInput = store.geminiAPIKey
        }
        .sheet(isPresented: $showLocalUpdateSheet) {
            UpdateSheetView(store: store)
        }
    }

    private var updateSummaryText: String {
        switch store.updateState {
        case .checking:
            return "Checking GitHub Releases…"
        case .available(_, let version, _):
            return "Update v\(version.description) available"
        case .downloading(_, _, let progress):
            return "Downloading \(Int((progress * 100).rounded()))%…"
        case .upToDate(let current, _):
            return "Up to date (v\(current.description))"
        case .installing(let release):
            return "Installing \(release.tagName)…"
        case .readyToInstall(let release, _):
            return "Ready to install \(release.tagName)"
        case .failed:
            return "Update check failed"
        case .idle:
            return "Installed v\(AppMetadata.currentVersionString) (Build \(AppMetadata.buildNumber))"
        }
    }
}
