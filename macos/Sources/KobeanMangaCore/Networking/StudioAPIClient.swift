import Foundation

public enum StudioAPIError: LocalizedError, Sendable, Equatable {
    case invalidURL(String)
    case httpError(statusCode: Int, detail: String)
    case decodingError(String)
    case networkError(String)
    case fileOperationFailed(String)

    public var errorDescription: String? {
        switch self {
        case .invalidURL(let url):
            return "Invalid backend URL: \(url)"
        case .httpError(let code, let detail):
            return "Server error (\(code)): \(detail)"
        case .decodingError(let msg):
            return "Failed to decode server response: \(msg)"
        case .networkError(let msg):
            return "Network error: \(msg)"
        case .fileOperationFailed(let msg):
            return "File error: \(msg)"
        }
    }
}

public protocol StudioAPIClientProtocol: Sendable {
    func updateBaseURL(_ url: URL)

    func fetchHealth() async throws -> HealthStatus
    func fetchHardware() async throws -> HardwareProfile

    func fetchSessions() async throws -> [MangaSessionSummary]
    func fetchSession(id: String) async throws -> MangaSessionDetail
    func deleteSession(id: String) async throws
    @discardableResult
    func bulkDeleteSessions(ids: [String], deleteAll: Bool) async throws -> Int
    @discardableResult
    func deletePage(sessionId: String, pageIndex: Int) async throws -> MangaSessionDetail

    func uploadFiles(fileURLs: [URL], batchId: String?, combineImages: Bool) async throws -> UploadResponseDTO
    func importLocalFiles(paths: [String], batchId: String?, combineImages: Bool) async throws -> DirectoryImportResponseDTO
    func importDirectory(path: String, recursive: Bool, combineImages: Bool) async throws -> DirectoryImportResponseDTO
    func fetchImportStatus(importId: String) async throws -> DirectoryImportStatusDTO
    func cancelImport(importId: String) async throws

    func previewPage(sessionId: String, pageIndex: Int, config: ColorizeConfig) async throws -> PreviewResultDTO
    func startColorize(sessionId: String, selectedPages: [Int]?, forceRecolorize: Bool, config: ColorizeConfig) async throws
    func resumeColorize(sessionId: String, config: ColorizeConfig?) async throws
    func cancelColorize(sessionId: String) async throws
    func startBatchColorize(sessionIds: [String], config: ColorizeConfig) async throws
    func cancelBatchColorize() async throws
    func fetchBatchStatus() async throws -> BatchStatusDTO

    func translatePage(sessionId: String, pageIndex: Int, config: ColorizeConfig) async throws -> TranslatePageResponseDTO
    func translateSession(sessionId: String, selectedPages: [Int]?, config: ColorizeConfig) async throws -> TranslateSessionResponseDTO

    func fetchPresets() async throws -> [MangaPresetDTO]
    func applyPreset(sessionId: String, presetId: String, applyToBatch: Bool) async throws -> CharacterPaletteDTO
    func searchOnlinePreset(query: String, sessionId: String?) async throws -> MangaPresetDTO
    func fetchPalette(sessionId: String) async throws -> CharacterPaletteDTO
    func upsertCharacter(sessionId: String, character: CharacterEntryDTO) async throws -> CharacterPaletteDTO
    func deleteCharacter(sessionId: String, name: String) async throws -> CharacterPaletteDTO
    func recognizePageCharacters(sessionId: String, pageIndex: Int, mode: RecognitionMode, apiKey: String) async throws -> RecognizePageResponseDTO

    func fetchSeriesMemory(sessionId: String) async throws -> SeriesMemoryResponseDTO
    func learnPage(sessionId: String, pageIndex: Int, characterNames: [String]?, exemplar: Bool) async throws -> SeriesMemoryResponseDTO
    func fetchExemplars(sessionOrSeriesId: String) async throws -> SeriesExemplarsResponseDTO
    func pinExemplar(seriesKey: String, pageIndex: Int, pinned: Bool) async throws
    func deleteExemplar(seriesKey: String, pageIndex: Int, sessionId: String?) async throws
    func trainAdapter(seriesKey: String, steps: Int, lr: Double) async throws -> AdapterStatusDTO
    func fetchAdapterStatus(seriesKey: String) async throws -> AdapterStatusDTO
    func cancelAdapterTraining(seriesKey: String) async throws
    func deleteAdapter(seriesKey: String) async throws
    func fetchPageQuality(sessionId: String, pageIndex: Int) async throws -> PageQualityScore
    func fetchAutoRefine(seriesKey: String) async throws -> AutoRefineSettingsDTO
    func updateAutoRefine(seriesKey: String, settings: AutoRefineSettingsDTO) async throws -> AutoRefineSettingsDTO

    func exportSession(sessionId: String, format: ExportFormat) async throws -> ExportResultDTO
    func exportBatch(sessionIds: [String], format: ExportFormat) async throws -> ExportResultDTO
    func startCombinedExport(config: CombinedOmnibusConfig) async throws -> CombinedExportJobDTO
    func cancelCombinedExport(jobId: String) async throws
    func downloadFile(relativePath: String, to destinationURL: URL) async throws -> URL

    func streamColorizeEvents(sessionId: String, autoResume: Bool) -> AsyncThrowingStream<SSEColorizeEvent, Error>
    func streamCombinedExportEvents(jobId: String) -> AsyncThrowingStream<SSECombinedExportEvent, Error>
    func imageURL(relativePath: String, cacheBuster: String?) -> URL?
}

public extension StudioAPIClientProtocol {
    func cancelBatchColorize() async throws {}
}

public final class StudioAPIClient: StudioAPIClientProtocol, @unchecked Sendable {
    private let lock = NSLock()
    private var _baseURL: URL
    private let session: URLSession
    private let streamSession: URLSession
    private let decoder = JSONDecoder()

    public init(
        baseURL: URL = URL(string: "http://127.0.0.1:8000")!,
        session: URLSession? = nil,
        streamSession: URLSession? = nil
    ) {
        self._baseURL = baseURL

        if let session {
            self.session = session
        } else {
            let cfg = URLSessionConfiguration.default
            cfg.timeoutIntervalForRequest = 300
            cfg.timeoutIntervalForResource = 3600
            cfg.urlCache = URLCache(
                memoryCapacity: 64 * 1024 * 1024,
                diskCapacity: 256 * 1024 * 1024
            )
            cfg.httpMaximumConnectionsPerHost = 8
            self.session = URLSession(configuration: cfg)
        }

        if let streamSession {
            self.streamSession = streamSession
        } else {
            let streamCfg = URLSessionConfiguration.default
            streamCfg.timeoutIntervalForRequest = 3600
            streamCfg.timeoutIntervalForResource = 21600
            streamCfg.httpMaximumConnectionsPerHost = 8
            self.streamSession = URLSession(configuration: streamCfg)
        }
    }

    public var sessionConfigurationSnapshot: URLSessionConfiguration {
        session.configuration
    }

    public var baseURL: URL {
        lock.lock()
        defer { lock.unlock() }
        return _baseURL
    }

    public func updateBaseURL(_ url: URL) {
        lock.lock()
        _baseURL = url
        lock.unlock()
    }

    // MARK: - Health & Hardware

    public func fetchHealth() async throws -> HealthStatus {
        try await request(path: "/api/health", method: "GET")
    }

    public func fetchHardware() async throws -> HardwareProfile {
        try await request(path: "/api/hardware", method: "GET")
    }

    // MARK: - Sessions

    private struct SessionsListEnvelope: Decodable {
        let sessions: [MangaSessionSummary]?
    }

    public func fetchSessions() async throws -> [MangaSessionSummary] {
        let envelope: SessionsListEnvelope = try await request(path: "/api/sessions", method: "GET")
        return envelope.sessions ?? []
    }

    public func fetchSession(id: String) async throws -> MangaSessionDetail {
        let safeId = encodePathSegment(id)
        return try await request(path: "/api/session/\(safeId)", method: "GET")
    }

    public func deleteSession(id: String) async throws {
        let safeId = encodePathSegment(id)
        _ = try await rawRequest(path: "/api/session/\(safeId)", method: "DELETE")
    }

    private struct BulkDeleteRequestBody: Encodable {
        let sessionIds: [String]?
        let deleteAll: Bool

        private enum CodingKeys: String, CodingKey {
            case sessionIds = "session_ids"
            case deleteAll = "delete_all"
        }
    }

    private struct BulkDeleteResponseEnvelope: Decodable {
        let count: Int?
        let deletedSessionIds: [String]?

        private enum CodingKeys: String, CodingKey {
            case count
            case deletedSessionIds = "deleted_session_ids"
        }
    }

    @discardableResult
    public func bulkDeleteSessions(ids: [String], deleteAll: Bool) async throws -> Int {
        let body = BulkDeleteRequestBody(sessionIds: deleteAll ? nil : ids, deleteAll: deleteAll)
        let resp: BulkDeleteResponseEnvelope = try await request(path: "/api/sessions/bulk-delete", method: "POST", body: body)
        return resp.count ?? resp.deletedSessionIds?.count ?? 0
    }

    private struct DeletePageResponseEnvelope: Decodable {
        let session: MangaSessionDetail
    }

    @discardableResult
    public func deletePage(sessionId: String, pageIndex: Int) async throws -> MangaSessionDetail {
        let safeId = encodePathSegment(sessionId)
        let resp: DeletePageResponseEnvelope = try await request(path: "/api/session/\(safeId)/page/\(pageIndex)", method: "DELETE")
        return resp.session
    }

    // MARK: - Upload & Directory Import

    public func uploadFiles(
        fileURLs: [URL],
        batchId: String? = nil,
        combineImages: Bool = false
    ) async throws -> UploadResponseDTO {
        let url = try buildURL(relativePath: "/api/upload")
        let boundary = "KobeanBoundary-\(UUID().uuidString)"
        let tempBodyURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("kobean-upload-\(UUID().uuidString).multipart")

        // Build multipart payload off the caller's actor so large files never block the main UI thread.
        let escapedParams: [(URL, String, String)] = fileURLs.map { fileURL in
            let standardized = fileURL.standardizedFileURL
            return (
                standardized,
                escapeHeaderParam(standardized.lastPathComponent),
                mimeType(for: standardized.pathExtension)
            )
        }

        defer { try? FileManager.default.removeItem(at: tempBodyURL) }

        try await Task.detached(priority: .userInitiated) {
            FileManager.default.createFile(atPath: tempBodyURL.path, contents: nil)
            do {
                let handle = try FileHandle(forWritingTo: tempBodyURL)
                defer { try? handle.close() }

                func writeString(_ s: String) throws {
                    if let d = s.data(using: .utf8) {
                        try handle.write(contentsOf: d)
                    }
                }

                if let batchId, !batchId.isEmpty {
                    try writeString("--\(boundary)\r\n")
                    try writeString("Content-Disposition: form-data; name=\"batch_id\"\r\n\r\n")
                    try writeString("\(batchId)\r\n")
                }

                if combineImages {
                    try writeString("--\(boundary)\r\n")
                    try writeString("Content-Disposition: form-data; name=\"combine_images\"\r\n\r\n")
                    try writeString("true\r\n")
                }

                for (standardized, escapedName, mime) in escapedParams {
                    try writeString("--\(boundary)\r\n")
                    try writeString("Content-Disposition: form-data; name=\"files\"; filename=\"\(escapedName)\"\r\n")
                    try writeString("Content-Type: \(mime)\r\n\r\n")

                    let reader = try FileHandle(forReadingFrom: standardized)
                    defer { try? reader.close() }
                    while let chunk = try reader.read(upToCount: 1024 * 1024), !chunk.isEmpty {
                        try handle.write(contentsOf: chunk)
                    }
                    try writeString("\r\n")
                }

                try writeString("--\(boundary)--\r\n")
            } catch let error as StudioAPIError {
                throw error
            } catch {
                throw StudioAPIError.fileOperationFailed(error.localizedDescription)
            }
        }.value

        // Explicitly set timeoutInterval because URLRequest defaults to 60s and overrides URLSessionConfiguration.
        var req = URLRequest(url: url, timeoutInterval: max(session.configuration.timeoutIntervalForRequest, 1800))
        req.httpMethod = "POST"
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.upload(for: req, fromFile: tempBodyURL)
        } catch {
            throw StudioAPIError.networkError(error.localizedDescription)
        }
        try validateHTTPResponse(response, data: data)
        return try decode(UploadResponseDTO.self, from: data)
    }

    private struct LocalFilesImportRequestBody: Encodable {
        let filePaths: [String]
        let batchId: String?
        let combineImages: Bool
        let runAsync: Bool

        private enum CodingKeys: String, CodingKey {
            case filePaths = "file_paths"
            case batchId = "batch_id"
            case combineImages = "combine_images"
            case runAsync = "run_async"
        }
    }

    public func importLocalFiles(
        paths: [String],
        batchId: String? = nil,
        combineImages: Bool = false
    ) async throws -> DirectoryImportResponseDTO {
        let body = LocalFilesImportRequestBody(
            filePaths: paths,
            batchId: batchId,
            combineImages: combineImages,
            runAsync: true
        )
        return try await request(path: "/api/import/files", method: "POST", body: body)
    }

    private struct DirectoryImportRequestBody: Encodable {
        let directoryPath: String
        let recursive: Bool
        let combineImages: Bool
        let runAsync: Bool

        private enum CodingKeys: String, CodingKey {
            case directoryPath = "directory_path"
            case recursive
            case combineImages = "combine_images"
            case runAsync = "run_async"
        }
    }

    public func importDirectory(
        path: String,
        recursive: Bool = true,
        combineImages: Bool = true
    ) async throws -> DirectoryImportResponseDTO {
        let body = DirectoryImportRequestBody(
            directoryPath: path,
            recursive: recursive,
            combineImages: combineImages,
            runAsync: true
        )
        return try await request(path: "/api/import/directory", method: "POST", body: body)
    }

    public func fetchImportStatus(importId: String) async throws -> DirectoryImportStatusDTO {
        let safeId = encodePathSegment(importId)
        return try await request(path: "/api/import/status/\(safeId)", method: "GET")
    }

    public func cancelImport(importId: String) async throws {
        let safeId = encodePathSegment(importId)
        _ = try await rawRequest(path: "/api/import/cancel/\(safeId)", method: "POST")
    }

    // MARK: - Colorization & Preview

    private struct PreviewRequestBody: Encodable {
        let sessionId: String
        let pageIndex: Int
        let modelProvider: String
        let modelName: String
        let apiKey: String
        let style: String
        let saturation: Double
        let contrast: Double
        let linePreserve: Double
        let skipIfColored: Bool
        let forceRecolorize: Bool
        let denoiseScreentone: Bool
        let denoiseSigma: Int
        let activeCharacterNames: [String]?
        let recognitionMode: String
        let translatePage: Bool
        let translationEngine: String
        let targetLanguage: String

        private enum CodingKeys: String, CodingKey {
            case sessionId = "session_id"
            case pageIndex = "page_index"
            case modelProvider = "model_provider"
            case modelName = "model_name"
            case apiKey = "api_key"
            case style
            case saturation
            case contrast
            case linePreserve = "line_preserve"
            case skipIfColored = "skip_if_colored"
            case forceRecolorize = "force_recolorize"
            case denoiseScreentone = "denoise_screentone"
            case denoiseSigma = "denoise_sigma"
            case activeCharacterNames = "active_character_names"
            case recognitionMode = "recognition_mode"
            case translatePage = "translate_page"
            case translationEngine = "translation_engine"
            case targetLanguage = "target_language"
        }
    }

    public func previewPage(
        sessionId: String,
        pageIndex: Int,
        config: ColorizeConfig
    ) async throws -> PreviewResultDTO {
        let body = PreviewRequestBody(
            sessionId: sessionId,
            pageIndex: pageIndex,
            modelProvider: config.modelProvider.rawValue,
            modelName: config.modelName,
            apiKey: config.apiKey,
            style: config.style.rawValue,
            saturation: config.saturation,
            contrast: config.contrast,
            linePreserve: config.linePreserve,
            skipIfColored: config.skipIfColored,
            forceRecolorize: true,
            denoiseScreentone: config.denoiseScreentone,
            denoiseSigma: config.denoiseSigma,
            activeCharacterNames: config.activeCharacterNames,
            recognitionMode: config.recognitionMode.rawValue,
            translatePage: config.translatePage,
            translationEngine: config.translationEngine.rawValue,
            targetLanguage: config.targetLanguage.rawValue
        )
        return try await request(path: "/api/colorize/preview", method: "POST", body: body)
    }

    private struct ColorizeRequestBody: Encodable {
        let sessionId: String
        let modelProvider: String
        let modelName: String
        let apiKey: String
        let style: String
        let saturation: Double
        let contrast: Double
        let linePreserve: Double
        let selectedPages: [Int]?
        let skipIfColored: Bool
        let forceRecolorize: Bool
        let denoiseScreentone: Bool
        let denoiseSigma: Int
        let recognitionMode: String
        let activeCharacterNames: [String]?
        let translatePage: Bool
        let translationEngine: String
        let targetLanguage: String

        init(sessionId: String, selectedPages: [Int]?, forceRecolorize: Bool, config: ColorizeConfig) {
            self.sessionId = sessionId
            self.modelProvider = config.modelProvider.rawValue
            self.modelName = config.modelName
            self.apiKey = config.apiKey
            self.style = config.style.rawValue
            self.saturation = config.saturation
            self.contrast = config.contrast
            self.linePreserve = config.linePreserve
            self.selectedPages = selectedPages
            self.skipIfColored = config.skipIfColored
            self.forceRecolorize = forceRecolorize
            self.denoiseScreentone = config.denoiseScreentone
            self.denoiseSigma = config.denoiseSigma
            self.recognitionMode = config.recognitionMode.rawValue
            self.activeCharacterNames = config.activeCharacterNames
            self.translatePage = config.translatePage
            self.translationEngine = config.translationEngine.rawValue
            self.targetLanguage = config.targetLanguage.rawValue
        }

        private enum CodingKeys: String, CodingKey {
            case sessionId = "session_id"
            case modelProvider = "model_provider"
            case modelName = "model_name"
            case apiKey = "api_key"
            case style
            case saturation
            case contrast
            case linePreserve = "line_preserve"
            case selectedPages = "selected_pages"
            case skipIfColored = "skip_if_colored"
            case forceRecolorize = "force_recolorize"
            case denoiseScreentone = "denoise_screentone"
            case denoiseSigma = "denoise_sigma"
            case recognitionMode = "recognition_mode"
            case activeCharacterNames = "active_character_names"
            case translatePage = "translate_page"
            case translationEngine = "translation_engine"
            case targetLanguage = "target_language"
        }
    }

    public func startColorize(
        sessionId: String,
        selectedPages: [Int]?,
        forceRecolorize: Bool,
        config: ColorizeConfig
    ) async throws {
        let body = ColorizeRequestBody(
            sessionId: sessionId,
            selectedPages: selectedPages,
            forceRecolorize: forceRecolorize,
            config: config
        )
        _ = try await rawRequest(path: "/api/colorize/start", method: "POST", body: body)
    }

    public func resumeColorize(sessionId: String, config: ColorizeConfig? = nil) async throws {
        let safeId = encodePathSegment(sessionId)
        if let config {
            let body = ColorizeRequestBody(
                sessionId: sessionId,
                selectedPages: nil,
                forceRecolorize: false,
                config: config
            )
            _ = try await rawRequest(path: "/api/colorize/resume/\(safeId)", method: "POST", body: body)
        } else {
            _ = try await rawRequest(path: "/api/colorize/resume/\(safeId)", method: "POST")
        }
    }

    public func cancelColorize(sessionId: String) async throws {
        let safeId = encodePathSegment(sessionId)
        _ = try await rawRequest(path: "/api/colorize/cancel/\(safeId)", method: "POST")
    }

    private struct BatchColorizeRequestBody: Encodable {
        let sessionIds: [String]
        let modelProvider: String
        let modelName: String
        let apiKey: String
        let style: String
        let saturation: Double
        let contrast: Double
        let linePreserve: Double
        let skipIfColored: Bool
        let denoiseScreentone: Bool
        let denoiseSigma: Int
        let recognitionMode: String
        let translatePage: Bool
        let translationEngine: String
        let targetLanguage: String

        private enum CodingKeys: String, CodingKey {
            case sessionIds = "session_ids"
            case modelProvider = "model_provider"
            case modelName = "model_name"
            case apiKey = "api_key"
            case style
            case saturation
            case contrast
            case linePreserve = "line_preserve"
            case skipIfColored = "skip_if_colored"
            case denoiseScreentone = "denoise_screentone"
            case denoiseSigma = "denoise_sigma"
            case recognitionMode = "recognition_mode"
            case translatePage = "translate_page"
            case translationEngine = "translation_engine"
            case targetLanguage = "target_language"
        }
    }

    public func startBatchColorize(sessionIds: [String], config: ColorizeConfig) async throws {
        let body = BatchColorizeRequestBody(
            sessionIds: sessionIds,
            modelProvider: config.modelProvider.rawValue,
            modelName: config.modelName,
            apiKey: config.apiKey,
            style: config.style.rawValue,
            saturation: config.saturation,
            contrast: config.contrast,
            linePreserve: config.linePreserve,
            skipIfColored: config.skipIfColored,
            denoiseScreentone: config.denoiseScreentone,
            denoiseSigma: config.denoiseSigma,
            recognitionMode: config.recognitionMode.rawValue,
            translatePage: config.translatePage,
            translationEngine: config.translationEngine.rawValue,
            targetLanguage: config.targetLanguage.rawValue
        )
        _ = try await rawRequest(path: "/api/colorize/batch/start", method: "POST", body: body)
    }

    public func cancelBatchColorize() async throws {
        _ = try await rawRequest(path: "/api/colorize/batch/cancel", method: "POST")
    }

    public func fetchBatchStatus() async throws -> BatchStatusDTO {
        try await request(path: "/api/colorize/batch/status", method: "GET")
    }

    // MARK: - Translation

    private struct TranslatePageRequestBody: Encodable {
        let sessionId: String
        let pageIndex: Int
        let targetLanguage: String
        let translationEngine: String
        let translateColorized: Bool
        let apiKey: String

        private enum CodingKeys: String, CodingKey {
            case sessionId = "session_id"
            case pageIndex = "page_index"
            case targetLanguage = "target_language"
            case translationEngine = "translation_engine"
            case translateColorized = "translate_colorized"
            case apiKey = "api_key"
        }
    }

    public func translatePage(
        sessionId: String,
        pageIndex: Int,
        config: ColorizeConfig
    ) async throws -> TranslatePageResponseDTO {
        let body = TranslatePageRequestBody(
            sessionId: sessionId,
            pageIndex: pageIndex,
            targetLanguage: config.targetLanguage.rawValue,
            translationEngine: config.translationEngine.rawValue,
            translateColorized: true,
            apiKey: config.apiKey
        )
        return try await request(path: "/api/translate/page", method: "POST", body: body)
    }

    private struct TranslateSessionRequestBody: Encodable {
        let sessionId: String
        let targetLanguage: String
        let translationEngine: String
        let apiKey: String
        let selectedPages: [Int]?

        private enum CodingKeys: String, CodingKey {
            case sessionId = "session_id"
            case targetLanguage = "target_language"
            case translationEngine = "translation_engine"
            case apiKey = "api_key"
            case selectedPages = "selected_pages"
        }
    }

    public func translateSession(
        sessionId: String,
        selectedPages: [Int]?,
        config: ColorizeConfig
    ) async throws -> TranslateSessionResponseDTO {
        let body = TranslateSessionRequestBody(
            sessionId: sessionId,
            targetLanguage: config.targetLanguage.rawValue,
            translationEngine: config.translationEngine.rawValue,
            apiKey: config.apiKey,
            selectedPages: selectedPages
        )
        return try await request(path: "/api/translate/session", method: "POST", body: body)
    }

    // MARK: - Presets & Character Palette

    private struct PresetsEnvelope: Decodable {
        let presets: [MangaPresetDTO]?
    }

    public func fetchPresets() async throws -> [MangaPresetDTO] {
        let env: PresetsEnvelope = try await request(path: "/api/palette/presets", method: "GET")
        return env.presets ?? []
    }

    private struct PaletteEnvelope: Decodable {
        let palette: CharacterPaletteDTO
    }

    private struct ApplyPresetRequestBody: Encodable {
        let sessionId: String
        let presetId: String
        let applyToBatch: Bool

        private enum CodingKeys: String, CodingKey {
            case sessionId = "session_id"
            case presetId = "preset_id"
            case applyToBatch = "apply_to_batch"
        }
    }

    public func applyPreset(
        sessionId: String,
        presetId: String,
        applyToBatch: Bool = true
    ) async throws -> CharacterPaletteDTO {
        let body = ApplyPresetRequestBody(
            sessionId: sessionId,
            presetId: presetId,
            applyToBatch: applyToBatch
        )
        let env: PaletteEnvelope = try await request(path: "/api/palette/apply-preset", method: "POST", body: body)
        return env.palette
    }

    private struct SearchOnlinePresetBody: Encodable {
        let query: String
        let sessionId: String?

        private enum CodingKeys: String, CodingKey {
            case query
            case sessionId = "session_id"
        }
    }

    private struct PresetEnvelope: Decodable {
        let preset: MangaPresetDTO
    }

    public func searchOnlinePreset(query: String, sessionId: String?) async throws -> MangaPresetDTO {
        let body = SearchOnlinePresetBody(query: query, sessionId: sessionId)
        let env: PresetEnvelope = try await request(path: "/api/palette/search-online", method: "POST", body: body)
        return env.preset
    }

    public func fetchPalette(sessionId: String) async throws -> CharacterPaletteDTO {
        let safeId = encodePathSegment(sessionId)
        let env: PaletteEnvelope = try await request(path: "/api/palette/\(safeId)", method: "GET")
        return env.palette
    }

    private struct UpsertCharacterBody: Encodable {
        let sessionId: String
        let character: CharacterEntryDTO

        private enum CodingKeys: String, CodingKey {
            case sessionId = "session_id"
            case character
        }
    }

    public func upsertCharacter(
        sessionId: String,
        character: CharacterEntryDTO
    ) async throws -> CharacterPaletteDTO {
        let body = UpsertCharacterBody(sessionId: sessionId, character: character)
        let env: PaletteEnvelope = try await request(path: "/api/palette/upsert", method: "POST", body: body)
        return env.palette
    }

    public func deleteCharacter(sessionId: String, name: String) async throws -> CharacterPaletteDTO {
        let safeId = encodePathSegment(sessionId)
        let safeName = encodePathSegment(name)
        let env: PaletteEnvelope = try await request(path: "/api/palette/\(safeId)/\(safeName)", method: "DELETE")
        return env.palette
    }

    private struct RecognizeRequestBody: Encodable {
        let apiKey: String
        let recognitionMode: String

        private enum CodingKeys: String, CodingKey {
            case apiKey = "api_key"
            case recognitionMode = "recognition_mode"
        }
    }

    public func recognizePageCharacters(
        sessionId: String,
        pageIndex: Int,
        mode: RecognitionMode,
        apiKey: String
    ) async throws -> RecognizePageResponseDTO {
        let safeId = encodePathSegment(sessionId)
        let body = RecognizeRequestBody(apiKey: apiKey, recognitionMode: mode.rawValue)
        return try await request(
            path: "/api/session/\(safeId)/page/\(pageIndex)/recognize",
            method: "POST",
            body: body
        )
    }

    // MARK: - Series Memory & LoRA Adapter

    public func fetchSeriesMemory(sessionId: String) async throws -> SeriesMemoryResponseDTO {
        let safeId = encodePathSegment(sessionId)
        return try await request(path: "/api/series-memory/\(safeId)", method: "GET")
    }

    private struct LearnPageBody: Encodable {
        let sessionId: String
        let pageIndex: Int
        let characterNames: [String]?
        let exemplar: Bool

        private enum CodingKeys: String, CodingKey {
            case sessionId = "session_id"
            case pageIndex = "page_index"
            case characterNames = "character_names"
            case exemplar
        }
    }

    public func learnPage(
        sessionId: String,
        pageIndex: Int,
        characterNames: [String]? = nil,
        exemplar: Bool = true
    ) async throws -> SeriesMemoryResponseDTO {
        let body = LearnPageBody(
            sessionId: sessionId,
            pageIndex: pageIndex,
            characterNames: characterNames,
            exemplar: exemplar
        )
        return try await request(path: "/api/series-memory/learn-page", method: "POST", body: body)
    }

    public func fetchExemplars(sessionOrSeriesId: String) async throws -> SeriesExemplarsResponseDTO {
        let safeId = encodePathSegment(sessionOrSeriesId)
        return try await request(path: "/api/series-memory/\(safeId)/exemplars", method: "GET")
    }

    private struct PinExemplarBody: Encodable {
        let seriesKey: String
        let pageIndex: Int
        let pinned: Bool

        private enum CodingKeys: String, CodingKey {
            case seriesKey = "series_key"
            case pageIndex = "page_index"
            case pinned
        }
    }

    public func pinExemplar(seriesKey: String, pageIndex: Int, pinned: Bool) async throws {
        let body = PinExemplarBody(seriesKey: seriesKey, pageIndex: pageIndex, pinned: pinned)
        _ = try await rawRequest(path: "/api/series-memory/pin-exemplar", method: "POST", body: body)
    }

    public func deleteExemplar(seriesKey: String, pageIndex: Int, sessionId: String? = nil) async throws {
        let safeKey = encodePathSegment(seriesKey)
        var path = "/api/series-memory/\(safeKey)/exemplar/\(pageIndex)"
        if let sessionId, !sessionId.isEmpty {
            let safeSess = sessionId.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? sessionId
            path += "?session_id=\(safeSess)"
        }
        _ = try await rawRequest(path: path, method: "DELETE")
    }

    private struct TrainAdapterBody: Encodable {
        let seriesKey: String
        let steps: Int
        let lr: Double

        private enum CodingKeys: String, CodingKey {
            case seriesKey = "series_key"
            case steps
            case lr
        }
    }

    public func trainAdapter(
        seriesKey: String,
        steps: Int = 100,
        lr: Double = 2e-4
    ) async throws -> AdapterStatusDTO {
        let safeKey = encodePathSegment(seriesKey)
        let body = TrainAdapterBody(seriesKey: seriesKey, steps: steps, lr: lr)
        return try await request(path: "/api/series-memory/\(safeKey)/train-adapter", method: "POST", body: body)
    }

    public func fetchAdapterStatus(seriesKey: String) async throws -> AdapterStatusDTO {
        let safeKey = encodePathSegment(seriesKey)
        return try await request(path: "/api/series-memory/\(safeKey)/adapter-status", method: "GET")
    }

    public func cancelAdapterTraining(seriesKey: String) async throws {
        let safeKey = encodePathSegment(seriesKey)
        _ = try await rawRequest(path: "/api/series-memory/\(safeKey)/cancel-training", method: "POST")
    }

    public func deleteAdapter(seriesKey: String) async throws {
        let safeKey = encodePathSegment(seriesKey)
        _ = try await rawRequest(path: "/api/series-memory/\(safeKey)/adapter", method: "DELETE")
    }

    private struct QualityScoreEnvelope: Decodable {
        let qualityScore: PageQualityScore

        private enum CodingKeys: String, CodingKey {
            case qualityScore = "quality_score"
        }
    }

    public func fetchPageQuality(sessionId: String, pageIndex: Int) async throws -> PageQualityScore {
        let safeId = encodePathSegment(sessionId)
        let env: QualityScoreEnvelope = try await request(
            path: "/api/session/\(safeId)/page/\(pageIndex)/quality",
            method: "GET"
        )
        return env.qualityScore
    }

    public func fetchAutoRefine(seriesKey: String) async throws -> AutoRefineSettingsDTO {
        let safeKey = encodePathSegment(seriesKey)
        return try await request(path: "/api/series-memory/\(safeKey)/auto-refine", method: "GET")
    }

    private struct AutoRefineUpdateBody: Encodable {
        let enabled: Bool
        let threshold: Double
        let interval: Int
    }

    public func updateAutoRefine(
        seriesKey: String,
        settings: AutoRefineSettingsDTO
    ) async throws -> AutoRefineSettingsDTO {
        let safeKey = encodePathSegment(seriesKey)
        let body = AutoRefineUpdateBody(
            enabled: settings.autoRefineEnabled,
            threshold: settings.autoHarvestThreshold,
            interval: settings.autoRefineInterval
        )
        return try await request(path: "/api/series-memory/\(safeKey)/auto-refine", method: "POST", body: body)
    }

    // MARK: - Exports & Downloads

    public func exportSession(sessionId: String, format: ExportFormat) async throws -> ExportResultDTO {
        let safeId = encodePathSegment(sessionId)
        return try await request(path: "/api/export/\(safeId)?format=\(format.rawValue)", method: "POST")
    }

    private struct BatchExportBody: Encodable {
        let sessionIds: [String]
        let format: String

        private enum CodingKeys: String, CodingKey {
            case sessionIds = "session_ids"
            case format
        }
    }

    public func exportBatch(sessionIds: [String], format: ExportFormat) async throws -> ExportResultDTO {
        let body = BatchExportBody(sessionIds: sessionIds, format: format.rawValue)
        return try await request(path: "/api/export/batch", method: "POST", body: body)
    }

    private struct CombinedExportBody: Encodable {
        let sessionIds: [String]?
        let format: String
        let title: String?
        let sync: Bool
        let chunkBy: String
        let chunkSize: Int
        let maxDimension: Int
        let jpegQuality: Int
        let grayscale: Bool
        let colorsoftTune: Bool
        let exportOriginal: Bool

        private enum CodingKeys: String, CodingKey {
            case sessionIds = "session_ids"
            case format
            case title
            case sync
            case chunkBy = "chunk_by"
            case chunkSize = "chunk_size"
            case maxDimension = "max_dimension"
            case jpegQuality = "jpeg_quality"
            case grayscale
            case colorsoftTune = "colorsoft_tune"
            case exportOriginal = "export_original"
        }
    }

    public func startCombinedExport(config: CombinedOmnibusConfig) async throws -> CombinedExportJobDTO {
        let body = CombinedExportBody(
            sessionIds: config.sessionIds,
            format: config.format.rawValue,
            title: config.title,
            sync: false,
            chunkBy: config.chunkBy.rawValue,
            chunkSize: config.chunkSize,
            maxDimension: config.maxDimension,
            jpegQuality: config.jpegQuality,
            grayscale: config.grayscale,
            colorsoftTune: config.colorsoftTune,
            exportOriginal: config.exportOriginal
        )
        return try await request(path: "/api/export/combined", method: "POST", body: body)
    }

    public func cancelCombinedExport(jobId: String) async throws {
        let safeId = encodePathSegment(jobId)
        _ = try await rawRequest(path: "/api/export/combined/cancel/\(safeId)", method: "POST")
    }

    public func downloadFile(relativePath: String, to destinationURL: URL) async throws -> URL {
        let url = try buildURL(relativePath: relativePath)
        let standardizedDest = destinationURL.standardizedFileURL

        let (tempURL, response) = try await session.download(from: url)
        guard let http = response as? HTTPURLResponse else {
            throw StudioAPIError.networkError("Invalid HTTP response during download")
        }
        guard (200...299).contains(http.statusCode) else {
            let data = (try? Data(contentsOf: tempURL)) ?? Data()
            throw StudioAPIError.httpError(statusCode: http.statusCode, detail: parseErrorDetail(from: data))
        }

        do {
            let fm = FileManager.default
            try fm.createDirectory(at: standardizedDest.deletingLastPathComponent(), withIntermediateDirectories: true)
            if fm.fileExists(atPath: standardizedDest.path) {
                try fm.removeItem(at: standardizedDest)
            }
            try fm.moveItem(at: tempURL, to: standardizedDest)
            return standardizedDest
        } catch {
            throw StudioAPIError.fileOperationFailed(error.localizedDescription)
        }
    }

    // MARK: - SSE Streams

    public func streamColorizeEvents(
        sessionId: String,
        autoResume: Bool = false
    ) -> AsyncThrowingStream<SSEColorizeEvent, Error> {
        let safeId = encodePathSegment(sessionId)
        let path = "/api/colorize/stream/\(safeId)?auto_resume=\(autoResume ? "true" : "false")"
        return makeSSEStream(path: path) { line in
            SSEParser.parseColorizeLine(line)
        }
    }

    public func streamCombinedExportEvents(jobId: String) -> AsyncThrowingStream<SSECombinedExportEvent, Error> {
        let safeId = encodePathSegment(jobId)
        let path = "/api/export/combined/stream/\(safeId)"
        return makeSSEStream(path: path) { line in
            SSEParser.parseCombinedExportLine(line)
        }
    }

    public func imageURL(relativePath: String, cacheBuster: String? = nil) -> URL? {
        guard !relativePath.isEmpty else { return nil }
        guard var url = try? buildURL(relativePath: relativePath) else { return nil }
        if let cacheBuster, !cacheBuster.isEmpty {
            if var comps = URLComponents(url: url, resolvingAgainstBaseURL: false) {
                var items = comps.queryItems ?? []
                items.append(URLQueryItem(name: "t", value: cacheBuster))
                comps.queryItems = items
                if let updated = comps.url {
                    url = updated
                }
            }
        }
        return url
    }

    // MARK: - Private HTTP Helpers

    private func makeSSEStream<Event: Sendable>(
        path: String,
        parse: @escaping @Sendable (String) -> Event?
    ) -> AsyncThrowingStream<Event, Error> {
        AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    let url = try self.buildURL(relativePath: path)
                    var req = URLRequest(
                        url: url,
                        timeoutInterval: self.streamSession.configuration.timeoutIntervalForRequest
                    )
                    req.httpMethod = "GET"
                    req.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    req.setValue("no-cache", forHTTPHeaderField: "Cache-Control")

                    let (bytes, response) = try await self.streamSession.bytes(for: req)
                    guard let http = response as? HTTPURLResponse else {
                        continuation.finish(throwing: StudioAPIError.networkError("Invalid SSE response"))
                        return
                    }
                    guard (200...299).contains(http.statusCode) else {
                        continuation.finish(
                            throwing: StudioAPIError.httpError(
                                statusCode: http.statusCode,
                                detail: "SSE connection rejected"
                            )
                        )
                        return
                    }

                    for try await line in bytes.lines {
                        if Task.isCancelled { break }
                        if let event = parse(line) {
                            continuation.yield(event)
                        }
                    }
                    continuation.finish()
                } catch is CancellationError {
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in
                task.cancel()
            }
        }
    }

    private func request<T: Decodable>(
        path: String,
        method: String
    ) async throws -> T {
        let data = try await rawRequest(path: path, method: method)
        return try decode(T.self, from: data)
    }

    private func request<T: Decodable, Body: Encodable>(
        path: String,
        method: String,
        body: Body
    ) async throws -> T {
        let data = try await rawRequest(path: path, method: method, body: body)
        return try decode(T.self, from: data)
    }

    private func rawRequest(path: String, method: String) async throws -> Data {
        let url = try buildURL(relativePath: path)
        var req = URLRequest(url: url, timeoutInterval: session.configuration.timeoutIntervalForRequest)
        req.httpMethod = method
        return try await execute(req)
    }

    private func rawRequest<Body: Encodable>(path: String, method: String, body: Body) async throws -> Data {
        let url = try buildURL(relativePath: path)
        var req = URLRequest(url: url, timeoutInterval: session.configuration.timeoutIntervalForRequest)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        return try await execute(req)
    }

    private func execute(_ req: URLRequest) async throws -> Data {
        let (data, response): (Data, URLResponse)
        do {
            (data, response) = try await session.data(for: req)
        } catch {
            throw StudioAPIError.networkError(error.localizedDescription)
        }
        try validateHTTPResponse(response, data: data)
        return data
    }

    private func validateHTTPResponse(_ response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else {
            throw StudioAPIError.networkError("Missing HTTP response")
        }
        guard (200...299).contains(http.statusCode) else {
            throw StudioAPIError.httpError(statusCode: http.statusCode, detail: parseErrorDetail(from: data))
        }
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw StudioAPIError.decodingError(error.localizedDescription)
        }
    }

    private func parseErrorDetail(from data: Data) -> String {
        if let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
           let detail = dict["detail"] as? String {
            return detail
        }
        if let str = String(data: data, encoding: .utf8), !str.isEmpty {
            return String(str.prefix(300))
        }
        return "Request failed"
    }

    private func buildURL(relativePath: String) throws -> URL {
        if relativePath.hasPrefix("http://") || relativePath.hasPrefix("https://") {
            guard let absolute = URL(string: relativePath) else {
                throw StudioAPIError.invalidURL(relativePath)
            }
            return absolute
        }
        let normalized = relativePath.hasPrefix("/") ? relativePath : "/\(relativePath)"
        let currentBase = baseURL.absoluteString.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        guard let url = URL(string: currentBase + normalized) else {
            throw StudioAPIError.invalidURL(currentBase + normalized)
        }
        return url
    }

    private func encodePathSegment(_ value: String) -> String {
        var allowed = CharacterSet.urlPathAllowed
        allowed.remove(charactersIn: "/")
        return value.addingPercentEncoding(withAllowedCharacters: allowed) ?? value
    }

    private func escapeHeaderParam(_ value: String) -> String {
        value.replacingOccurrences(of: "\"", with: "_")
            .replacingOccurrences(of: "\r", with: "")
            .replacingOccurrences(of: "\n", with: "")
    }

    private func mimeType(for ext: String) -> String {
        switch ext.lowercased() {
        case "pdf": return "application/pdf"
        case "epub": return "application/epub+zip"
        case "cbz", "zip": return "application/zip"
        case "png": return "image/png"
        case "jpg", "jpeg": return "image/jpeg"
        case "webp": return "image/webp"
        case "bmp": return "image/bmp"
        case "gif": return "image/gif"
        case "tiff", "tif": return "image/tiff"
        default: return "application/octet-stream"
        }
    }
}
