import XCTest
@testable import KobeanMangaCore

@MainActor
final class StudioStoreTests: XCTestCase {
    private func makeIsolatedDefaults() -> UserDefaults {
        let suiteName = "ai.kobean.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)
        return defaults
    }

    func testSessionLoadAndPageSelectionHelpers() async throws {
        let mockAPI = MockStudioAPIClient()
        mockAPI.sessionsToReturn = [
            MangaSessionSummary(
                sessionId: "s1",
                filename: "Dr_Slump_v01.cbz",
                ext: ".cbz",
                totalPages: 3,
                processedCount: 1,
                status: "pending",
                isActive: false
            )
        ]
        mockAPI.sessionDetailToReturn = MangaSessionDetail(
            sessionId: "s1",
            filename: "Dr_Slump_v01.cbz",
            ext: ".cbz",
            totalPages: 3,
            processedCount: 1,
            status: "pending",
            pages: [
                MangaPageInfo(index: 0, filename: "p1.jpg", status: "colorized"),
                MangaPageInfo(index: 1, filename: "p2.jpg", status: "pending"),
                MangaPageInfo(index: 2, filename: "p3.jpg", status: "pending")
            ]
        )

        let defaults = makeIsolatedDefaults()
        let keychain = KeychainHelper(inMemory: true)
        let store = StudioStore(
            apiClient: mockAPI,
            supervisor: BackendSupervisor(),
            keychain: keychain,
            userDefaults: defaults
        )

        await store.refreshSessions()
        XCTAssertEqual(store.sessions.count, 1)

        await store.selectSession(id: "s1")
        XCTAssertEqual(store.activeSession?.sessionId, "s1")
        XCTAssertEqual(store.activeSession?.pages.count, 3)

        store.deselectAllPages()
        XCTAssertTrue(store.selectedPageIndices.isEmpty)
        XCTAssertFalse(store.canStartColorize)

        store.selectUncolorizedPages()
        XCTAssertEqual(store.selectedPageIndices, [1, 2])
        XCTAssertTrue(store.canStartColorize)

        store.togglePageSelection(1)
        XCTAssertEqual(store.selectedPageIndices, [2])

        store.selectAllPages()
        XCTAssertEqual(store.selectedPageIndices, [0, 1, 2])
    }

    func testComparatorClampingZoomAndNavigation() async {
        let mockAPI = MockStudioAPIClient()
        mockAPI.sessionDetailToReturn = MangaSessionDetail(
            sessionId: "s1",
            filename: "Test.cbz",
            ext: ".cbz",
            totalPages: 2,
            processedCount: 0,
            status: "idle",
            pages: [
                MangaPageInfo(index: 0, filename: "p1.jpg", status: "pending"),
                MangaPageInfo(index: 1, filename: "p2.jpg", status: "pending")
            ]
        )

        let store = StudioStore(
            apiClient: mockAPI,
            supervisor: BackendSupervisor(),
            keychain: KeychainHelper(inMemory: true),
            userDefaults: makeIsolatedDefaults()
        )
        await store.selectSession(id: "s1")

        store.setSplitRatio(1.5)
        XCTAssertEqual(store.splitRatio, 0.98, accuracy: 0.0001)

        store.setSplitRatio(-0.5)
        XCTAssertEqual(store.splitRatio, 0.02, accuracy: 0.0001)

        store.zoomScale = 10.0
        XCTAssertEqual(store.zoomScale, 5.0, accuracy: 0.0001)

        store.zoomScale = 0.05
        XCTAssertEqual(store.zoomScale, 0.25, accuracy: 0.0001)

        store.resetZoom()
        XCTAssertEqual(store.zoomScale, 1.0, accuracy: 0.0001)
        store.toggleDoubleClickZoom()
        XCTAssertEqual(store.zoomScale, 2.0, accuracy: 0.0001)

        XCTAssertEqual(store.activePageIndex, 0)
        store.nextPage()
        XCTAssertEqual(store.activePageIndex, 1)
        store.nextPage()
        XCTAssertEqual(store.activePageIndex, 1)
        store.previousPage()
        XCTAssertEqual(store.activePageIndex, 0)

        store.comparatorMode = .originalOnly
        XCTAssertEqual(store.comparatorMode, .originalOnly)
        store.toggleThumbnailStrip()
        XCTAssertFalse(store.showThumbnailStrip)
        store.toggleFullscreenComparator()
        XCTAssertTrue(store.isFullscreenComparator)
    }

    func testThemePersistenceAndKeychainSecretIsolation() {
        let defaults = makeIsolatedDefaults()
        let keychain = KeychainHelper(inMemory: true)

        let store = StudioStore(
            apiClient: MockStudioAPIClient(),
            supervisor: BackendSupervisor(),
            keychain: keychain,
            userDefaults: defaults
        )

        store.setTheme(.paperStudio)
        XCTAssertEqual(store.activeThemeID, .paperStudio)
        XCTAssertEqual(defaults.string(forKey: "kobean_theme"), "paper-studio")

        store.saveGeminiAPIKey("AIzaTestSecretKey999")
        XCTAssertEqual(store.geminiAPIKey, "AIzaTestSecretKey999")
        XCTAssertEqual(keychain.read(key: KeychainHelper.geminiAPIKeyAccount), "AIzaTestSecretKey999")
        // Verify T-01: API key must never be persisted to UserDefaults
        for (k, v) in defaults.dictionaryRepresentation() {
            if let str = v as? String {
                XCTAssertFalse(str.contains("AIzaTestSecretKey999"), "Secret leaked into UserDefaults key \(k)")
            }
        }
    }

    func testSSEPageUpdateAndPreviewAndFinderReveal() async {
        let mockAPI = MockStudioAPIClient()
        mockAPI.sessionDetailToReturn = MangaSessionDetail(
            sessionId: "s1",
            filename: "One_Piece_v01.cbz",
            ext: ".cbz",
            totalPages: 2,
            processedCount: 0,
            status: "idle",
            pages: [
                MangaPageInfo(index: 0, filename: "p1.jpg", status: "pending"),
                MangaPageInfo(index: 1, filename: "p2.jpg", status: "pending")
            ]
        )

        var revealedURLs: [URL] = []
        let store = StudioStore(
            apiClient: mockAPI,
            supervisor: BackendSupervisor(),
            keychain: KeychainHelper(inMemory: true),
            userDefaults: makeIsolatedDefaults(),
            revealInFinderHandler: { url in revealedURLs.append(url) }
        )

        await store.selectSession(id: "s1")
        await store.previewCurrentPage()

        XCTAssertEqual(store.activeSession?.pages[0].status, "colorized")
        XCTAssertGreaterThan(store.cacheBusterVersion, 0)

        let update = SSEColorizeEvent.pageUpdate(
            PageUpdatePayload(
                pageIndex: 1,
                status: "colorized",
                skippedColored: false,
                colorizedUrl: "/api/session/s1/image/colorized/p2.jpg",
                engine: "ResNeXt",
                adapterUsed: true,
                autoHarvested: true,
                processedCount: 2,
                total: 2
            )
        )
        store.handleSSEColorizeEvent(update)
        XCTAssertEqual(store.activeSession?.pages[1].status, "colorized")
        XCTAssertTrue(store.activeSession?.pages[1].adapterUsed ?? false)
        XCTAssertEqual(store.activeSession?.processedCount, 2)

        store.handleSSEColorizeEvent(.completed(totalProcessed: 2, message: "Done"))
        XCTAssertFalse(store.isColorizing)
        XCTAssertEqual(store.activeSession?.status, "completed")

        let unnormalized = URL(fileURLWithPath: "/tmp/foo/../bar/export.epub")
        store.revealInFinder(unnormalized)
        XCTAssertEqual(revealedURLs.first?.path, "/tmp/bar/export.epub")
    }

    func testBackendSupervisorAttachesToExistingWithoutKilling() async throws {
        let supervisor = BackendSupervisor { port in
            HealthStatus(
                status: "ok",
                service: "kobean-manga-colorizer",
                version: "1.0.0",
                activeColorizationTasks: 0,
                batchRunning: false,
                totalSessions: 1
            )
        }
        let url = try await supervisor.start(preferredPort: 8123)
        XCTAssertEqual(url.absoluteString, "http://127.0.0.1:8123")
        let runningState = await supervisor.state
        XCTAssertEqual(runningState, .running(port: 8123, attachedToExisting: true))

        await supervisor.stop()
        let stoppedState = await supervisor.state
        XCTAssertEqual(stoppedState, .stopped)

        let freePort = BackendSupervisor.findAvailableLocalPort()
        XCTAssertNotNil(freePort)
        if let freePort {
            XCTAssertTrue(BackendSupervisor.isLocalPortAvailable(freePort))
        }

        let runner = BackendSupervisor.PythonRunner(
            executableURL: URL(fileURLWithPath: "/usr/bin/python3"),
            baseArguments: [],
            mainPyPath: "/path with spaces/main.py"
        )
        XCTAssertEqual(
            runner.arguments(port: 8000),
            ["/path with spaces/main.py", "--host", "127.0.0.1", "--port", "8000", "--no-open"]
        )
    }

    func testStudioAPIClientImageURLAndHTTPDecoding() async throws {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.protocolClasses = [StubURLProtocol.self]
        let stubSession = URLSession(configuration: cfg)
        let client = StudioAPIClient(baseURL: URL(string: "http://127.0.0.1:8000")!, session: stubSession)

        let imgURL = client.imageURL(relativePath: "/api/session/s1/image/colorized/p1.jpg", cacheBuster: "42")
        XCTAssertEqual(imgURL?.absoluteString, "http://127.0.0.1:8000/api/session/s1/image/colorized/p1.jpg?t=42")

        StubURLProtocol.handler = { _ in
            let data = #"{"detail":"Session not found"}"#.data(using: .utf8)!
            let resp = HTTPURLResponse(
                url: URL(string: "http://127.0.0.1:8000/api/session/missing")!,
                statusCode: 404,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (resp, data)
        }

        do {
            _ = try await client.fetchSession(id: "missing")
            XCTFail("Expected HTTP 404 error")
        } catch let error as StudioAPIError {
            XCTAssertEqual(error, .httpError(statusCode: 404, detail: "Session not found"))
        }
    }

    func testPaletteSeriesMemoryAndLoRAAdapterFlows() async {
        let mockAPI = MockStudioAPIClient()
        mockAPI.sessionDetailToReturn = MangaSessionDetail(
            sessionId: "s1",
            filename: "Dr_Slump_v01.cbz",
            ext: ".cbz",
            totalPages: 1,
            processedCount: 1,
            status: "completed",
            pages: [MangaPageInfo(index: 0, filename: "p1.jpg", status: "colorized")],
            detectedPreset: "dr_slump"
        )
        mockAPI.recognizedCharactersToReturn = [
            RecognizedCharacterDTO(name: "Arale Norimaki", confidence: 0.95)
        ]

        let store = StudioStore(
            apiClient: mockAPI,
            supervisor: BackendSupervisor(),
            keychain: KeychainHelper(inMemory: true),
            userDefaults: makeIsolatedDefaults()
        )
        await store.selectSession(id: "s1")

        await store.applyPreset(presetId: "dr_slump")
        XCTAssertEqual(store.activePalette.presetId, "dr_slump")

        let char = CharacterEntryDTO(name: "Arale Norimaki", hairHex: "#8B2BE2")
        await store.upsertCharacter(char)
        XCTAssertEqual(store.activePalette.characters.count, 1)

        await store.recognizeCurrentPageCharacters()
        XCTAssertEqual(store.currentPage?.recognizedCharacters.first?.name, "Arale Norimaki")

        await store.learnCurrentPageToSeriesMemory()
        XCTAssertTrue(store.currentPage?.learnedToMemory ?? false)

        await store.trainSeriesAdapter(steps: 50, lr: 1e-4)
        XCTAssertEqual(store.adapterStatus?.status, "training_started")

        let updatedSettings = AutoRefineSettingsDTO(
            seriesKey: "one_piece",
            autoRefineEnabled: false,
            autoHarvestThreshold: 0.9,
            autoRefineInterval: 10
        )
        await store.updateAutoRefineSettings(updatedSettings)
        XCTAssertEqual(store.autoRefineSettings?.autoRefineEnabled, false)
        XCTAssertEqual(store.autoRefineSettings?.autoHarvestThreshold ?? 0, 0.9, accuracy: 0.001)

        await store.deleteCharacter(name: "Arale Norimaki")
        XCTAssertTrue(store.activePalette.characters.isEmpty)
    }

    func testOmnibusExportStreamDownloadsFile() async {
        let mockAPI = MockStudioAPIClient()
        mockAPI.sessionsToReturn = [
            MangaSessionSummary(sessionId: "s1", filename: "Vol1.cbz", totalPages: 2, processedCount: 2, status: "completed")
        ]
        mockAPI.combinedExportEventsToStream = [
            .initial(jobId: "job1", status: "processing", progress: CombinedProgressPayload(jobId: "job1", percent: 0, processedPages: 0, totalPages: 2, status: "Starting")),
            .progress(CombinedProgressPayload(jobId: "job1", percent: 50, processedPages: 1, totalPages: 2, status: "Volume 1/1: Page 1")),
            .completed(jobId: "job1", downloadUrl: "/api/download/combined/Vol1.epub", filename: "Vol1.epub", totalVolumes: 1, title: "Vol1")
        ]

        let tempDir = FileManager.default.temporaryDirectory.appendingPathComponent("kobean-export-test-\(UUID().uuidString)")
        let store = StudioStore(
            apiClient: mockAPI,
            supervisor: BackendSupervisor(),
            keychain: KeychainHelper(inMemory: true),
            userDefaults: makeIsolatedDefaults()
        )
        await store.refreshSessions()
        await store.startCombinedOmnibusExport(saveToDirectory: tempDir)

        for _ in 0..<20 where store.isExporting {
            try? await Task.sleep(nanoseconds: 25_000_000)
        }

        XCTAssertFalse(store.isExporting)
        XCTAssertEqual(store.combinedExportPercent, 100)
        XCTAssertEqual(store.lastDownloadedFileURL?.lastPathComponent, "Vol1.epub")
    }

    func testPageGalleryFilterAndStoreConvenienceActions() async {
        let mockAPI = MockStudioAPIClient()
        mockAPI.sessionsToReturn = [
            MangaSessionSummary(sessionId: "s1", filename: "Vol1.cbz", totalPages: 3, processedCount: 2, status: "pending")
        ]
        mockAPI.sessionDetailToReturn = MangaSessionDetail(
            sessionId: "s1",
            filename: "Vol1.cbz",
            ext: ".cbz",
            totalPages: 3,
            processedCount: 2,
            status: "pending",
            pages: [
                MangaPageInfo(index: 0, filename: "p1.jpg", status: "colorized", translated: true),
                MangaPageInfo(index: 1, filename: "p2.jpg", status: "colorized", translated: false),
                MangaPageInfo(index: 2, filename: "p3.jpg", status: "pending", translated: false)
            ]
        )

        let store = StudioStore(
            apiClient: mockAPI,
            supervisor: BackendSupervisor { _ in
                HealthStatus(status: "ok", service: "kobean-manga-colorizer", version: "1.0.0")
            },
            keychain: KeychainHelper(inMemory: true),
            userDefaults: makeIsolatedDefaults()
        )
        XCTAssertEqual(store.currentTheme.id, store.activeTheme.id)

        await store.selectSession(id: "s1")

        store.pageGalleryFilter = .all
        XCTAssertEqual(store.filteredPages.map(\.index), [0, 1, 2])

        store.pageGalleryFilter = .colorized
        XCTAssertEqual(store.filteredPages.map(\.index), [0, 1])

        store.pageGalleryFilter = .uncolorized
        XCTAssertEqual(store.filteredPages.map(\.index), [2])

        store.pageGalleryFilter = .translated
        XCTAssertEqual(store.filteredPages.map(\.index), [0])

        store.toggleSessionSelection("s1")
        XCTAssertEqual(store.selectedSessionIds, ["s1"])
        store.toggleSessionSelection("s1")
        XCTAssertTrue(store.selectedSessionIds.isEmpty)

        await store.learnCurrentPage()
        XCTAssertTrue(store.currentPage?.learnedToMemory ?? false)

        await store.startOrResumeColorization()
        for _ in 0..<20 where store.isColorizing {
            try? await Task.sleep(nanoseconds: 10_000_000)
        }
        XCTAssertFalse(store.isColorizing) // stream finishes cleanly and clears busy flag

        await store.importDirectory(url: URL(fileURLWithPath: "/tmp/manga_folder"))
        XCTAssertTrue(
            store.statusBannerMessage?.contains("Imported") == true
                || store.statusBannerMessage?.contains("Folder import") == true
        )

        store.shutdownSynchronously()
    }

    func testBulkImport18VolumesUsesLocalAsyncImportWithLiveProgressAndStreaming() async {
        let mockAPI = MockStudioAPIClient()
        let eighteenURLs = (1...18).reversed().map { idx in
            URL(fileURLWithPath: "/tmp/manga/Dr_Slump_Vol_\(idx).cbz")
        }

        // Simulate progressive background import over 3 status polls: 6 -> 12 -> 18 volumes
        let allSummaries = (1...18).map { idx in
            MangaSessionSummary(
                sessionId: "vol-\(idx)",
                filename: "Dr_Slump_Vol_\(idx).cbz",
                ext: ".cbz",
                totalPages: 180,
                processedCount: 0,
                status: "idle"
            )
        }
        mockAPI.importLocalFilesResponse = DirectoryImportResponseDTO(
            status: "started",
            importId: "imp-18",
            batchId: "batch-18",
            totalFiles: 18,
            totalScannedFiles: 18
        )
        mockAPI.importStatusSequence = [
            DirectoryImportStatusDTO(
                importId: "imp-18",
                batchId: "batch-18",
                status: "running",
                totalFiles: 18,
                importedFiles: 6,
                failedFiles: 0,
                processedFiles: 6,
                currentFile: "Dr_Slump_Vol_7.cbz",
                percent: 33.3,
                createdSessions: Array(allSummaries.prefix(6)),
                createdSessionIds: allSummaries.prefix(6).map(\.sessionId)
            ),
            DirectoryImportStatusDTO(
                importId: "imp-18",
                batchId: "batch-18",
                status: "running",
                totalFiles: 18,
                importedFiles: 12,
                failedFiles: 0,
                processedFiles: 12,
                currentFile: "Dr_Slump_Vol_13.cbz",
                percent: 66.7,
                createdSessions: Array(allSummaries.prefix(12)),
                createdSessionIds: allSummaries.prefix(12).map(\.sessionId)
            ),
            DirectoryImportStatusDTO(
                importId: "imp-18",
                batchId: "batch-18",
                status: "completed",
                totalFiles: 18,
                importedFiles: 18,
                failedFiles: 0,
                processedFiles: 18,
                currentFile: nil,
                percent: 100.0,
                createdSessions: allSummaries,
                createdSessionIds: allSummaries.map(\.sessionId)
            ),
        ]
        mockAPI.sessionsToReturn = allSummaries

        let store = StudioStore(
            apiClient: mockAPI,
            supervisor: BackendSupervisor(),
            keychain: KeychainHelper(inMemory: true),
            userDefaults: makeIsolatedDefaults()
        )

        await store.uploadFiles(eighteenURLs)

        // Must use fast zero-copy /api/import/files instead of 1 giant multipart HTTP upload
        XCTAssertEqual(mockAPI.importLocalFilesCalledPaths.count, 18)
        XCTAssertEqual(mockAPI.uploadFilesCallCount, 0)
        // Must naturally sort Vol_1 before Vol_2 and Vol_10
        XCTAssertEqual(
            URL(fileURLWithPath: mockAPI.importLocalFilesCalledPaths[0]).lastPathComponent,
            "Dr_Slump_Vol_1.cbz"
        )
        XCTAssertEqual(
            URL(fileURLWithPath: mockAPI.importLocalFilesCalledPaths[1]).lastPathComponent,
            "Dr_Slump_Vol_2.cbz"
        )
        XCTAssertEqual(
            URL(fileURLWithPath: mockAPI.importLocalFilesCalledPaths[17]).lastPathComponent,
            "Dr_Slump_Vol_18.cbz"
        )
        XCTAssertEqual(store.sessions.count, 18)
        XCTAssertFalse(store.isImporting)
        XCTAssertNil(store.errorMessage)
        XCTAssertEqual(store.statusBannerMessage, "Imported 18 volumes")
    }

    func testBulkImport18VolumesFallsBackToPerVolumeChunkedUploadsWhenEndpointMissing() async {
        let mockAPI = MockStudioAPIClient()
        mockAPI.importLocalFilesError = StudioAPIError.httpError(statusCode: 404, detail: "Not Found")

        let eighteenURLs = (1...18).map { idx in
            URL(fileURLWithPath: "/tmp/manga/Vol_\(idx).pdf")
        }

        let store = StudioStore(
            apiClient: mockAPI,
            supervisor: BackendSupervisor(),
            keychain: KeychainHelper(inMemory: true),
            userDefaults: makeIsolatedDefaults()
        )

        await store.uploadFiles(eighteenURLs)

        // Must chunk into 18 single-volume HTTP requests (1 per volume), never 1 giant 18-volume request
        XCTAssertEqual(mockAPI.uploadFilesCallCount, 18)
        XCTAssertTrue(mockAPI.uploadFilesBatchSizes.allSatisfy { $0 == 1 })
        XCTAssertFalse(store.isImporting)
        XCTAssertNil(store.errorMessage)
        XCTAssertEqual(store.statusBannerMessage, "Imported 18 volumes")
    }

    func testAPIClientRequestTimeoutOverridesFoundation60SecondDefault() async throws {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = 300
        cfg.protocolClasses = [StubURLProtocol.self]
        let stubSession = URLSession(configuration: cfg)
        let client = StudioAPIClient(baseURL: URL(string: "http://127.0.0.1:8000")!, session: stubSession)

        var observedTimeout: TimeInterval = 0
        StubURLProtocol.handler = { req in
            observedTimeout = req.timeoutInterval
            let data = #"{"sessions":[]}"#.data(using: .utf8)!
            let resp = HTTPURLResponse(
                url: req.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: ["Content-Type": "application/json"]
            )!
            return (resp, data)
        }

        _ = try await client.fetchSessions()
        XCTAssertGreaterThanOrEqual(observedTimeout, 300.0)
    }

    func testLocateWorkspaceRootHonorsInfoDictionaryWorkspacePath() throws {
        let tempDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("kobean-ws-test-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: tempDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tempDir) }

        let mainPy = tempDir.appendingPathComponent("main.py")
        FileManager.default.createFile(atPath: mainPy.path, contents: Data("# test\n".utf8))

        let resolved = BackendSupervisor.locateWorkspaceRoot(
            hint: nil,
            infoDictionaryWorkspacePath: tempDir.path
        )
        XCTAssertEqual(resolved?.standardizedFileURL, tempDir.standardizedFileURL)
    }

    func testImageCacheKeyAndThumbnailDownsampling() throws {
        let sampleURL = URL(string: "http://127.0.0.1:8000/api/session/s1/image/original/p1.png")!
        XCTAssertEqual(
            StudioImageCache.cacheKey(for: sampleURL, maxPixelDimension: nil),
            sampleURL.absoluteString
        )
        XCTAssertEqual(
            StudioImageCache.cacheKey(for: sampleURL, maxPixelDimension: 240),
            "\(sampleURL.absoluteString)#240"
        )

        // Create a 600x800 PNG in memory and downsample to maxPixelDimension = 200
        let rep = NSBitmapImageRep(
            bitmapDataPlanes: nil,
            pixelsWide: 600,
            pixelsHigh: 800,
            bitsPerSample: 8,
            samplesPerPixel: 4,
            hasAlpha: true,
            isPlanar: false,
            colorSpaceName: .deviceRGB,
            bytesPerRow: 0,
            bitsPerPixel: 0
        )!
        let pngData = rep.representation(using: .png, properties: [:])!
        let thumb = try XCTUnwrap(StudioImageCache.decodeImage(data: pngData, maxPixelDimension: 200))
        XCTAssertLessThanOrEqual(max(thumb.size.width, thumb.size.height), 200)
        XCTAssertGreaterThan(thumb.size.height, thumb.size.width)
    }

    func testAdjacentPagePrefetchOnNavigation() async {
        let mockAPI = MockStudioAPIClient()
        mockAPI.sessionDetailToReturn = MangaSessionDetail(
            sessionId: "s1",
            filename: "Vol1.cbz",
            ext: ".cbz",
            totalPages: 4,
            processedCount: 1,
            status: "pending",
            pages: [
                MangaPageInfo(index: 0, filename: "p1.jpg", colorizedUrl: "/api/session/s1/image/colorized/p1.jpg", status: "colorized"),
                MangaPageInfo(index: 1, filename: "p2.jpg", status: "pending"),
                MangaPageInfo(index: 2, filename: "p3.jpg", status: "pending"),
                MangaPageInfo(index: 3, filename: "p4.jpg", status: "pending")
            ]
        )

        var prefetchedBatches: [[URL]] = []
        let store = StudioStore(
            apiClient: mockAPI,
            supervisor: BackendSupervisor(),
            keychain: KeychainHelper(inMemory: true),
            userDefaults: makeIsolatedDefaults(),
            imagePrefetchHandler: { urls in
                prefetchedBatches.append(urls)
            }
        )

        await store.selectSession(id: "s1")
        prefetchedBatches.removeAll()

        store.selectPage(at: 1)
        let lastBatch = prefetchedBatches.last ?? []
        let paths = Set(lastBatch.map(\.path))
        XCTAssertTrue(paths.contains("/api/session/s1/image/original/p1.jpg"))
        XCTAssertTrue(paths.contains("/api/session/s1/image/colorized/p1.jpg"))
        XCTAssertTrue(paths.contains("/api/session/s1/image/original/p3.jpg"))

        store.nextPage()
        let nextPaths = Set((prefetchedBatches.last ?? []).map(\.path))
        XCTAssertTrue(nextPaths.contains("/api/session/s1/image/original/p2.jpg"))
        XCTAssertTrue(nextPaths.contains("/api/session/s1/image/original/p4.jpg"))

        store.previousPage()
        let prevPaths = Set((prefetchedBatches.last ?? []).map(\.path))
        XCTAssertTrue(prevPaths.contains("/api/session/s1/image/original/p1.jpg"))
        XCTAssertTrue(prevPaths.contains("/api/session/s1/image/original/p3.jpg"))
    }

    func testDebouncedPreferencesPersistence() async {
        let defaults = makeIsolatedDefaults()
        let store = StudioStore(
            apiClient: MockStudioAPIClient(),
            supervisor: BackendSupervisor(),
            keychain: KeychainHelper(inMemory: true),
            userDefaults: defaults
        )

        store.colorizeConfig.saturation = 1.45
        store.persistColorizePreferences(immediate: false)
        // Not written synchronously yet before 250ms debounce fires
        XCTAssertNil(defaults.data(forKey: "kobean_colorize_settings"))

        try? await Task.sleep(nanoseconds: 350_000_000)
        XCTAssertNotNil(defaults.data(forKey: "kobean_colorize_settings"))

        store.colorizeConfig.saturation = 1.85
        store.persistColorizePreferences(immediate: true)
        let flushedData = defaults.data(forKey: "kobean_colorize_settings")
        XCTAssertNotNil(flushedData)
    }

    func testStudioAPIClientSessionCacheAndPipeliningConfiguration() {
        let client = StudioAPIClient()
        let cfg = client.sessionConfigurationSnapshot
        XCTAssertEqual(cfg.httpMaximumConnectionsPerHost, 8)
        XCTAssertEqual(cfg.urlCache?.memoryCapacity, 64 * 1024 * 1024)
        XCTAssertEqual(cfg.urlCache?.diskCapacity, 256 * 1024 * 1024)
    }
}

private final class StubURLProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = Self.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        do {
            let (resp, data) = try handler(request)
            client?.urlProtocol(self, didReceive: resp, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

private final class MockStudioAPIClient: StudioAPIClientProtocol, @unchecked Sendable {
    var sessionsToReturn: [MangaSessionSummary] = []
    var recognizedCharactersToReturn: [RecognizedCharacterDTO] = []
    var combinedExportEventsToStream: [SSECombinedExportEvent] = []
    var importLocalFilesResponse: DirectoryImportResponseDTO?
    var importLocalFilesError: Error?
    var importLocalFilesCalledPaths: [String] = []
    var importStatusSequence: [DirectoryImportStatusDTO] = []
    var importStatusPollIndex: Int = 0
    var cancelledImportIds: [String] = []
    var uploadFilesCallCount: Int = 0
    var uploadFilesBatchSizes: [Int] = []
    var sessionDetailToReturn = MangaSessionDetail(
        sessionId: "s1",
        filename: "Sample.cbz",
        ext: ".cbz",
        totalPages: 0,
        processedCount: 0,
        status: "idle",
        pages: []
    )

    func updateBaseURL(_ url: URL) {}

    func fetchHealth() async throws -> HealthStatus {
        HealthStatus(status: "ok", service: "kobean-manga-colorizer", version: "1.0.0", activeColorizationTasks: 0, batchRunning: false, totalSessions: sessionsToReturn.count)
    }

    func fetchHardware() async throws -> HardwareProfile {
        HardwareProfile(device: "mps", chipName: "Apple M4 Pro", ramGB: 24, useFP16: true, emptyCacheInterval: 15, preferredSize: 768, maxConcurrency: 2, generatorWeightsReady: true, storage: StorageDirectoriesInfo())
    }

    func fetchSessions() async throws -> [MangaSessionSummary] { sessionsToReturn }
    func fetchSession(id: String) async throws -> MangaSessionDetail { sessionDetailToReturn }
    func deleteSession(id: String) async throws {}
    func bulkDeleteSessions(ids: [String], deleteAll: Bool) async throws -> Int { ids.count }
    func deletePage(sessionId: String, pageIndex: Int) async throws -> MangaSessionDetail { sessionDetailToReturn }

    func uploadFiles(fileURLs: [URL], batchId: String?, combineImages: Bool) async throws -> UploadResponseDTO {
        uploadFilesCallCount += 1
        uploadFilesBatchSizes.append(fileURLs.count)
        let firstName = fileURLs.first?.lastPathComponent ?? "Sample.cbz"
        let sess = MangaSessionSummary(
            sessionId: "up-\(uploadFilesCallCount)",
            filename: firstName,
            ext: ".\(fileURLs.first?.pathExtension ?? "cbz")",
            totalPages: 2,
            processedCount: 0,
            status: "idle"
        )
        return UploadResponseDTO(
            status: "success",
            batchId: batchId ?? "b1",
            totalFiles: fileURLs.count,
            sessions: [sess],
            sessionId: sess.sessionId,
            filename: firstName,
            totalPages: 2
        )
    }

    func importLocalFiles(paths: [String], batchId: String?, combineImages: Bool) async throws -> DirectoryImportResponseDTO {
        importLocalFilesCalledPaths = paths
        if let err = importLocalFilesError {
            throw err
        }
        if let custom = importLocalFilesResponse {
            return custom
        }
        return DirectoryImportResponseDTO(
            status: "completed",
            importId: "imp-local",
            batchId: batchId ?? "b1",
            totalFiles: paths.count,
            totalScannedFiles: paths.count,
            importedFiles: paths.count,
            processedFiles: paths.count,
            failedFiles: 0,
            createdSessions: sessionsToReturn,
            createdSessionIds: sessionsToReturn.map(\.sessionId),
            message: "OK"
        )
    }

    func importDirectory(path: String, recursive: Bool, combineImages: Bool) async throws -> DirectoryImportResponseDTO {
        DirectoryImportResponseDTO(status: "completed", importId: "imp1", batchId: "b1", totalFiles: 1, totalScannedFiles: 1, importedFiles: 1, processedFiles: 1, failedFiles: 0, createdSessions: sessionsToReturn, createdSessionIds: ["s1"], message: "OK")
    }

    func fetchImportStatus(importId: String) async throws -> DirectoryImportStatusDTO {
        if !importStatusSequence.isEmpty {
            let idx = min(importStatusPollIndex, importStatusSequence.count - 1)
            importStatusPollIndex += 1
            return importStatusSequence[idx]
        }
        return DirectoryImportStatusDTO(importId: importId, batchId: "b1", directory: "/tmp", status: "completed", totalFiles: 1, importedFiles: 1, failedFiles: 0, currentFile: nil, percent: 100, createdSessionIds: ["s1"], error: nil)
    }

    func cancelImport(importId: String) async throws {
        cancelledImportIds.append(importId)
    }

    func previewPage(sessionId: String, pageIndex: Int, config: ColorizeConfig) async throws -> PreviewResultDTO {
        PreviewResultDTO(
            status: "success",
            pageIndex: pageIndex,
            colorizedUrl: "/api/session/\(sessionId)/image/colorized/p1.jpg",
            engine: "ResNeXt",
            qualityScore: PageQualityScore(overall: 0.9, lineworkIntegrity: 0.94, whitePurity: 0.91, colorRichness: 0.85, autoLearnEligible: true),
            adapterUsed: true,
            seriesKey: "one_piece",
            processedCount: 1,
            totalPages: 2
        )
    }

    func startColorize(sessionId: String, selectedPages: [Int]?, forceRecolorize: Bool, config: ColorizeConfig) async throws {}
    func resumeColorize(sessionId: String, config: ColorizeConfig?) async throws {}
    func cancelColorize(sessionId: String) async throws {}
    func startBatchColorize(sessionIds: [String], config: ColorizeConfig) async throws {}
    func fetchBatchStatus() async throws -> BatchStatusDTO { BatchStatusDTO() }

    func translatePage(sessionId: String, pageIndex: Int, config: ColorizeConfig) async throws -> TranslatePageResponseDTO {
        TranslatePageResponseDTO(status: "success", pageIndex: pageIndex, colorizedUrl: nil, translations: [], bubbleCount: 0, translated: false)
    }

    func translateSession(sessionId: String, selectedPages: [Int]?, config: ColorizeConfig) async throws -> TranslateSessionResponseDTO {
        TranslateSessionResponseDTO(status: "started", sessionId: sessionId, totalPages: 2, targetPages: 2, message: "Started")
    }

    func fetchPresets() async throws -> [MangaPresetDTO] { [] }
    func applyPreset(sessionId: String, presetId: String, applyToBatch: Bool) async throws -> CharacterPaletteDTO { CharacterPaletteDTO(presetId: presetId, presetTitle: presetId) }
    func searchOnlinePreset(query: String, sessionId: String?) async throws -> MangaPresetDTO { MangaPresetDTO(id: "custom", title: query) }
    func fetchPalette(sessionId: String) async throws -> CharacterPaletteDTO { CharacterPaletteDTO() }
    func upsertCharacter(sessionId: String, character: CharacterEntryDTO) async throws -> CharacterPaletteDTO { CharacterPaletteDTO(characters: [character]) }
    func deleteCharacter(sessionId: String, name: String) async throws -> CharacterPaletteDTO { CharacterPaletteDTO() }
    func recognizePageCharacters(sessionId: String, pageIndex: Int, mode: RecognitionMode, apiKey: String) async throws -> RecognizePageResponseDTO {
        RecognizePageResponseDTO(status: "ok", sessionId: sessionId, pageIndex: pageIndex, recognized: recognizedCharactersToReturn, palette: nil, message: nil)
    }

    func fetchSeriesMemory(sessionId: String) async throws -> SeriesMemoryResponseDTO {
        SeriesMemoryResponseDTO(status: "ok", sessionId: sessionId, seriesKey: "one_piece", title: "One Piece", memory: nil)
    }

    func learnPage(sessionId: String, pageIndex: Int, characterNames: [String]?, exemplar: Bool) async throws -> SeriesMemoryResponseDTO {
        SeriesMemoryResponseDTO(status: "ok", sessionId: sessionId, seriesKey: "one_piece", title: "One Piece", memory: nil)
    }

    func fetchExemplars(sessionOrSeriesId: String) async throws -> SeriesExemplarsResponseDTO {
        SeriesExemplarsResponseDTO(status: "ok", sessionId: sessionOrSeriesId, seriesKey: "one_piece", title: "One Piece", exemplars: [])
    }

    func pinExemplar(seriesKey: String, pageIndex: Int, pinned: Bool) async throws {}
    func deleteExemplar(seriesKey: String, pageIndex: Int, sessionId: String?) async throws {}
    func trainAdapter(seriesKey: String, steps: Int, lr: Double) async throws -> AdapterStatusDTO { AdapterStatusDTO(status: "training_started", seriesKey: seriesKey) }
    func fetchAdapterStatus(seriesKey: String) async throws -> AdapterStatusDTO { AdapterStatusDTO(status: "not_trained", seriesKey: seriesKey) }
    func cancelAdapterTraining(seriesKey: String) async throws {}
    func deleteAdapter(seriesKey: String) async throws {}
    func fetchPageQuality(sessionId: String, pageIndex: Int) async throws -> PageQualityScore { PageQualityScore() }
    func fetchAutoRefine(seriesKey: String) async throws -> AutoRefineSettingsDTO { AutoRefineSettingsDTO(seriesKey: seriesKey) }
    func updateAutoRefine(seriesKey: String, settings: AutoRefineSettingsDTO) async throws -> AutoRefineSettingsDTO { settings }

    func exportSession(sessionId: String, format: ExportFormat) async throws -> ExportResultDTO {
        ExportResultDTO(status: "success", format: format.rawValue, downloadUrl: "/api/download/\(sessionId)/out.epub", filename: "out.epub")
    }

    func exportBatch(sessionIds: [String], format: ExportFormat) async throws -> ExportResultDTO {
        ExportResultDTO(status: "success", format: format.rawValue, downloadUrl: "/api/download/batch/all.zip", filename: "all.zip", totalDocuments: sessionIds.count)
    }

    func startCombinedExport(config: CombinedOmnibusConfig) async throws -> CombinedExportJobDTO {
        CombinedExportJobDTO(status: "started", jobId: "job1", format: config.format.rawValue, totalVolumes: 1, totalPages: 2, title: config.title ?? "Collection", isOmnibus: false, streamUrl: "/api/export/combined/stream/job1", cancelUrl: "/api/export/combined/cancel/job1", downloadUrl: nil)
    }

    func cancelCombinedExport(jobId: String) async throws {}
    func downloadFile(relativePath: String, to destinationURL: URL) async throws -> URL { destinationURL }

    func streamColorizeEvents(sessionId: String, autoResume: Bool) -> AsyncThrowingStream<SSEColorizeEvent, Error> {
        AsyncThrowingStream { continuation in continuation.finish() }
    }

    func streamCombinedExportEvents(jobId: String) -> AsyncThrowingStream<SSECombinedExportEvent, Error> {
        let events = combinedExportEventsToStream
        return AsyncThrowingStream { continuation in
            for ev in events {
                continuation.yield(ev)
            }
            continuation.finish()
        }
    }

    func imageURL(relativePath: String, cacheBuster: String?) -> URL? {
        URL(string: "http://127.0.0.1:8000\(relativePath)")
    }
}
