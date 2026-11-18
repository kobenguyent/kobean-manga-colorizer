import KobeanMangaCore
import SwiftUI

struct StudioSettingsView: View {
    @Bindable var store: StudioStore
    @State private var apiKeyInput: String = ""

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
        }
        .formStyle(.grouped)
        .frame(width: 520, height: 380)
        .onAppear {
            apiKeyInput = store.geminiAPIKey
        }
    }
}
