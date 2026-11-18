import AppKit
import KobeanMangaCore
import SwiftUI

@main
struct KobeanMangaApp: App {
    @State private var store = StudioStore()

    var body: some Scene {
        WindowGroup("Kobean Manga Colorizer", id: "studio-main") {
            MainStudioSplitView(store: store)
                .frame(minWidth: 1080, minHeight: 700)
                .preferredColorScheme(store.currentTheme.preferredColorScheme)
                .task {
                    StudioBrandAssets.applyOfficialApplicationIcon()
                    await store.bootstrap()
                }
                .onReceive(
                    NotificationCenter.default.publisher(for: NSApplication.willTerminateNotification)
                ) { _ in
                    store.shutdownSynchronously()
                }
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 1360, height: 860)
        .commands {
            CommandMenu("Studio") {
                Button("Import Files…") {
                    let urls = StudioFilePanels.pickFiles()
                    if !urls.isEmpty {
                        Task { await store.uploadFiles(urls) }
                    }
                }
                .keyboardShortcut("o", modifiers: .command)

                Button("Import Manga Folder…") {
                    if let folder = StudioFilePanels.pickFolder() {
                        Task { await store.importDirectory(url: folder) }
                    }
                }
                .keyboardShortcut("o", modifiers: [.command, .shift])

                Divider()

                Button("Preview Current Page") {
                    Task { await store.previewCurrentPage() }
                }
                .keyboardShortcut("p", modifiers: .command)
                .disabled(store.activeSession == nil || store.isPreviewing)

                Button("Start / Resume Colorization") {
                    Task { await store.startOrResumeColorization() }
                }
                .keyboardShortcut("r", modifiers: .command)
                .disabled(store.activeSession == nil || store.isColorizing)

                Button("Translate Current Page") {
                    Task { await store.translateCurrentPage() }
                }
                .keyboardShortcut("t", modifiers: .command)
                .disabled(store.activeSession == nil || store.isTranslating)

                Button("Learn Current Page to Series Memory") {
                    Task { await store.learnCurrentPage() }
                }
                .keyboardShortcut("l", modifiers: .command)
                .disabled(store.currentPage?.isColorized != true)

                Divider()

                Button("Quick Export Current Session") {
                    Task { await store.exportCurrentSession(format: .auto) }
                }
                .keyboardShortcut("e", modifiers: .command)
                .disabled(store.activeSession == nil || store.isExporting)
            }

            CommandMenu("Navigate") {
                Button("Previous Page") {
                    store.previousPage()
                }
                .keyboardShortcut("[", modifiers: .command)
                .disabled(store.activePageIndex <= 0)

                Button("Next Page") {
                    store.nextPage()
                }
                .keyboardShortcut("]", modifiers: .command)
                .disabled(store.activePageIndex + 1 >= (store.activeSession?.pages.count ?? 0))

                Divider()

                Button("Toggle Thumbnail Strip") {
                    store.toggleThumbnailStrip()
                }
                .keyboardShortcut("t", modifiers: [.control, .command])

                Button("Toggle Fullscreen Comparator") {
                    store.toggleFullscreenComparator()
                }
                .keyboardShortcut("f", modifiers: [.control, .command])

                Divider()

                Button("Zoom In") {
                    store.zoomIn()
                }
                .keyboardShortcut("+", modifiers: .command)

                Button("Zoom Out") {
                    store.zoomOut()
                }
                .keyboardShortcut("-", modifiers: .command)

                Button("Reset Zoom (100%)") {
                    store.resetZoom()
                }
                .keyboardShortcut("0", modifiers: .command)
            }
        }

        MenuBarExtra {
            MenuBarStudioPopover(store: store)
                .preferredColorScheme(store.currentTheme.preferredColorScheme)
        } label: {
            if let icon = StudioBrandAssets.menuBarIconImage() {
                Image(nsImage: icon)
            } else {
                Text("Kobean")
            }
        }
        .menuBarExtraStyle(.window)

        Settings {
            StudioSettingsView(store: store)
                .preferredColorScheme(store.currentTheme.preferredColorScheme)
        }
    }
}
