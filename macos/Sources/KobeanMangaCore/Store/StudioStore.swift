import AppKit
import Foundation
import Observation
import SwiftUI

public enum ComparatorMode: String, Codable, Sendable, CaseIterable, Identifiable {
    case split
    case originalOnly = "original_only"
    case colorizedOnly = "colorized_only"

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .split: return "Split"
        case .originalOnly: return "B&W"
        case .colorizedOnly: return "Color"
        }
    }
}

public enum InspectorTab: String, Codable, Sendable, CaseIterable, Identifiable {
    case engine = "Engine"
    case palette = "Palette"
    case export = "Export"

    public var id: String { rawValue }
}

public enum PageGalleryFilter: String, Codable, Sendable, CaseIterable, Identifiable {
    case all = "All Pages"
    case colorized = "Colorized"
    case uncolorized = "Uncolorized"
    case translated = "Translated"

    public var id: String { rawValue }
}

@Observable
@MainActor
public final class StudioStore {
    public typealias RevealInFinderHandler = @MainActor @Sendable (URL) -> Void
    public typealias ImagePrefetchHandler = @MainActor @Sendable ([URL]) -> Void

    private static let themeDefaultsKey = "kobean_theme"
    private static let settingsDefaultsKey = "kobean_colorize_settings"
    private static let workspaceDefaultsKey = "kobean_workspace_path"
    private static let preferredPortDefaultsKey = "kobean_preferred_port"

    // MARK: - Dependencies

    public let apiClient: StudioAPIClientProtocol
    public let supervisor: BackendSupervisor
    private let keychain: KeychainHelperProtocol
    private let userDefaults: UserDefaults
    private let revealInFinderHandler: RevealInFinderHandler
    private let imagePrefetchHandler: ImagePrefetchHandler

    // MARK: - Backend & Workspace State

    public var backendState: BackendState = .stopped
    public var healthStatus: HealthStatus?
    public var hardwareProfile: HardwareProfile?
    public var backendLogs: [String] = []
    public var workspacePathOverride: String {
        didSet {
            userDefaults.set(workspacePathOverride, forKey: Self.workspaceDefaultsKey)
        }
    }
    public var preferredPort: Int {
        didSet {
            let clamped = (1024...65535).contains(preferredPort) ? preferredPort : 8000
            if preferredPort != clamped { preferredPort = clamped }
            userDefaults.set(preferredPort, forKey: Self.preferredPortDefaultsKey)
        }
    }

    // MARK: - UI & Theme State

    public var activeThemeID: StudioThemeID
    public var activeTheme: StudioTheme { activeThemeID.theme }
    public var currentTheme: StudioTheme { activeTheme }
    public var selectedInspectorTab: InspectorTab = .engine
    public var isInspectorVisible: Bool = true
    public var showExemplarSheet: Bool = false
    public var showHistorySheet: Bool = false
    public var pageGalleryFilter: PageGalleryFilter = .all

    public var isBusy: Bool = false
    public var statusBannerMessage: String?
    public var errorMessage: String?

    // MARK: - Sessions & Pages State

    public var sessions: [MangaSessionSummary] = []
    public var activeSession: MangaSessionDetail?
    public var selectedSessionIds: Set<String> = []
    public var sessionSearchQuery: String = ""
    public var activePageIndex: Int = 0
    public var selectedPageIndices: Set<Int> = []
    public var cacheBusterVersion: Int = 0

    // MARK: - Comparator State

    public var comparatorMode: ComparatorMode = .split
    public var splitRatio: Double = 0.5 {
        didSet {
            let clamped = min(0.98, max(0.02, splitRatio))
            if splitRatio != clamped {
                splitRatio = clamped
            }
        }
    }
    public var zoomScale: Double = 1.0 {
        didSet {
            let clamped = min(5.0, max(0.25, zoomScale))
            if zoomScale != clamped {
                zoomScale = clamped
            }
        }
    }
    public var panOffset: CGSize = .zero
    public var showThumbnailStrip: Bool = true
    public var isFullscreenComparator: Bool = false

    // MARK: - Engine, Colorization & Translation State

    public var colorizeConfig: ColorizeConfig
    public var geminiAPIKey: String = ""
    public var isColorizing: Bool = false
    public var isPreviewing: Bool = false
    public var isTranslating: Bool = false
    public var isImporting: Bool = false
    public var importProgressText: String = ""
    public var colorizeProgressMessage: String = ""
    public var batchStatus: BatchStatusDTO?

    // MARK: - Palette, Series Memory & LoRA State

    public var presets: [MangaPresetDTO] = []
    public var activePalette: CharacterPaletteDTO = CharacterPaletteDTO()
    public var seriesMemoryResponse: SeriesMemoryResponseDTO?
    public var seriesExemplars: [SeriesExemplarDTO] = []
    public var adapterStatus: AdapterStatusDTO?
    public var autoRefineSettings: AutoRefineSettingsDTO?
    public var isRecognizingCharacters: Bool = false
    public var isTrainingAdapter: Bool = false

    // MARK: - Export & Omnibus State

    public var omnibusConfig: CombinedOmnibusConfig = CombinedOmnibusConfig()
    public var isExporting: Bool = false
    public var combinedExportJob: CombinedExportJobDTO?
    public var combinedExportPercent: Int = 0
    public var combinedExportStatusText: String = ""
    public var lastDownloadedFileURL: URL?

    @ObservationIgnored private var colorizeStreamTask: Task<Void, Never>?
    @ObservationIgnored private var exportStreamTask: Task<Void, Never>?
    @ObservationIgnored private var persistPreferencesTask: Task<Void, Never>?

    // MARK: - Init

    public init(
        apiClient: StudioAPIClientProtocol = StudioAPIClient(),
        supervisor: BackendSupervisor = BackendSupervisor(),
        keychain: KeychainHelperProtocol = KeychainHelper.shared,
        userDefaults: UserDefaults = .standard,
        revealInFinderHandler: RevealInFinderHandler? = nil,
        imagePrefetchHandler: ImagePrefetchHandler? = nil
    ) {
        self.apiClient = apiClient
        self.supervisor = supervisor
        self.keychain = keychain
        self.userDefaults = userDefaults
        self.revealInFinderHandler = revealInFinderHandler ?? { url in
            let safeURL = url.standardizedFileURL
            NSWorkspace.shared.activateFileViewerSelecting([safeURL])
        }
        self.imagePrefetchHandler = imagePrefetchHandler ?? { urls in
            Task.detached(priority: .utility) {
                await StudioImageCache.shared.prefetch(urls: urls)
            }
        }

        let storedTheme = userDefaults.string(forKey: Self.themeDefaultsKey)
        self.activeThemeID = storedTheme.flatMap(StudioThemeID.init(rawValue:)) ?? .cyberNeon
        self.workspacePathOverride = userDefaults.string(forKey: Self.workspaceDefaultsKey) ?? ""
        let savedPort = userDefaults.integer(forKey: Self.preferredPortDefaultsKey)
        self.preferredPort = (1024...65535).contains(savedPort) ? savedPort : 8000

        let savedSecret = keychain.read(key: KeychainHelper.geminiAPIKeyAccount) ?? ""
        self.geminiAPIKey = savedSecret

        var loadedConfig = ColorizeConfig()
        if let rawData = userDefaults.data(forKey: Self.settingsDefaultsKey),
           let decoded = try? JSONDecoder().decode(PersistedColorizeSettings.self, from: rawData) {
            loadedConfig.modelProvider = decoded.modelProvider
            loadedConfig.modelName = decoded.modelName
            loadedConfig.style = decoded.style
            loadedConfig.saturation = decoded.saturation
            loadedConfig.contrast = decoded.contrast
            loadedConfig.linePreserve = decoded.linePreserve
            loadedConfig.skipIfColored = decoded.skipIfColored
            loadedConfig.denoiseScreentone = decoded.denoiseScreentone
            loadedConfig.recognitionMode = decoded.recognitionMode
            loadedConfig.translatePage = decoded.translatePage
            loadedConfig.translationEngine = decoded.translationEngine
            loadedConfig.targetLanguage = decoded.targetLanguage
        }
        loadedConfig.apiKey = savedSecret
        self.colorizeConfig = loadedConfig
    }

    // MARK: - Computed Helpers

    public var activeSessionId: String? {
        activeSession?.sessionId
    }

    public var filteredSessions: [MangaSessionSummary] {
        let q = sessionSearchQuery.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !q.isEmpty else { return sessions }
        return sessions.filter {
            $0.filename.lowercased().contains(q)
                || ($0.presetTitle?.lowercased().contains(q) ?? false)
                || ($0.detectedPreset?.lowercased().contains(q) ?? false)
        }
    }

    public var currentPage: MangaPageInfo? {
        guard let pages = activeSession?.pages,
              activePageIndex >= 0,
              activePageIndex < pages.count else {
            return nil
        }
        return pages[activePageIndex]
    }

    public var canStartColorize: Bool {
        activeSession != nil && !selectedPageIndices.isEmpty && !isColorizing
    }

    public var activeSeriesKey: String {
        seriesMemoryResponse?.seriesKey ?? activeSession?.detectedPreset ?? ""
    }

    public var filteredPages: [MangaPageInfo] {
        guard let pages = activeSession?.pages else { return [] }
        switch pageGalleryFilter {
        case .all:
            return pages
        case .colorized:
            return pages.filter(\.isColorized)
        case .uncolorized:
            return pages.filter { !$0.isColorized }
        case .translated:
            return pages.filter(\.translated)
        }
    }

    // MARK: - Theme & Preferences Actions

    public func setTheme(_ themeID: StudioThemeID) {
        activeThemeID = themeID
        userDefaults.set(themeID.rawValue, forKey: Self.themeDefaultsKey)
    }

    public func saveGeminiAPIKey(_ key: String) {
        let trimmed = key.trimmingCharacters(in: .whitespacesAndNewlines)
        geminiAPIKey = trimmed
        colorizeConfig.apiKey = trimmed
        if trimmed.isEmpty {
            keychain.delete(key: KeychainHelper.geminiAPIKeyAccount)
        } else {
            keychain.save(key: KeychainHelper.geminiAPIKeyAccount, value: trimmed)
        }
    }

    public func persistColorizePreferences(immediate: Bool = false) {
        persistPreferencesTask?.cancel()
        if immediate {
            writeColorizePreferencesNow()
            return
        }
        persistPreferencesTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 250_000_000)
            guard !Task.isCancelled else { return }
            self?.writeColorizePreferencesNow()
        }
    }

    private func writeColorizePreferencesNow() {
        let snapshot = PersistedColorizeSettings(from: colorizeConfig)
        if let data = try? JSONEncoder().encode(snapshot) {
            userDefaults.set(data, forKey: Self.settingsDefaultsKey)
        }
    }

    public func selectAIProvider(_ provider: AIProvider) {
        colorizeConfig.modelProvider = provider
        if !provider.variants.contains(where: { $0.id == colorizeConfig.modelName }) {
            colorizeConfig.modelName = provider.defaultModelName
        }
        persistColorizePreferences(immediate: true)
    }

    // MARK: - Backend Lifecycle

    public func bootstrap() async {
        await connectAndLoad()
    }

    nonisolated public func shutdownSynchronously() {
        supervisor.terminateOwnedProcessSynchronously()
    }

    public func connectAndLoad() async {
        errorMessage = nil
        backendState = .starting(port: preferredPort)

        let hintURL: URL? = workspacePathOverride.isEmpty
            ? nil
            : URL(fileURLWithPath: workspacePathOverride)

        do {
            let url = try await supervisor.start(preferredPort: preferredPort, workspaceHint: hintURL)
            apiClient.updateBaseURL(url)
            backendState = await supervisor.state
            backendLogs = await supervisor.recentLogs()

            async let healthTask = apiClient.fetchHealth()
            async let hardwareTask = apiClient.fetchHardware()
            async let presetsTask = apiClient.fetchPresets()
            async let sessionsTask = apiClient.fetchSessions()

            self.healthStatus = try? await healthTask
            self.hardwareProfile = try? await hardwareTask
            self.presets = (try? await presetsTask) ?? []
            self.sessions = (try? await sessionsTask) ?? []

            if let first = sessions.first {
                await selectSession(id: first.sessionId)
            }
        } catch {
            backendState = await supervisor.state
            backendLogs = await supervisor.recentLogs()
            errorMessage = error.localizedDescription
        }
    }

    public func restartBackend() async {
        colorizeStreamTask?.cancel()
        exportStreamTask?.cancel()
        await supervisor.stop()
        await connectAndLoad()
    }

    public func refreshHealthAndHardware() async {
        healthStatus = try? await apiClient.fetchHealth()
        hardwareProfile = try? await apiClient.fetchHardware()
        backendLogs = await supervisor.recentLogs()
    }

    // MARK: - Sessions & Document Queue

    public func refreshSessions() async {
        do {
            let list = try await apiClient.fetchSessions()
            self.sessions = list
            if let activeId = activeSession?.sessionId,
               !list.contains(where: { $0.sessionId == activeId }) {
                self.activeSession = nil
                self.selectedPageIndices.removeAll()
                self.activePageIndex = 0
            }
        } catch {
            self.errorMessage = error.localizedDescription
        }
    }

    public func selectSession(id: String) async {
        colorizeStreamTask?.cancel()
        errorMessage = nil

        do {
            let detail = try await apiClient.fetchSession(id: id)
            self.activeSession = detail
            self.activePageIndex = min(max(0, activePageIndex), max(0, detail.pages.count - 1))
            if detail.pages.isEmpty {
                self.selectedPageIndices = []
            } else {
                let uncolorized = Set(detail.pages.filter { !$0.isColorized }.map(\.index))
                self.selectedPageIndices = uncolorized.isEmpty
                    ? Set(detail.pages.map(\.index))
                    : uncolorized
            }
            self.resetZoom()
            self.isColorizing = detail.isActive || detail.status == "processing"

            if let recommended = detail.recommendedStyle,
               let style = ColorAestheticStyle(rawValue: recommended) {
                colorizeConfig.style = style
            }

            await loadSessionContext(sessionId: id)
            prefetchAdjacentPages()

            if self.isColorizing {
                startColorizeStream(sessionId: id, autoResume: false)
            }
        } catch {
            self.errorMessage = error.localizedDescription
        }
    }

    public func deleteSession(id: String) async {
        do {
            if activeSession?.sessionId == id {
                colorizeStreamTask?.cancel()
            }
            try await apiClient.deleteSession(id: id)
            selectedSessionIds.remove(id)
            await refreshSessions()
            if activeSession == nil, let next = sessions.first {
                await selectSession(id: next.sessionId)
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func bulkDeleteSelectedSessions() async {
        guard !selectedSessionIds.isEmpty else { return }
        do {
            let ids = Array(selectedSessionIds)
            _ = try await apiClient.bulkDeleteSessions(ids: ids, deleteAll: false)
            selectedSessionIds.removeAll()
            await refreshSessions()
            if activeSession == nil, let next = sessions.first {
                await selectSession(id: next.sessionId)
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func deletePage(at index: Int) async {
        guard let sessionId = activeSession?.sessionId else { return }
        do {
            let updated = try await apiClient.deletePage(sessionId: sessionId, pageIndex: index)
            self.activeSession = updated
            self.selectedPageIndices = Set(
                selectedPageIndices.compactMap { oldIdx in
                    if oldIdx == index { return nil }
                    return oldIdx > index ? oldIdx - 1 : oldIdx
                }
            )
            self.activePageIndex = min(max(0, activePageIndex), max(0, updated.pages.count - 1))
            await refreshSessions()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Ingestion (Files & Directories)

    public func handleDroppedOrPickedURLs(_ urls: [URL], recursive: Bool = false) async {
        guard !urls.isEmpty else { return }
        let fm = FileManager.default
        var directories: [URL] = []
        var files: [URL] = []

        for url in urls.map(\.standardizedFileURL) {
            var isDir: ObjCBool = false
            if fm.fileExists(atPath: url.path, isDirectory: &isDir) {
                if isDir.boolValue {
                    directories.append(url)
                } else {
                    files.append(url)
                }
            }
        }

        for dir in directories {
            await importDirectory(path: dir.path, recursive: recursive, combineImages: true)
        }
        if !files.isEmpty {
            await uploadFiles(files, combineImages: false)
        }
    }

    public func uploadFiles(_ urls: [URL], combineImages: Bool = false) async {
        guard !urls.isEmpty else { return }
        isImporting = true
        importProgressText = "Uploading \(urls.count) file(s)..."
        errorMessage = nil
        defer {
            isImporting = false
            importProgressText = ""
        }

        do {
            let resp = try await apiClient.uploadFiles(
                fileURLs: urls,
                batchId: nil,
                combineImages: combineImages
            )
            await refreshSessions()
            let targetId = resp.sessions.first?.sessionId ?? resp.sessionId
            if !targetId.isEmpty {
                await selectSession(id: targetId)
            }
            statusBannerMessage = "Imported \(resp.totalFiles) document(s)"
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func importDirectory(
        url: URL,
        recursive: Bool = false,
        combineImages: Bool = true
    ) async {
        await importDirectory(
            path: url.standardizedFileURL.path,
            recursive: recursive,
            combineImages: combineImages
        )
    }

    public func importDirectory(
        path: String,
        recursive: Bool = false,
        combineImages: Bool = true
    ) async {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            errorMessage = "Please choose a valid manga folder path."
            return
        }

        isImporting = true
        importProgressText = "Scanning directory..."
        errorMessage = nil
        defer {
            isImporting = false
            importProgressText = ""
        }

        do {
            let resp = try await apiClient.importDirectory(
                path: trimmed,
                recursive: recursive,
                combineImages: combineImages
            )
            var createdIds = resp.createdSessionIds

            if resp.status == "started", !resp.importId.isEmpty {
                while !Task.isCancelled {
                    try await Task.sleep(nanoseconds: 350_000_000)
                    let st = try await apiClient.fetchImportStatus(importId: resp.importId)
                    importProgressText = st.currentFile ?? "Imported \(st.importedFiles)/\(st.totalFiles)"
                    if st.status == "completed" || st.status == "cancelled" || st.status == "failed" {
                        createdIds = st.createdSessionIds
                        if let err = st.error, !err.isEmpty {
                            errorMessage = err
                        }
                        break
                    }
                }
            }

            await refreshSessions()
            if let firstId = createdIds.first ?? sessions.first?.sessionId {
                await selectSession(id: firstId)
            }
            statusBannerMessage = "Folder import completed"
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Comparator & Page Selection Helpers

    public func setSplitRatio(_ ratio: Double) {
        splitRatio = min(0.98, max(0.02, ratio))
    }

    public func setZoomScale(_ scale: Double) {
        zoomScale = min(5.0, max(0.25, scale))
    }

    public func zoomIn() {
        setZoomScale(zoomScale + 0.25)
    }

    public func zoomOut() {
        setZoomScale(zoomScale - 0.25)
    }

    public func resetZoom() {
        zoomScale = 1.0
        panOffset = .zero
    }

    public func toggleDoubleClickZoom() {
        if abs(zoomScale - 1.0) < 0.05 {
            setZoomScale(2.0)
        } else {
            resetZoom()
        }
    }

    public func toggleThumbnailStrip() {
        showThumbnailStrip.toggle()
    }

    public func toggleFullscreenComparator() {
        isFullscreenComparator.toggle()
    }

    public func selectPage(at index: Int) {
        guard let total = activeSession?.pages.count, total > 0 else { return }
        activePageIndex = min(max(0, index), total - 1)
        prefetchAdjacentPages()
    }

    public func nextPage() {
        guard let total = activeSession?.pages.count, activePageIndex + 1 < total else { return }
        activePageIndex += 1
        prefetchAdjacentPages()
    }

    public func previousPage() {
        guard activePageIndex > 0 else { return }
        activePageIndex -= 1
        prefetchAdjacentPages()
    }

    private func prefetchAdjacentPages() {
        guard let pages = activeSession?.pages, !pages.isEmpty else { return }
        var urls: [URL] = []
        for idx in [activePageIndex - 1, activePageIndex + 1] where idx >= 0 && idx < pages.count {
            let page = pages[idx]
            if let orig = originalImageURL(for: page) {
                urls.append(orig)
            }
            if let color = colorizedImageURL(for: page) {
                urls.append(color)
            }
        }
        if !urls.isEmpty {
            imagePrefetchHandler(urls)
        }
    }

    public func selectAllPages() {
        guard let pages = activeSession?.pages else { return }
        selectedPageIndices = Set(pages.map(\.index))
    }

    public func deselectAllPages() {
        selectedPageIndices.removeAll()
    }

    public func selectUncolorizedPages() {
        guard let pages = activeSession?.pages else { return }
        selectedPageIndices = Set(pages.filter { !$0.isColorized }.map(\.index))
    }

    public func invertPageSelection() {
        guard let pages = activeSession?.pages else { return }
        let all = Set(pages.map(\.index))
        selectedPageIndices = all.subtracting(selectedPageIndices)
    }

    public func togglePageSelection(_ index: Int) {
        if selectedPageIndices.contains(index) {
            selectedPageIndices.remove(index)
        } else {
            selectedPageIndices.insert(index)
        }
    }

    public func originalImageURL(for page: MangaPageInfo) -> URL? {
        guard let sessionId = activeSession?.sessionId else { return nil }
        return apiClient.imageURL(
            relativePath: page.resolvedOriginalRelativePath(sessionId: sessionId),
            cacheBuster: nil
        )
    }

    public func colorizedImageURL(for page: MangaPageInfo) -> URL? {
        guard let sessionId = activeSession?.sessionId,
              let path = page.resolvedColorizedRelativePath(sessionId: sessionId) else {
            return nil
        }
        return apiClient.imageURL(
            relativePath: path,
            cacheBuster: "\(cacheBusterVersion)"
        )
    }

    // MARK: - Colorization, Preview & Translation

    public func previewCurrentPage() async {
        guard let sessionId = activeSession?.sessionId else { return }
        let pageIdx = activePageIndex
        isPreviewing = true
        errorMessage = nil
        defer { isPreviewing = false }

        do {
            var reqConfig = colorizeConfig
            reqConfig.apiKey = geminiAPIKey
            let result = try await apiClient.previewPage(
                sessionId: sessionId,
                pageIndex: pageIdx,
                config: reqConfig
            )
            applyPreviewResult(result, pageIndex: pageIdx)
            syncSummaryFromActiveSession()
            await loadSeriesAndAdapter(sessionId: sessionId)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func startOrResumeColorization() async {
        guard let sess = activeSession else { return }
        if !selectedPageIndices.isEmpty {
            await startColorization(forceRecolorize: false)
        } else if sess.pages.contains(where: { !$0.isColorized }) {
            await resumeColorization()
        } else if !sess.pages.isEmpty {
            selectAllPages()
            await startColorization(forceRecolorize: false)
        }
    }

    public func startColorization(forceRecolorize: Bool = false) async {
        guard let sessionId = activeSession?.sessionId, !selectedPageIndices.isEmpty else { return }
        isColorizing = true
        errorMessage = nil
        colorizeProgressMessage = "Starting colorization..."

        do {
            var reqConfig = colorizeConfig
            reqConfig.apiKey = geminiAPIKey
            let pages = selectedPageIndices.sorted()
            try await apiClient.startColorize(
                sessionId: sessionId,
                selectedPages: pages,
                forceRecolorize: forceRecolorize,
                config: reqConfig
            )
            startColorizeStream(sessionId: sessionId, autoResume: false)
        } catch {
            isColorizing = false
            errorMessage = error.localizedDescription
        }
    }

    public func resumeColorization() async {
        guard let sessionId = activeSession?.sessionId else { return }
        isColorizing = true
        errorMessage = nil
        colorizeProgressMessage = "Resuming colorization..."

        do {
            var reqConfig = colorizeConfig
            reqConfig.apiKey = geminiAPIKey
            try await apiClient.resumeColorize(sessionId: sessionId, config: reqConfig)
            startColorizeStream(sessionId: sessionId, autoResume: false)
        } catch {
            isColorizing = false
            errorMessage = error.localizedDescription
        }
    }

    public func cancelColorization() async {
        guard let sessionId = activeSession?.sessionId else { return }
        colorizeStreamTask?.cancel()
        do {
            try await apiClient.cancelColorize(sessionId: sessionId)
            isColorizing = false
            colorizeProgressMessage = "Cancelled"
            await refreshSessions()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func startBatchColorization() async {
        let targets = selectedSessionIds.isEmpty ? sessions.map(\.sessionId) : Array(selectedSessionIds)
        guard !targets.isEmpty else { return }
        errorMessage = nil

        do {
            var reqConfig = colorizeConfig
            reqConfig.apiKey = geminiAPIKey
            try await apiClient.startBatchColorize(sessionIds: targets, config: reqConfig)
            batchStatus = try? await apiClient.fetchBatchStatus()
            if let activeId = activeSession?.sessionId {
                isColorizing = true
                startColorizeStream(sessionId: activeId, autoResume: false)
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func translateCurrentPage() async {
        guard let sessionId = activeSession?.sessionId else { return }
        let pageIdx = activePageIndex
        isTranslating = true
        errorMessage = nil
        defer { isTranslating = false }

        do {
            var reqConfig = colorizeConfig
            reqConfig.apiKey = geminiAPIKey
            let resp = try await apiClient.translatePage(
                sessionId: sessionId,
                pageIndex: pageIdx,
                config: reqConfig
            )
            if var sess = activeSession, pageIdx >= 0, pageIdx < sess.pages.count {
                sess.pages[pageIdx].translations = resp.translations
                sess.pages[pageIdx].translated = resp.translated
                if let url = resp.colorizedUrl {
                    sess.pages[pageIdx].colorizedUrl = url
                    sess.pages[pageIdx].status = "colorized"
                }
                activeSession = sess
                cacheBusterVersion += 1
            }
            statusBannerMessage = resp.translated
                ? "Translated \(resp.bubbleCount) speech bubble(s)"
                : "No Japanese dialogue found on page"
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func translateSelectedOrAllPages() async {
        guard let sessionId = activeSession?.sessionId else { return }
        isTranslating = true
        isColorizing = true
        errorMessage = nil

        do {
            var reqConfig = colorizeConfig
            reqConfig.apiKey = geminiAPIKey
            let targetPages = selectedPageIndices.isEmpty ? nil : selectedPageIndices.sorted()
            let resp = try await apiClient.translateSession(
                sessionId: sessionId,
                selectedPages: targetPages,
                config: reqConfig
            )
            colorizeProgressMessage = resp.message
            startColorizeStream(sessionId: sessionId, autoResume: false)
        } catch {
            isTranslating = false
            isColorizing = false
            errorMessage = error.localizedDescription
        }
    }

    public func startColorizeStream(sessionId: String, autoResume: Bool = false) {
        colorizeStreamTask?.cancel()
        colorizeStreamTask = Task { [weak self] in
            guard let self else { return }
            do {
                let stream = apiClient.streamColorizeEvents(sessionId: sessionId, autoResume: autoResume)
                for try await event in stream {
                    if Task.isCancelled { break }
                    self.handleSSEColorizeEvent(event)
                }
                self.isColorizing = false
                self.isTranslating = false
            } catch is CancellationError {
                self.isColorizing = false
                self.isTranslating = false
            } catch {
                self.isColorizing = false
                self.isTranslating = false
                self.errorMessage = error.localizedDescription
            }
        }
    }

    public func handleSSEColorizeEvent(_ event: SSEColorizeEvent) {
        switch event {
        case .initial(let session, let isActive, _):
            if let session, activeSession?.sessionId == session.sessionId {
                activeSession = session
            }
            isColorizing = isActive

        case .start(let total, _, _):
            isColorizing = true
            colorizeProgressMessage = "Colorizing 0/\(total)..."

        case .pageUpdate(let payload):
            if var sess = activeSession, payload.pageIndex >= 0, payload.pageIndex < sess.pages.count {
                var page = sess.pages[payload.pageIndex]
                page.status = payload.status
                page.skippedColored = payload.skippedColored
                if let url = payload.colorizedUrl {
                    page.colorizedUrl = url
                }
                if let engine = payload.engine {
                    page.engineUsed = engine
                }
                if let exemplar = payload.exemplarUsed {
                    page.exemplarUsed = exemplar
                }
                if !payload.exemplarsUsed.isEmpty {
                    page.exemplarsUsed = payload.exemplarsUsed
                }
                if payload.adapterUsed {
                    page.adapterUsed = true
                }
                if payload.autoHarvested {
                    page.autoHarvested = true
                }
                if let q = payload.qualityScore {
                    page.qualityScore = q
                }
                if !payload.recognizedCharacters.isEmpty {
                    page.recognizedCharacters = payload.recognizedCharacters
                }
                if !payload.translations.isEmpty || payload.translated {
                    page.translations = payload.translations
                    page.translated = payload.translated
                }
                if let err = payload.error {
                    page.errorMessage = err
                }
                sess.pages[payload.pageIndex] = page
                if let processed = payload.processedCount {
                    sess.processedCount = processed
                } else {
                    sess.processedCount = sess.pages.filter(\.isColorized).count
                }
                activeSession = sess
                cacheBusterVersion += 1
                syncSummaryFromActiveSession()

                if let total = payload.total {
                    colorizeProgressMessage = payload.message
                        ?? "Processed \(sess.processedCount)/\(total) pages"
                } else if let progress = payload.progress {
                    colorizeProgressMessage = progress
                }
            }

        case .adapterTrainingProgress(let adapterPayload):
            isTrainingAdapter = adapterPayload.status == "training"
            adapterStatus = AdapterStatusDTO(
                status: adapterPayload.status,
                seriesKey: adapterPayload.seriesKey,
                step: adapterPayload.step,
                totalSteps: adapterPayload.totalSteps,
                progress: adapterPayload.progress,
                loss: adapterPayload.loss
            )

        case .completed(let totalProcessed, let message):
            isColorizing = false
            isTranslating = false
            if var sess = activeSession {
                sess.status = "completed"
                sess.processedCount = totalProcessed
                activeSession = sess
                syncSummaryFromActiveSession()
            }
            colorizeProgressMessage = message ?? "Completed \(totalProcessed) pages"
            statusBannerMessage = colorizeProgressMessage

        case .idle(let totalProcessed, _):
            isColorizing = false
            isTranslating = false
            if var sess = activeSession {
                sess.processedCount = totalProcessed
                activeSession = sess
                syncSummaryFromActiveSession()
            }

        case .cancelled(let processedCount, _):
            isColorizing = false
            isTranslating = false
            if var sess = activeSession {
                sess.status = "cancelled"
                sess.processedCount = processedCount
                activeSession = sess
                syncSummaryFromActiveSession()
            }
            colorizeProgressMessage = "Cancelled"

        case .error(let message):
            isColorizing = false
            isTranslating = false
            errorMessage = message
        }
    }

    // MARK: - Palette, Series Memory & LoRA Studio

    public func loadSessionContext(sessionId: String) async {
        async let paletteTask = apiClient.fetchPalette(sessionId: sessionId)
        async let memoryTask = apiClient.fetchSeriesMemory(sessionId: sessionId)
        async let exemplarsTask = apiClient.fetchExemplars(sessionOrSeriesId: sessionId)

        self.activePalette = (try? await paletteTask) ?? CharacterPaletteDTO()
        let memResp = try? await memoryTask
        self.seriesMemoryResponse = memResp
        self.seriesExemplars = (try? await exemplarsTask)?.exemplars ?? []

        let key = memResp?.seriesKey ?? ""
        if !key.isEmpty {
            async let adapterTask = apiClient.fetchAdapterStatus(seriesKey: key)
            async let refineTask = apiClient.fetchAutoRefine(seriesKey: key)
            self.adapterStatus = try? await adapterTask
            self.autoRefineSettings = try? await refineTask
        }
    }

    private func loadSeriesAndAdapter(sessionId: String) async {
        if let memResp = try? await apiClient.fetchSeriesMemory(sessionId: sessionId) {
            self.seriesMemoryResponse = memResp
            self.seriesExemplars = (try? await apiClient.fetchExemplars(sessionOrSeriesId: sessionId))?.exemplars ?? []
            if !memResp.seriesKey.isEmpty {
                self.adapterStatus = try? await apiClient.fetchAdapterStatus(seriesKey: memResp.seriesKey)
                self.autoRefineSettings = try? await apiClient.fetchAutoRefine(seriesKey: memResp.seriesKey)
            }
        }
    }

    public func applyPreset(presetId: String, applyToBatch: Bool = true) async {
        guard let sessionId = activeSession?.sessionId else { return }
        do {
            let pal = try await apiClient.applyPreset(
                sessionId: sessionId,
                presetId: presetId,
                applyToBatch: applyToBatch
            )
            self.activePalette = pal
            await loadSeriesAndAdapter(sessionId: sessionId)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func searchOnlinePreset(query: String) async {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return }
        do {
            let preset = try await apiClient.searchOnlinePreset(
                query: trimmed,
                sessionId: activeSession?.sessionId
            )
            if !presets.contains(where: { $0.id == preset.id }) {
                presets.insert(preset, at: 0)
            }
            if let sid = activeSession?.sessionId {
                await loadSessionContext(sessionId: sid)
            }
            statusBannerMessage = "Loaded character palette for \(preset.title)"
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func upsertCharacter(_ character: CharacterEntryDTO) async {
        guard let sessionId = activeSession?.sessionId else { return }
        do {
            self.activePalette = try await apiClient.upsertCharacter(sessionId: sessionId, character: character)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func deleteCharacter(name: String) async {
        guard let sessionId = activeSession?.sessionId else { return }
        do {
            self.activePalette = try await apiClient.deleteCharacter(sessionId: sessionId, name: name)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func recognizeCurrentPageCharacters() async {
        guard let sessionId = activeSession?.sessionId else { return }
        let pageIdx = activePageIndex
        isRecognizingCharacters = true
        defer { isRecognizingCharacters = false }

        do {
            let resp = try await apiClient.recognizePageCharacters(
                sessionId: sessionId,
                pageIndex: pageIdx,
                mode: colorizeConfig.recognitionMode,
                apiKey: geminiAPIKey
            )
            if var sess = activeSession, pageIdx >= 0, pageIdx < sess.pages.count {
                sess.pages[pageIdx].recognizedCharacters = resp.recognized
                activeSession = sess
            }
            if let pal = resp.palette {
                activePalette = pal
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func learnCurrentPage() async {
        await learnCurrentPageToSeriesMemory()
    }

    public func learnCurrentPageToSeriesMemory(
        characterNames: [String]? = nil,
        exemplar: Bool = true
    ) async {
        guard let sessionId = activeSession?.sessionId else { return }
        let pageIdx = activePageIndex
        do {
            let memResp = try await apiClient.learnPage(
                sessionId: sessionId,
                pageIndex: pageIdx,
                characterNames: characterNames,
                exemplar: exemplar
            )
            self.seriesMemoryResponse = memResp
            if var sess = activeSession, pageIdx >= 0, pageIdx < sess.pages.count {
                sess.pages[pageIdx].learnedToMemory = true
                activeSession = sess
            }
            self.seriesExemplars = (try? await apiClient.fetchExemplars(sessionOrSeriesId: sessionId))?.exemplars ?? []
            statusBannerMessage = memResp.message ?? "Saved page to Series Memory"
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func togglePinExemplar(pageIndex: Int, pinned: Bool) async {
        let key = activeSeriesKey
        guard !key.isEmpty else { return }
        do {
            try await apiClient.pinExemplar(seriesKey: key, pageIndex: pageIndex, pinned: pinned)
            if let sid = activeSession?.sessionId {
                self.seriesExemplars = (try? await apiClient.fetchExemplars(sessionOrSeriesId: sid))?.exemplars ?? []
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func deleteExemplar(pageIndex: Int) async {
        let key = activeSeriesKey
        guard !key.isEmpty else { return }
        do {
            try await apiClient.deleteExemplar(
                seriesKey: key,
                pageIndex: pageIndex,
                sessionId: activeSession?.sessionId
            )
            if let sid = activeSession?.sessionId {
                self.seriesExemplars = (try? await apiClient.fetchExemplars(sessionOrSeriesId: sid))?.exemplars ?? []
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func trainSeriesAdapter(steps: Int = 100, lr: Double = 2e-4) async {
        let key = activeSeriesKey
        guard !key.isEmpty else { return }
        isTrainingAdapter = true
        do {
            let status = try await apiClient.trainAdapter(seriesKey: key, steps: steps, lr: lr)
            self.adapterStatus = status
        } catch {
            isTrainingAdapter = false
            errorMessage = error.localizedDescription
        }
    }

    public func cancelAdapterTraining() async {
        let key = activeSeriesKey
        guard !key.isEmpty else { return }
        do {
            try await apiClient.cancelAdapterTraining(seriesKey: key)
            isTrainingAdapter = false
            adapterStatus = try? await apiClient.fetchAdapterStatus(seriesKey: key)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func deleteSeriesAdapter() async {
        let key = activeSeriesKey
        guard !key.isEmpty else { return }
        do {
            try await apiClient.deleteAdapter(seriesKey: key)
            adapterStatus = try? await apiClient.fetchAdapterStatus(seriesKey: key)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func updateAutoRefineSettings(_ settings: AutoRefineSettingsDTO) async {
        let key = activeSeriesKey
        guard !key.isEmpty else { return }
        do {
            self.autoRefineSettings = try await apiClient.updateAutoRefine(seriesKey: key, settings: settings)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Export & Finder Integration

    public func exportCurrentSession(format: ExportFormat, saveTo destinationURL: URL? = nil) async {
        guard let sessionId = activeSession?.sessionId else { return }
        isExporting = true
        errorMessage = nil
        defer { isExporting = false }

        do {
            let result = try await apiClient.exportSession(sessionId: sessionId, format: format)
            let dest = destinationURL ?? defaultDownloadDestination(filename: result.filename)
            let savedURL = try await apiClient.downloadFile(relativePath: result.downloadUrl, to: dest)
            self.lastDownloadedFileURL = savedURL
            statusBannerMessage = "Exported \(savedURL.lastPathComponent)"
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func exportSelectedBatch(format: ExportFormat, saveTo destinationURL: URL? = nil) async {
        let ids = selectedSessionIds.isEmpty ? sessions.map(\.sessionId) : Array(selectedSessionIds)
        guard !ids.isEmpty else { return }
        isExporting = true
        errorMessage = nil
        defer { isExporting = false }

        do {
            let result = try await apiClient.exportBatch(sessionIds: ids, format: format)
            let dest = destinationURL ?? defaultDownloadDestination(filename: result.filename)
            let savedURL = try await apiClient.downloadFile(relativePath: result.downloadUrl, to: dest)
            self.lastDownloadedFileURL = savedURL
            statusBannerMessage = "Exported batch archive \(savedURL.lastPathComponent)"
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func startCombinedOmnibusExport(saveToDirectory directoryURL: URL? = nil) async {
        isExporting = true
        errorMessage = nil
        combinedExportPercent = 0
        combinedExportStatusText = "Starting omnibus export..."

        var effectiveConfig = omnibusConfig
        if effectiveConfig.sessionIds == nil || effectiveConfig.sessionIds?.isEmpty == true {
            let ids = selectedSessionIds.isEmpty ? sessions.map(\.sessionId) : Array(selectedSessionIds)
            effectiveConfig.sessionIds = ids.isEmpty ? nil : ids
        }

        do {
            let job = try await apiClient.startCombinedExport(config: effectiveConfig)
            self.combinedExportJob = job

            exportStreamTask?.cancel()
            exportStreamTask = Task { [weak self] in
                guard let self else { return }
                do {
                    let stream = apiClient.streamCombinedExportEvents(jobId: job.jobId)
                    for try await event in stream {
                        if Task.isCancelled { break }
                        switch event {
                        case .initial(_, _, let progress):
                            self.combinedExportPercent = progress.percent
                            self.combinedExportStatusText = progress.status
                        case .progress(let progress):
                            self.combinedExportPercent = progress.percent
                            self.combinedExportStatusText = progress.status
                        case .completed(_, let downloadUrl, let filename, _, _):
                            self.combinedExportPercent = 100
                            self.combinedExportStatusText = "Export complete"
                            self.isExporting = false
                            let dest = directoryURL?.appendingPathComponent(filename)
                                ?? self.defaultDownloadDestination(filename: filename)
                            if let saved = try? await self.apiClient.downloadFile(
                                relativePath: downloadUrl,
                                to: dest
                            ) {
                                self.lastDownloadedFileURL = saved
                                self.statusBannerMessage = "Saved \(saved.lastPathComponent)"
                            }
                        case .cancelled(_, let message):
                            self.isExporting = false
                            self.combinedExportStatusText = message ?? "Cancelled"
                        case .error(_, let message):
                            self.isExporting = false
                            self.errorMessage = message
                        }
                    }
                } catch is CancellationError {
                    self.isExporting = false
                } catch {
                    self.isExporting = false
                    self.errorMessage = error.localizedDescription
                }
            }
        } catch {
            isExporting = false
            errorMessage = error.localizedDescription
        }
    }

    public func cancelCombinedOmnibusExport() async {
        guard let jobId = combinedExportJob?.jobId else { return }
        exportStreamTask?.cancel()
        do {
            try await apiClient.cancelCombinedExport(jobId: jobId)
            isExporting = false
            combinedExportStatusText = "Cancelled"
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func toggleSessionSelection(_ sessionId: String) {
        if selectedSessionIds.contains(sessionId) {
            selectedSessionIds.remove(sessionId)
        } else {
            selectedSessionIds.insert(sessionId)
        }
    }

    public func selectAllSessions() {
        selectedSessionIds = Set(sessions.map(\.sessionId))
    }

    public func deselectAllSessions() {
        selectedSessionIds.removeAll()
    }

    public func deleteAllSessions() async {
        do {
            colorizeStreamTask?.cancel()
            _ = try await apiClient.bulkDeleteSessions(ids: [], deleteAll: true)
            selectedSessionIds.removeAll()
            activeSession = nil
            selectedPageIndices.removeAll()
            activePageIndex = 0
            await refreshSessions()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func revealOutputDirectory() {
        if let dir = hardwareProfile?.storage.outputDir, !dir.isEmpty {
            revealInFinder(URL(fileURLWithPath: dir, isDirectory: true))
        } else if let last = lastDownloadedFileURL {
            revealInFinder(last)
        } else {
            let downloads = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
                ?? FileManager.default.temporaryDirectory
            revealInFinder(downloads)
        }
    }

    public func dismissError() {
        errorMessage = nil
    }

    public func dismissStatusBanner() {
        statusBannerMessage = nil
    }

    public func revealInFinder(_ url: URL) {
        let standardized = url.standardizedFileURL
        guard standardized.isFileURL else { return }
        revealInFinderHandler(standardized)
    }

    // MARK: - Internal Helpers

    private func applyPreviewResult(_ result: PreviewResultDTO, pageIndex: Int) {
        guard var sess = activeSession, pageIndex >= 0, pageIndex < sess.pages.count else { return }
        if let updatedPage = result.pageInfo {
            sess.pages[pageIndex] = updatedPage
        } else {
            var page = sess.pages[pageIndex]
            page.status = "colorized"
            if let url = result.colorizedUrl {
                page.colorizedUrl = url
            }
            if let engine = result.engine {
                page.engineUsed = engine
            }
            if let quality = result.qualityScore {
                page.qualityScore = quality
            }
            if !result.recognizedCharacters.isEmpty {
                page.recognizedCharacters = result.recognizedCharacters
            }
            if !result.translations.isEmpty || result.translated {
                page.translations = result.translations
                page.translated = result.translated
            }
            if let ex = result.exemplarUsed {
                page.exemplarUsed = ex
            }
            if !result.exemplarsUsed.isEmpty {
                page.exemplarsUsed = result.exemplarsUsed
            }
            if result.adapterUsed {
                page.adapterUsed = true
            }
            sess.pages[pageIndex] = page
        }
        sess.processedCount = result.processedCount
        if result.totalPages > 0 {
            sess.totalPages = result.totalPages
        }
        activeSession = sess
        cacheBusterVersion += 1
    }

    private func syncSummaryFromActiveSession() {
        guard let sess = activeSession,
              let idx = sessions.firstIndex(where: { $0.sessionId == sess.sessionId }) else {
            return
        }
        sessions[idx].processedCount = sess.processedCount
        sessions[idx].totalPages = sess.totalPages
        sessions[idx].status = sess.status
        sessions[idx].isActive = isColorizing
    }

    private func defaultDownloadDestination(filename: String) -> URL {
        let safeFilename = URL(fileURLWithPath: filename).lastPathComponent
        let downloads = FileManager.default.urls(for: .downloadsDirectory, in: .userDomainMask).first
            ?? FileManager.default.temporaryDirectory
        return downloads.appendingPathComponent(safeFilename.isEmpty ? "kobean-export" : safeFilename)
    }
}

private struct PersistedColorizeSettings: Codable {
    let modelProvider: AIProvider
    let modelName: String
    let style: ColorAestheticStyle
    let saturation: Double
    let contrast: Double
    let linePreserve: Double
    let skipIfColored: Bool
    let denoiseScreentone: Bool
    let recognitionMode: RecognitionMode
    let translatePage: Bool
    let translationEngine: TranslationEngine
    let targetLanguage: TargetLanguage

    init(from config: ColorizeConfig) {
        self.modelProvider = config.modelProvider
        self.modelName = config.modelName
        self.style = config.style
        self.saturation = config.saturation
        self.contrast = config.contrast
        self.linePreserve = config.linePreserve
        self.skipIfColored = config.skipIfColored
        self.denoiseScreentone = config.denoiseScreentone
        self.recognitionMode = config.recognitionMode
        self.translatePage = config.translatePage
        self.translationEngine = config.translationEngine
        self.targetLanguage = config.targetLanguage
    }
}
