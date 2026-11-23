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

public enum AppUpdateState: Equatable, Sendable {
    case idle
    case checking
    case upToDate(current: SemanticVersion, checkedAt: Date)
    case available(release: GitHubRelease, latestVersion: SemanticVersion, asset: GitHubReleaseAsset?)
    case downloading(release: GitHubRelease, asset: GitHubReleaseAsset, progress: Double)
    case readyToInstall(release: GitHubRelease, artifact: DownloadedUpdateArtifact)
    case installing(release: GitHubRelease)
    case failed(String)
}

@Observable
@MainActor
public final class StudioStore {
    public typealias RevealInFinderHandler = @MainActor @Sendable (URL) -> Void
    public typealias ImagePrefetchHandler = @MainActor @Sendable ([URL]) -> Void
    public typealias UpdateInstallerHandler = @MainActor @Sendable (UpdateInstallPlan) throws -> Void
    public typealias TerminateAppHandler = @MainActor @Sendable () -> Void

    private static let themeDefaultsKey = "kobean_theme"
    private static let settingsDefaultsKey = "kobean_colorize_settings"
    private static let workspaceDefaultsKey = "kobean_workspace_path"
    private static let preferredPortDefaultsKey = "kobean_preferred_port"
    private static let autoCheckUpdatesDefaultsKey = "kobean_auto_check_updates"
    private static let includePrereleaseUpdatesDefaultsKey = "kobean_include_prerelease_updates"
    private static let updateGitHubRepoDefaultsKey = "kobean_update_github_repo"
    private static let skippedUpdateTagDefaultsKey = "kobean_skipped_update_tag"

    // MARK: - Dependencies

    public let apiClient: StudioAPIClientProtocol
    public let supervisor: BackendSupervisor
    private let keychain: KeychainHelperProtocol
    private let userDefaults: UserDefaults
    private let revealInFinderHandler: RevealInFinderHandler
    private let imagePrefetchHandler: ImagePrefetchHandler
    private let updateService: UpdateService
    private let updateInstallerHandler: UpdateInstallerHandler
    private let terminateAppHandler: TerminateAppHandler
    private let currentVersionProvider: @Sendable () -> SemanticVersion
    private let targetAppBundleProvider: @Sendable () -> URL?

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
    public var showUpdateSheet: Bool = false
    public var pageGalleryFilter: PageGalleryFilter = .all

    // MARK: - Software Updates State

    public var updateState: AppUpdateState = .idle
    public var autoCheckForUpdates: Bool {
        didSet {
            userDefaults.set(autoCheckForUpdates, forKey: Self.autoCheckUpdatesDefaultsKey)
        }
    }
    public var includePrereleaseUpdates: Bool {
        didSet {
            userDefaults.set(includePrereleaseUpdates, forKey: Self.includePrereleaseUpdatesDefaultsKey)
        }
    }
    public var updateGitHubRepository: String {
        didSet {
            userDefaults.set(updateGitHubRepository, forKey: Self.updateGitHubRepoDefaultsKey)
        }
    }
    public var skippedUpdateTag: String {
        didSet {
            userDefaults.set(skippedUpdateTag, forKey: Self.skippedUpdateTagDefaultsKey)
        }
    }

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
    public var importProcessedCount: Int = 0
    public var importTotalCount: Int = 0
    public var importProgressFraction: Double = 0.0
    public var activeImportId: String?
    public var colorizeProgressMessage: String = ""
    public var batchStatus: BatchStatusDTO?
    @ObservationIgnored private var importCancelledLocally: Bool = false

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
    @ObservationIgnored private var batchPollTask: Task<Void, Never>?
    @ObservationIgnored private var exportStreamTask: Task<Void, Never>?
    @ObservationIgnored private var persistPreferencesTask: Task<Void, Never>?
    @ObservationIgnored private var startupUpdateCheckTask: Task<Void, Never>?

    // MARK: - Init

    public init(
        apiClient: StudioAPIClientProtocol = StudioAPIClient(),
        supervisor: BackendSupervisor = BackendSupervisor(),
        keychain: KeychainHelperProtocol = KeychainHelper.shared,
        userDefaults: UserDefaults = .standard,
        revealInFinderHandler: RevealInFinderHandler? = nil,
        imagePrefetchHandler: ImagePrefetchHandler? = nil,
        updateService: UpdateService = UpdateService(),
        updateInstallerHandler: UpdateInstallerHandler? = nil,
        terminateAppHandler: TerminateAppHandler? = nil,
        currentVersionProvider: @escaping @Sendable () -> SemanticVersion = { AppMetadata.currentSemanticVersion },
        targetAppBundleProvider: @escaping @Sendable () -> URL? = { UpdateInstaller.currentAppBundleURL() }
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
        self.updateService = updateService
        self.updateInstallerHandler = updateInstallerHandler ?? { plan in
            try UpdateInstaller.launchDetachedInstaller(plan: plan)
        }
        self.terminateAppHandler = terminateAppHandler ?? {
            NSApplication.shared.terminate(nil)
        }
        self.currentVersionProvider = currentVersionProvider
        self.targetAppBundleProvider = targetAppBundleProvider

        let storedTheme = userDefaults.string(forKey: Self.themeDefaultsKey)
        self.activeThemeID = storedTheme.flatMap(StudioThemeID.init(rawValue:)) ?? .cyberNeon
        self.workspacePathOverride = userDefaults.string(forKey: Self.workspaceDefaultsKey) ?? ""
        let savedPort = userDefaults.integer(forKey: Self.preferredPortDefaultsKey)
        self.preferredPort = (1024...65535).contains(savedPort) ? savedPort : 8000

        if userDefaults.object(forKey: Self.autoCheckUpdatesDefaultsKey) != nil {
            self.autoCheckForUpdates = userDefaults.bool(forKey: Self.autoCheckUpdatesDefaultsKey)
        } else {
            self.autoCheckForUpdates = true
        }
        self.includePrereleaseUpdates = userDefaults.bool(forKey: Self.includePrereleaseUpdatesDefaultsKey)
        let savedRepo = userDefaults.string(forKey: Self.updateGitHubRepoDefaultsKey)?
            .trimmingCharacters(in: .whitespacesAndNewlines)
        self.updateGitHubRepository = (savedRepo?.isEmpty == false)
            ? savedRepo!
            : AppMetadata.configuredGitHubRepo
        self.skippedUpdateTag = userDefaults.string(forKey: Self.skippedUpdateTagDefaultsKey) ?? ""

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
        scheduleStartupUpdateCheckIfEnabled()
        await connectAndLoad()
    }

    nonisolated public func shutdownSynchronously() {
        supervisor.terminateOwnedProcessSynchronously()
    }

    // MARK: - Software Updates (GitHub Releases)

    public var availableUpdateInfo: (release: GitHubRelease, version: SemanticVersion, asset: GitHubReleaseAsset?)? {
        if case .available(let release, let latestVersion, let asset) = updateState {
            return (release, latestVersion, asset)
        }
        return nil
    }

    public var hasAvailableUpdate: Bool {
        availableUpdateInfo != nil
    }

    public var isCheckingOrDownloadingUpdate: Bool {
        switch updateState {
        case .checking, .downloading, .installing:
            return true
        default:
            return false
        }
    }

    private func scheduleStartupUpdateCheckIfEnabled() {
        guard autoCheckForUpdates else { return }
        startupUpdateCheckTask?.cancel()
        startupUpdateCheckTask = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 2_500_000_000)
            guard !Task.isCancelled else { return }
            await self?.checkForUpdates(userInitiated: false)
        }
    }

    public func checkForUpdates(userInitiated: Bool = true, presentSheet: Bool = true) async {
        guard !isCheckingOrDownloadingUpdate else {
            if userInitiated && presentSheet {
                showUpdateSheet = true
            }
            return
        }

        if userInitiated {
            if presentSheet {
                showUpdateSheet = true
            }
            updateState = .checking
        }

        let repo = updateGitHubRepository.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            ? AppMetadata.configuredGitHubRepo
            : updateGitHubRepository

        do {
            let outcome = try await updateService.checkForUpdates(
                repository: repo,
                currentVersion: currentVersionProvider(),
                includePrereleases: includePrereleaseUpdates
            )
            switch outcome {
            case .updateAvailable(let release, let latestVersion, let asset):
                if !userInitiated && skippedUpdateTag == release.tagName {
                    return
                }
                updateState = .available(release: release, latestVersion: latestVersion, asset: asset)
                if !userInitiated {
                    statusBannerMessage = "Update v\(latestVersion.description) is available on GitHub Releases."
                }
            case .upToDate(let current, _):
                updateState = .upToDate(current: current, checkedAt: Date())
            }
        } catch {
            if userInitiated {
                updateState = .failed(error.localizedDescription)
            }
        }
    }

    public func skipUpdateVersion(_ tagName: String) {
        skippedUpdateTag = tagName
        updateState = .idle
        showUpdateSheet = false
    }

    /// Downloads the release artifact, verifies SHA-256 against `SHA256SUMS.txt`,
    /// and once downloaded automatically launches the detached updater, shuts down
    /// the local Python backend, and closes the current app to apply the update.
    public func downloadAndInstallUpdate(
        release: GitHubRelease,
        asset: GitHubReleaseAsset,
        autoCloseAndInstall: Bool = true
    ) async {
        updateState = .downloading(release: release, asset: asset, progress: 0.0)
        do {
            let artifact = try await updateService.downloadAndVerify(
                release: release,
                asset: asset,
                progress: { [weak self] ratio in
                    Task { @MainActor [weak self] in
                        guard let self else { return }
                        if case .downloading(let activeRelease, let activeAsset, _) = self.updateState {
                            self.updateState = .downloading(
                                release: activeRelease,
                                asset: activeAsset,
                                progress: ratio
                            )
                        }
                    }
                }
            )

            if autoCloseAndInstall {
                installDownloadedUpdateAndQuit(release: release, artifact: artifact)
            } else {
                updateState = .readyToInstall(release: release, artifact: artifact)
            }
        } catch {
            updateState = .failed(error.localizedDescription)
        }
    }

    public func installDownloadedUpdateAndQuit(
        release: GitHubRelease,
        artifact: DownloadedUpdateArtifact
    ) {
        updateState = .installing(release: release)
        let plan = UpdateInstallPlan(
            downloadedAssetURL: artifact.fileURL,
            targetAppURL: targetAppBundleProvider()
        )
        do {
            try updateInstallerHandler(plan)
            colorizeStreamTask?.cancel()
            batchPollTask?.cancel()
            exportStreamTask?.cancel()
            startupUpdateCheckTask?.cancel()
            shutdownSynchronously()
            terminateAppHandler()
        } catch {
            updateState = .readyToInstall(release: release, artifact: artifact)
            errorMessage = error.localizedDescription
        }
    }

    public func connectAndLoad() async {
        errorMessage = nil
        backendState = .starting(port: preferredPort)

        await supervisor.setStateChangeHandler { [weak self] newState in
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.backendState = newState
                if case .failed = newState {
                    let wasWorking = self.isColorizing || self.isBatchColorizing || self.isImporting || self.isExporting
                    self.batchPollTask?.cancel()
                    self.batchPollTask = nil
                    self.colorizeStreamTask?.cancel()
                    self.isColorizing = false
                    self.isTranslating = false
                    self.batchStatus?.isRunning = false
                    self.backendLogs = await self.supervisor.recentLogs()
                    if wasWorking {
                        self.errorMessage = "Backend engine stopped unexpectedly. All completed pages are saved — click Restart Engine, then click Resume Remaining to continue."
                    } else if case .failed(let reason) = newState {
                        self.errorMessage = reason
                    }
                }
            }
        }

        let hintURL: URL? = workspacePathOverride.isEmpty
            ? nil
            : URL(fileURLWithPath: workspacePathOverride)

        do {
            let url = try await supervisor.start(
                preferredPort: preferredPort,
                workspaceHint: hintURL,
                statusUpdate: { [weak self] message in
                    Task { @MainActor [weak self] in
                        self?.statusBannerMessage = message
                    }
                }
            )
            statusBannerMessage = nil
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

            if let runningBatch = try? await apiClient.fetchBatchStatus(), runningBatch.isRunning {
                self.batchStatus = runningBatch
                self.isColorizing = true
                if let currentSid = runningBatch.currentSessionId {
                    if self.activeSession?.sessionId != currentSid {
                        await self.selectSession(id: currentSid)
                    }
                    self.startColorizeStream(sessionId: currentSid, autoResume: false)
                }
                self.startBatchPollingLoop()
            }
        } catch {
            statusBannerMessage = nil
            backendState = await supervisor.state
            backendLogs = await supervisor.recentLogs()
            errorMessage = error.localizedDescription
        }
    }

    public func restartBackend() async {
        colorizeStreamTask?.cancel()
        batchPollTask?.cancel()
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
            self.isColorizing = detail.isActive || detail.status == "processing" || isBatchColorizing

            if let recommended = detail.recommendedStyle,
               let style = ColorAestheticStyle(rawValue: recommended) {
                colorizeConfig.style = style
            }

            await loadSessionContext(sessionId: id)
            prefetchAdjacentPages()

            if detail.isActive || detail.status == "processing" || batchStatus?.currentSessionId == id {
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

    private static let supportedContainerExtensions: Set<String> = ["pdf", "epub", "zip", "cbz"]
    private static let supportedImageExtensions: Set<String> = ["png", "jpg", "jpeg", "webp", "bmp", "gif", "tiff"]

    public func handleDroppedOrPickedURLs(_ urls: [URL], recursive: Bool = true) async {
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

        directories.sort { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }
        for dir in directories {
            await importDirectory(path: dir.path, recursive: recursive, combineImages: true)
        }
        if !files.isEmpty {
            await uploadFiles(files, combineImages: false)
        }
    }

    public func cancelImport() async {
        importCancelledLocally = true
        importProgressText = "Cancelling import…"
        if let importId = activeImportId, !importId.isEmpty {
            try? await apiClient.cancelImport(importId: importId)
        }
    }

    public func uploadFiles(_ urls: [URL], combineImages: Bool = false) async {
        let supported = Self.supportedContainerExtensions.union(Self.supportedImageExtensions)
        let sortedURLs = urls
            .map(\.standardizedFileURL)
            .filter { supported.contains($0.pathExtension.lowercased()) }
            .sorted { $0.lastPathComponent.localizedStandardCompare($1.lastPathComponent) == .orderedAscending }

        guard !sortedURLs.isEmpty else {
            if !urls.isEmpty {
                errorMessage = "Supported formats: .pdf, .epub, .cbz, .zip, and images (.png, .jpg, .webp)."
            }
            return
        }

        let allImages = sortedURLs.allSatisfy { Self.supportedImageExtensions.contains($0.pathExtension.lowercased()) }
        let effectiveCombineImages = combineImages || (sortedURLs.count > 1 && allImages)

        isImporting = true
        importCancelledLocally = false
        activeImportId = nil
        importProcessedCount = 0
        importTotalCount = sortedURLs.count
        importProgressFraction = 0.0
        importProgressText = "Preparing \(sortedURLs.count) volume\(sortedURLs.count == 1 ? "" : "s")…"
        errorMessage = nil
        defer {
            isImporting = false
            activeImportId = nil
            importProgressText = ""
            importProcessedCount = 0
            importTotalCount = 0
            importProgressFraction = 0.0
        }

        // Fast zero-copy local path import (no multi-GB HTTP multipart duplication, no 60s timeout,
        // live per-volume progress & cancellation via background IMPORT_TASKS).
        do {
            let resp = try await apiClient.importLocalFiles(
                paths: sortedURLs.map(\.path),
                batchId: nil,
                combineImages: effectiveCombineImages
            )
            let finalStatus = try await handleBackgroundImportResponse(
                resp,
                initialTotal: max(resp.totalFiles, sortedURLs.count),
                completionLabel: "Imported"
            )
            if let err = finalStatus.error, !err.isEmpty {
                errorMessage = err
            }
            return
        } catch StudioAPIError.httpError(let code, _) where code == 404 || code == 405 {
            // Older backend without /api/import/files — fall back seamlessly to per-volume chunked uploads.
        } catch {
            // If local path wasn't directly accessible (e.g. remote backend), fall back to chunked HTTP uploads.
            let shouldFallback: Bool
            if case StudioAPIError.httpError(let code, _) = error, code == 400 {
                shouldFallback = true
            } else {
                shouldFallback = false
            }
            if !shouldFallback {
                errorMessage = error.localizedDescription
                return
            }
        }

        await uploadFilesChunkedFallback(sortedURLs, combineImages: effectiveCombineImages)
    }

    private func uploadFilesChunkedFallback(_ sortedURLs: [URL], combineImages: Bool) async {
        // Upload container volumes one-by-one (or grouped loose images as one volume) to avoid
        // huge single multipart payloads and provide smooth per-volume progress & live queue updates.
        let chunks: [[URL]]
        if combineImages {
            chunks = [sortedURLs]
        } else {
            chunks = sortedURLs.map { [$0] }
        }

        importTotalCount = chunks.count
        importProcessedCount = 0
        importProgressFraction = 0.0

        var activeBatchId: String?
        var successCount = 0
        var failCount = 0
        var firstSessionId: String?
        var lastError: String?

        for (index, chunk) in chunks.enumerated() {
            if importCancelledLocally || Task.isCancelled {
                statusBannerMessage = successCount > 0
                    ? "Import cancelled after \(successCount) volume(s)"
                    : "Import cancelled"
                break
            }

            let label = chunk.count == 1
                ? chunk[0].lastPathComponent
                : "\(chunk.count) image pages"
            importProgressText = "Importing \(index + 1)/\(chunks.count): \(label)"

            do {
                let resp = try await apiClient.uploadFiles(
                    fileURLs: chunk,
                    batchId: activeBatchId,
                    combineImages: combineImages
                )
                if !resp.batchId.isEmpty {
                    activeBatchId = resp.batchId
                }
                successCount += max(resp.totalFiles, resp.sessions.count)
                if firstSessionId == nil {
                    firstSessionId = resp.sessions.first?.sessionId ?? (resp.sessionId.isEmpty ? nil : resp.sessionId)
                }
                if !resp.sessions.isEmpty {
                    mergeSessionsIncrementally(resp.sessions)
                }
                if activeSession == nil, let firstId = firstSessionId {
                    await selectSession(id: firstId)
                }
            } catch {
                failCount += chunk.count
                lastError = error.localizedDescription
            }

            importProcessedCount = index + 1
            importProgressFraction = Double(importProcessedCount) / Double(max(1, chunks.count))
        }

        await refreshSessions()
        if activeSession == nil, let targetId = firstSessionId ?? sessions.first?.sessionId {
            await selectSession(id: targetId)
        }

        if successCount > 0 {
            let suffix = failCount > 0 ? " (\(failCount) failed)" : ""
            statusBannerMessage = "Imported \(successCount) volume\(successCount == 1 ? "" : "s")\(suffix)"
        } else if let lastError {
            errorMessage = lastError
        }
    }

    public func importDirectory(
        url: URL,
        recursive: Bool = true,
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
        recursive: Bool = true,
        combineImages: Bool = true
    ) async {
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else {
            errorMessage = "Please choose a valid manga folder path."
            return
        }

        isImporting = true
        importCancelledLocally = false
        activeImportId = nil
        importProcessedCount = 0
        importTotalCount = 0
        importProgressFraction = 0.0
        importProgressText = "Scanning directory…"
        errorMessage = nil
        defer {
            isImporting = false
            activeImportId = nil
            importProgressText = ""
            importProcessedCount = 0
            importTotalCount = 0
            importProgressFraction = 0.0
        }

        do {
            let resp = try await apiClient.importDirectory(
                path: trimmed,
                recursive: recursive,
                combineImages: combineImages
            )
            let finalStatus = try await handleBackgroundImportResponse(
                resp,
                initialTotal: resp.totalFiles,
                completionLabel: "Folder import"
            )
            if let err = finalStatus.error, !err.isEmpty {
                errorMessage = err
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    @discardableResult
    private func handleBackgroundImportResponse(
        _ resp: DirectoryImportResponseDTO,
        initialTotal: Int,
        completionLabel: String
    ) async throws -> DirectoryImportStatusDTO {
        importTotalCount = max(initialTotal, resp.totalFiles)
        var createdIds = resp.createdSessionIds
        var finalStatus = DirectoryImportStatusDTO(
            importId: resp.importId,
            batchId: resp.batchId,
            status: resp.status,
            totalFiles: importTotalCount,
            importedFiles: resp.importedFiles,
            failedFiles: resp.failedFiles,
            processedFiles: resp.processedFiles,
            percent: resp.status == "completed" ? 100 : 0,
            createdSessions: resp.createdSessions,
            createdSessionIds: resp.createdSessionIds
        )

        if resp.status == "started", !resp.importId.isEmpty {
            activeImportId = resp.importId
            var lastImportedCount = 0
            var consecutivePollErrors = 0
            var selectedFirst = (activeSession != nil)

            while !Task.isCancelled {
                try await Task.sleep(nanoseconds: 250_000_000)

                let st: DirectoryImportStatusDTO
                do {
                    st = try await apiClient.fetchImportStatus(importId: resp.importId)
                    consecutivePollErrors = 0
                } catch {
                    consecutivePollErrors += 1
                    if consecutivePollErrors >= 5 {
                        throw error
                    }
                    continue
                }

                finalStatus = st
                let total = max(1, st.totalFiles > 0 ? st.totalFiles : importTotalCount)
                let processed = max(st.processedFiles, st.importedFiles + st.failedFiles)
                importTotalCount = total
                importProcessedCount = min(processed, total)
                importProgressFraction = st.percent > 0
                    ? min(1.0, max(0.0, st.percent / 100.0))
                    : min(1.0, Double(importProcessedCount) / Double(total))

                if let cur = st.currentFile, !cur.isEmpty {
                    importProgressText = "Importing \(min(processed + 1, total))/\(total): \(cur)"
                } else {
                    importProgressText = "Imported \(st.importedFiles)/\(total) volume\(total == 1 ? "" : "s")"
                }

                // Stream completed volumes into the sidebar queue live as they finish
                if st.importedFiles > lastImportedCount {
                    lastImportedCount = st.importedFiles
                    if !st.createdSessions.isEmpty {
                        mergeSessionsIncrementally(st.createdSessions)
                    } else {
                        await refreshSessions()
                    }
                    if !selectedFirst, let firstId = st.createdSessionIds.first ?? st.createdSessions.first?.sessionId {
                        selectedFirst = true
                        await selectSession(id: firstId)
                    }
                }

                if st.status == "completed" || st.status == "cancelled" || st.status == "failed" || st.status == "error" {
                    createdIds = st.createdSessionIds
                    break
                }
            }
        } else if !resp.createdSessions.isEmpty {
            mergeSessionsIncrementally(resp.createdSessions)
        }

        await refreshSessions()
        if activeSession == nil, let firstId = createdIds.first ?? sessions.first?.sessionId {
            await selectSession(id: firstId)
        }

        if finalStatus.status == "cancelled" {
            statusBannerMessage = "\(completionLabel) cancelled (\(finalStatus.importedFiles) imported)"
        } else if finalStatus.importedFiles > 0 {
            let failSuffix = finalStatus.failedFiles > 0 ? " (\(finalStatus.failedFiles) failed)" : ""
            statusBannerMessage = "Imported \(finalStatus.importedFiles) volume\(finalStatus.importedFiles == 1 ? "" : "s")\(failSuffix)"
        } else if finalStatus.status == "completed" {
            statusBannerMessage = "\(completionLabel) completed"
        }

        return finalStatus
    }

    private func mergeSessionsIncrementally(_ incoming: [MangaSessionSummary]) {
        guard !incoming.isEmpty else { return }
        var byId: [String: MangaSessionSummary] = Dictionary(
            uniqueKeysWithValues: sessions.map { ($0.sessionId, $0) }
        )
        for item in incoming {
            byId[item.sessionId] = item
        }
        sessions = byId.values.sorted {
            $0.filename.localizedStandardCompare($1.filename) == .orderedAscending
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

    /// Volumes in the queue that still have uncolorized pages.
    public var incompleteSessions: [MangaSessionSummary] {
        sessions.filter { summary in
            if summary.totalPages > 0 {
                return summary.processedCount < summary.totalPages
            }
            return summary.status != "completed"
        }
    }

    /// True when some queued volumes are already completed and others still have pages remaining.
    public var hasCompletedAndIncompleteVolumes: Bool {
        let remaining = incompleteSessions.count
        return remaining > 0 && remaining < sessions.count
    }

    /// Ordered list of session IDs that "Colorize All / Resume Remaining / Checked" will process.
    /// Preserves the Document Queue order (never arbitrary Set iteration order).
    /// When no checkboxes are selected and some volumes are already complete, targets only the
    /// remaining incomplete volumes so progress counters and resuming stay crisp.
    public var batchTargetSessionIds: [String] {
        if !selectedSessionIds.isEmpty {
            return sessions.map(\.sessionId).filter { selectedSessionIds.contains($0) }
        }
        if hasCompletedAndIncompleteVolumes {
            return incompleteSessions.map(\.sessionId)
        }
        return sessions.map(\.sessionId)
    }

    public var isBatchColorizing: Bool {
        batchStatus?.isRunning == true
    }

    public var hasPartialVolumeSelection: Bool {
        !selectedSessionIds.isEmpty && selectedSessionIds.count < sessions.count
    }

    public func cancelColorization() async {
        let wasBatch = isBatchColorizing
        let targetSessionId = batchStatus?.currentSessionId ?? activeSession?.sessionId
        batchPollTask?.cancel()
        batchPollTask = nil
        colorizeStreamTask?.cancel()

        do {
            if wasBatch {
                do {
                    try await apiClient.cancelBatchColorize()
                } catch {
                    // Fallback for older backend versions without /api/colorize/batch/cancel
                    if let sid = targetSessionId {
                        try await apiClient.cancelColorize(sessionId: sid)
                    }
                }
                batchStatus?.isRunning = false
            } else if let sessionId = targetSessionId {
                try await apiClient.cancelColorize(sessionId: sessionId)
            }
            isColorizing = false
            colorizeProgressMessage = "Cancelled"
            await refreshSessions()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    public func startBatchColorization() async {
        let targets = batchTargetSessionIds
        guard !targets.isEmpty else { return }
        errorMessage = nil
        isColorizing = true

        do {
            var reqConfig = colorizeConfig
            reqConfig.apiKey = geminiAPIKey
            try await apiClient.startBatchColorize(sessionIds: targets, config: reqConfig)

            let fetched = try? await apiClient.fetchBatchStatus()
            let initialBatch = fetched ?? BatchStatusDTO(
                isRunning: true,
                totalDocs: targets.count,
                completedDocs: 0,
                currentIndex: 0,
                currentSessionId: targets.first,
                sessionIds: targets
            )
            batchStatus = initialBatch
            colorizeProgressMessage = "Colorizing batch (1/\(targets.count) volumes)…"

            let streamTargetId = initialBatch.currentSessionId ?? targets.first
            if let streamTargetId {
                if activeSession?.sessionId != streamTargetId {
                    await selectSession(id: streamTargetId)
                }
                startColorizeStream(sessionId: streamTargetId, autoResume: false)
            }
            startBatchPollingLoop()
        } catch {
            isColorizing = false
            errorMessage = error.localizedDescription
        }
    }

    private func startBatchPollingLoop() {
        batchPollTask?.cancel()
        batchPollTask = Task { [weak self] in
            guard let self else { return }
            var lastTrackedSessionId = self.batchStatus?.currentSessionId
            var consecutivePollFailures = 0

            while !Task.isCancelled {
                try? await Task.sleep(nanoseconds: 1_200_000_000)
                if Task.isCancelled { break }

                let status: BatchStatusDTO
                do {
                    status = try await self.apiClient.fetchBatchStatus()
                    consecutivePollFailures = 0
                } catch {
                    consecutivePollFailures += 1
                    if consecutivePollFailures >= 3 {
                        self.backendState = await self.supervisor.state
                        self.backendLogs = await self.supervisor.recentLogs()
                        self.isColorizing = false
                        self.isTranslating = false
                        self.batchStatus?.isRunning = false
                        self.errorMessage = "Lost connection to local backend engine. All completed pages are saved — click Restart Engine, then click Resume Remaining to continue."
                        break
                    }
                    continue
                }
                self.batchStatus = status
                await self.refreshSessions()

                if status.isRunning {
                    self.isColorizing = true
                    if let nextSid = status.currentSessionId, nextSid != lastTrackedSessionId {
                        lastTrackedSessionId = nextSid
                        if self.activeSession?.sessionId != nextSid {
                            await self.selectSession(id: nextSid)
                        }
                        self.startColorizeStream(sessionId: nextSid, autoResume: false)
                    }
                } else {
                    self.isColorizing = false
                    self.isTranslating = false
                    if let activeId = self.activeSession?.sessionId {
                        await self.selectSession(id: activeId)
                    }
                    let doneCount = max(status.completedDocs, status.totalDocs)
                    if doneCount > 0 {
                        self.statusBannerMessage = "Completed batch colorization (\(doneCount) volume\(doneCount == 1 ? "" : "s"))"
                    }
                    break
                }
            }
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
                if !self.isBatchColorizing {
                    self.isColorizing = false
                    self.isTranslating = false
                }
            } catch is CancellationError {
                if !self.isBatchColorizing {
                    self.isColorizing = false
                    self.isTranslating = false
                }
            } catch {
                if !self.isBatchColorizing {
                    self.isColorizing = false
                    self.isTranslating = false
                    self.errorMessage = error.localizedDescription
                }
            }
        }
    }

    public func handleSSEColorizeEvent(_ event: SSEColorizeEvent) {
        switch event {
        case .initial(let session, let isActive, _):
            if let session, activeSession?.sessionId == session.sessionId {
                activeSession = session
            }
            isColorizing = isActive || isBatchColorizing

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
            if !isBatchColorizing {
                isColorizing = false
                isTranslating = false
            }
            if var sess = activeSession {
                sess.status = "completed"
                sess.processedCount = totalProcessed
                activeSession = sess
                syncSummaryFromActiveSession()
            }
            colorizeProgressMessage = message ?? "Completed \(totalProcessed) pages"
            if !isBatchColorizing {
                statusBannerMessage = colorizeProgressMessage
            }

        case .idle(let totalProcessed, _):
            if !isBatchColorizing {
                isColorizing = false
                isTranslating = false
            }
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
            batchPollTask?.cancel()
            batchPollTask = nil
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
