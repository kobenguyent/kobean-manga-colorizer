import Foundation

// MARK: - Health & Hardware

public struct HealthStatus: Codable, Sendable, Equatable {
    public var status: String
    public var service: String
    public var version: String
    public var activeColorizationTasks: Int
    public var batchRunning: Bool
    public var totalSessions: Int

    public var isHealthy: Bool { status.lowercased() == "ok" }

    public init(
        status: String = "unknown",
        service: String = "kobean-manga-colorizer",
        version: String = "1.0.0",
        activeColorizationTasks: Int = 0,
        batchRunning: Bool = false,
        totalSessions: Int = 0
    ) {
        self.status = status
        self.service = service
        self.version = version
        self.activeColorizationTasks = activeColorizationTasks
        self.batchRunning = batchRunning
        self.totalSessions = totalSessions
    }

    private enum CodingKeys: String, CodingKey {
        case status
        case service
        case version
        case activeColorizationTasks = "active_colorization_tasks"
        case activeTasks = "active_tasks"
        case batchRunning = "batch_running"
        case totalSessions = "total_sessions"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "unknown"
        self.service = try c.decodeIfPresent(String.self, forKey: .service) ?? "kobean-manga-colorizer"
        self.version = try c.decodeIfPresent(String.self, forKey: .version) ?? "1.0.0"
        let tasks = try c.decodeIfPresent(Int.self, forKey: .activeColorizationTasks)
            ?? c.decodeIfPresent(Int.self, forKey: .activeTasks)
            ?? 0
        self.activeColorizationTasks = tasks
        self.batchRunning = try c.decodeIfPresent(Bool.self, forKey: .batchRunning) ?? false
        self.totalSessions = try c.decodeIfPresent(Int.self, forKey: .totalSessions) ?? 0
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(status, forKey: .status)
        try c.encode(service, forKey: .service)
        try c.encode(version, forKey: .version)
        try c.encode(activeColorizationTasks, forKey: .activeColorizationTasks)
        try c.encode(batchRunning, forKey: .batchRunning)
        try c.encode(totalSessions, forKey: .totalSessions)
    }
}

public struct StorageDirectoriesInfo: Codable, Sendable, Equatable {
    public var sessionsDir: String
    public var uploadsDir: String
    public var outputDir: String

    public init(
        sessionsDir: String = "",
        uploadsDir: String = "",
        outputDir: String = ""
    ) {
        self.sessionsDir = sessionsDir
        self.uploadsDir = uploadsDir
        self.outputDir = outputDir
    }

    private enum CodingKeys: String, CodingKey {
        case sessionsDir = "sessions_dir"
        case uploadsDir = "uploads_dir"
        case outputDir = "output_dir"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.sessionsDir = try c.decodeIfPresent(String.self, forKey: .sessionsDir) ?? ""
        self.uploadsDir = try c.decodeIfPresent(String.self, forKey: .uploadsDir) ?? ""
        self.outputDir = try c.decodeIfPresent(String.self, forKey: .outputDir) ?? ""
    }
}

public struct HardwareProfile: Codable, Sendable, Equatable {
    public var device: String
    public var chipName: String
    public var ramGB: Int
    public var useFP16: Bool
    public var emptyCacheInterval: Int
    public var preferredSize: Int
    public var maxConcurrency: Int
    public var generatorWeightsReady: Bool
    public var storage: StorageDirectoriesInfo

    public var isMPS: Bool { device.lowercased() == "mps" }

    public var badgeLabel: String {
        let accel = device.uppercased()
        if chipName.isEmpty || chipName == "CPU" {
            return "\(accel) · \(ramGB) GB"
        }
        return "\(chipName) · \(ramGB) GB · \(accel)"
    }

    public init(
        device: String = "cpu",
        chipName: String = "CPU",
        ramGB: Int = 16,
        useFP16: Bool = false,
        emptyCacheInterval: Int = 20,
        preferredSize: Int = 768,
        maxConcurrency: Int = 1,
        generatorWeightsReady: Bool = false,
        storage: StorageDirectoriesInfo = StorageDirectoriesInfo()
    ) {
        self.device = device
        self.chipName = chipName
        self.ramGB = ramGB
        self.useFP16 = useFP16
        self.emptyCacheInterval = emptyCacheInterval
        self.preferredSize = preferredSize
        self.maxConcurrency = maxConcurrency
        self.generatorWeightsReady = generatorWeightsReady
        self.storage = storage
    }

    private enum CodingKeys: String, CodingKey {
        case device
        case chipName = "chip_name"
        case ramGB = "ram_gb"
        case useFP16 = "use_fp16"
        case emptyCacheInterval = "empty_cache_interval"
        case preferredSize = "preferred_size"
        case maxConcurrency = "max_concurrency"
        case generatorWeightsReady = "generator_weights_ready"
        case storage
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.device = try c.decodeIfPresent(String.self, forKey: .device) ?? "cpu"
        self.chipName = try c.decodeIfPresent(String.self, forKey: .chipName) ?? "CPU"
        self.ramGB = try c.decodeIfPresent(Int.self, forKey: .ramGB) ?? 16
        self.useFP16 = try c.decodeIfPresent(Bool.self, forKey: .useFP16) ?? false
        self.emptyCacheInterval = try c.decodeIfPresent(Int.self, forKey: .emptyCacheInterval) ?? 20
        self.preferredSize = try c.decodeIfPresent(Int.self, forKey: .preferredSize) ?? 768
        self.maxConcurrency = try c.decodeIfPresent(Int.self, forKey: .maxConcurrency) ?? 1
        self.generatorWeightsReady = try c.decodeIfPresent(Bool.self, forKey: .generatorWeightsReady) ?? false
        self.storage = try c.decodeIfPresent(StorageDirectoriesInfo.self, forKey: .storage) ?? StorageDirectoriesInfo()
    }
}

// MARK: - Sessions & Pages

public struct MangaSessionSummary: Codable, Sendable, Equatable, Identifiable {
    public var sessionId: String
    public var batchId: String?
    public var filename: String
    public var ext: String
    public var totalPages: Int
    public var processedCount: Int
    public var status: String
    public var isActive: Bool
    public var detectedPreset: String?
    public var presetTitle: String?

    public var id: String { sessionId }

    public var progressFraction: Double {
        guard totalPages > 0 else { return 0 }
        return min(1.0, max(0.0, Double(processedCount) / Double(totalPages)))
    }

    public init(
        sessionId: String,
        batchId: String? = nil,
        filename: String,
        ext: String = "",
        totalPages: Int = 0,
        processedCount: Int = 0,
        status: String = "idle",
        isActive: Bool = false,
        detectedPreset: String? = nil,
        presetTitle: String? = nil
    ) {
        self.sessionId = sessionId
        self.batchId = batchId
        self.filename = filename
        self.ext = ext
        self.totalPages = totalPages
        self.processedCount = processedCount
        self.status = status
        self.isActive = isActive
        self.detectedPreset = detectedPreset
        self.presetTitle = presetTitle
    }

    private enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case batchId = "batch_id"
        case filename
        case ext
        case totalPages = "total_pages"
        case processedCount = "processed_count"
        case status
        case isActive = "is_active"
        case detectedPreset = "detected_preset"
        case presetTitle = "preset_title"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.sessionId = try c.decodeIfPresent(String.self, forKey: .sessionId) ?? ""
        self.batchId = try c.decodeIfPresent(String.self, forKey: .batchId)
        self.filename = try c.decodeIfPresent(String.self, forKey: .filename) ?? "Untitled"
        self.ext = try c.decodeIfPresent(String.self, forKey: .ext) ?? ""
        self.totalPages = try c.decodeIfPresent(Int.self, forKey: .totalPages) ?? 0
        self.processedCount = try c.decodeIfPresent(Int.self, forKey: .processedCount) ?? 0
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "idle"
        self.isActive = try c.decodeIfPresent(Bool.self, forKey: .isActive) ?? false
        self.detectedPreset = try c.decodeIfPresent(String.self, forKey: .detectedPreset)
        self.presetTitle = try c.decodeIfPresent(String.self, forKey: .presetTitle)
    }
}

public struct RecognizedCharacterDTO: Codable, Sendable, Equatable, Identifiable {
    public var name: String
    public var confidence: Double
    public var boundingBox: [Double]?
    public var detectionMethod: String
    public var matchedFeatures: [String]

    public var id: String { name }

    public init(
        name: String,
        confidence: Double = 0.0,
        boundingBox: [Double]? = nil,
        detectionMethod: String = "visual_heuristic",
        matchedFeatures: [String] = []
    ) {
        self.name = name
        self.confidence = confidence
        self.boundingBox = boundingBox
        self.detectionMethod = detectionMethod
        self.matchedFeatures = matchedFeatures
    }

    private enum CodingKeys: String, CodingKey {
        case name
        case confidence
        case boundingBox = "bounding_box"
        case detectionMethod = "detection_method"
        case matchedFeatures = "matched_features"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.name = try c.decodeIfPresent(String.self, forKey: .name) ?? ""
        self.confidence = try c.decodeIfPresent(Double.self, forKey: .confidence) ?? 0.0
        self.boundingBox = try c.decodeIfPresent([Double].self, forKey: .boundingBox)
        self.detectionMethod = try c.decodeIfPresent(String.self, forKey: .detectionMethod) ?? "visual_heuristic"
        self.matchedFeatures = try c.decodeIfPresent([String].self, forKey: .matchedFeatures) ?? []
    }
}

public struct BubbleTranslationDTO: Codable, Sendable, Equatable, Identifiable {
    public var box: [Int]
    public var japanese: String
    public var english: String
    public var confidence: Double

    public var id: String {
        "\(box.map(String.init).joined(separator: ","))-\(japanese)-\(english)"
    }

    public init(
        box: [Int] = [],
        japanese: String = "",
        english: String = "",
        confidence: Double = 0.88
    ) {
        self.box = box
        self.japanese = japanese
        self.english = english
        self.confidence = confidence
    }

    private enum CodingKeys: String, CodingKey {
        case box
        case japanese
        case english
        case confidence
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        if let intBox = try? c.decodeIfPresent([Int].self, forKey: .box) {
            self.box = intBox
        } else if let doubleBox = try? c.decodeIfPresent([Double].self, forKey: .box) {
            self.box = doubleBox.map { Int($0.rounded()) }
        } else {
            self.box = []
        }
        self.japanese = try c.decodeIfPresent(String.self, forKey: .japanese) ?? ""
        self.english = try c.decodeIfPresent(String.self, forKey: .english) ?? ""
        self.confidence = try c.decodeIfPresent(Double.self, forKey: .confidence) ?? 0.88
    }
}

public struct PageQualityScore: Codable, Sendable, Equatable {
    public var overall: Double
    public var lineworkIntegrity: Double
    public var whitePurity: Double
    public var colorRichness: Double
    public var autoLearnEligible: Bool
    public var grade: String
    public var threshold: Double
    public var isAuthorColored: Bool

    public init(
        overall: Double = 0.0,
        lineworkIntegrity: Double = 0.0,
        whitePurity: Double = 0.0,
        colorRichness: Double = 0.0,
        autoLearnEligible: Bool = false,
        grade: String = "moderate",
        threshold: Double = 0.82,
        isAuthorColored: Bool = false
    ) {
        self.overall = overall
        self.lineworkIntegrity = lineworkIntegrity
        self.whitePurity = whitePurity
        self.colorRichness = colorRichness
        self.autoLearnEligible = autoLearnEligible
        self.grade = grade
        self.threshold = threshold
        self.isAuthorColored = isAuthorColored
    }

    private enum CodingKeys: String, CodingKey {
        case overallScore = "overall_score"
        case overall
        case grade
        case autoLearnEligible = "auto_learn_eligible"
        case metrics
        case lineworkIntegrity = "linework_integrity"
        case whitePurity = "white_purity"
        case colorRichness = "color_richness"
        case threshold
        case isAuthorColored = "is_author_colored"
    }

    private enum MetricsCodingKeys: String, CodingKey {
        case lineworkIntegrity = "linework_integrity"
        case whitePurity = "white_purity"
        case colorRichness = "color_richness"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.overall = try c.decodeIfPresent(Double.self, forKey: .overallScore)
            ?? c.decodeIfPresent(Double.self, forKey: .overall)
            ?? 0.0
        self.grade = try c.decodeIfPresent(String.self, forKey: .grade) ?? "moderate"
        self.autoLearnEligible = try c.decodeIfPresent(Bool.self, forKey: .autoLearnEligible) ?? false
        self.threshold = try c.decodeIfPresent(Double.self, forKey: .threshold) ?? 0.82
        self.isAuthorColored = try c.decodeIfPresent(Bool.self, forKey: .isAuthorColored) ?? false

        if let metrics = try? c.nestedContainer(keyedBy: MetricsCodingKeys.self, forKey: .metrics) {
            self.lineworkIntegrity = try metrics.decodeIfPresent(Double.self, forKey: .lineworkIntegrity) ?? 0.0
            self.whitePurity = try metrics.decodeIfPresent(Double.self, forKey: .whitePurity) ?? 0.0
            self.colorRichness = try metrics.decodeIfPresent(Double.self, forKey: .colorRichness) ?? 0.0
        } else {
            self.lineworkIntegrity = try c.decodeIfPresent(Double.self, forKey: .lineworkIntegrity) ?? 0.0
            self.whitePurity = try c.decodeIfPresent(Double.self, forKey: .whitePurity) ?? 0.0
            self.colorRichness = try c.decodeIfPresent(Double.self, forKey: .colorRichness) ?? 0.0
        }
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(overall, forKey: .overallScore)
        try c.encode(grade, forKey: .grade)
        try c.encode(autoLearnEligible, forKey: .autoLearnEligible)
        try c.encode(threshold, forKey: .threshold)
        try c.encode(isAuthorColored, forKey: .isAuthorColored)
        var metrics = c.nestedContainer(keyedBy: MetricsCodingKeys.self, forKey: .metrics)
        try metrics.encode(lineworkIntegrity, forKey: .lineworkIntegrity)
        try metrics.encode(whitePurity, forKey: .whitePurity)
        try metrics.encode(colorRichness, forKey: .colorRichness)
    }
}

public struct MangaPageInfo: Codable, Sendable, Equatable, Identifiable {
    public var index: Int
    public var displayName: String
    public var filename: String
    public var originalPath: String?
    public var originalUrl: String?
    public var colorizedUrl: String?
    public var status: String
    public var skippedColored: Bool
    public var translated: Bool
    public var qualityScore: PageQualityScore?
    public var exemplarUsed: String?
    public var exemplarsUsed: [String]
    public var adapterUsed: Bool
    public var autoHarvested: Bool
    public var learnedToMemory: Bool
    public var engineUsed: String?
    public var width: Int?
    public var height: Int?
    public var errorMessage: String?
    public var recognizedCharacters: [RecognizedCharacterDTO]
    public var translations: [BubbleTranslationDTO]

    public var id: Int { index }

    public var isColorized: Bool {
        status == "colorized"
    }

    public func resolvedOriginalRelativePath(sessionId: String) -> String {
        if let originalUrl, !originalUrl.isEmpty {
            return originalUrl
        }
        let fn = filename.isEmpty ? "page_\(String(format: "%04d", index + 1)).jpg" : filename
        return "/api/session/\(sessionId)/image/original/\(fn)"
    }

    public func resolvedColorizedRelativePath(sessionId: String) -> String? {
        if let colorizedUrl, !colorizedUrl.isEmpty {
            return colorizedUrl
        }
        guard isColorized, !filename.isEmpty else { return nil }
        return "/api/session/\(sessionId)/image/colorized/\(filename)"
    }

    public init(
        index: Int = 0,
        displayName: String? = nil,
        filename: String = "",
        originalPath: String? = nil,
        originalUrl: String? = nil,
        colorizedUrl: String? = nil,
        status: String = "pending",
        skippedColored: Bool = false,
        translated: Bool = false,
        qualityScore: PageQualityScore? = nil,
        exemplarUsed: String? = nil,
        exemplarsUsed: [String] = [],
        adapterUsed: Bool = false,
        autoHarvested: Bool = false,
        learnedToMemory: Bool = false,
        engineUsed: String? = nil,
        width: Int? = nil,
        height: Int? = nil,
        errorMessage: String? = nil,
        recognizedCharacters: [RecognizedCharacterDTO] = [],
        translations: [BubbleTranslationDTO] = []
    ) {
        self.index = index
        self.displayName = displayName ?? "Page \(index + 1)"
        self.filename = filename
        self.originalPath = originalPath
        self.originalUrl = originalUrl
        self.colorizedUrl = colorizedUrl
        self.status = status
        self.skippedColored = skippedColored
        self.translated = translated
        self.qualityScore = qualityScore
        self.exemplarUsed = exemplarUsed
        self.exemplarsUsed = exemplarsUsed
        self.adapterUsed = adapterUsed
        self.autoHarvested = autoHarvested
        self.learnedToMemory = learnedToMemory
        self.engineUsed = engineUsed
        self.width = width
        self.height = height
        self.errorMessage = errorMessage
        self.recognizedCharacters = recognizedCharacters
        self.translations = translations
    }

    private enum CodingKeys: String, CodingKey {
        case pageIndex = "page_index"
        case index
        case displayName = "display_name"
        case filename
        case originalPath = "original_path"
        case originalUrl = "original_url"
        case colorizedUrl = "colorized_url"
        case status
        case skippedColored = "skipped_colored"
        case translated
        case qualityScore = "quality_score"
        case exemplarUsed = "exemplar_used"
        case exemplarsUsed = "exemplars_used"
        case adapterUsed = "adapter_used"
        case autoHarvested = "auto_harvested"
        case learnedToMemory = "learned_to_memory"
        case engineUsed = "engine_used"
        case width
        case height
        case errorMessage = "error_msg"
        case recognizedCharacters = "recognized_characters"
        case translations
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let idx = try c.decodeIfPresent(Int.self, forKey: .pageIndex)
            ?? c.decodeIfPresent(Int.self, forKey: .index)
            ?? 0
        self.index = idx
        self.displayName = try c.decodeIfPresent(String.self, forKey: .displayName) ?? "Page \(idx + 1)"
        self.filename = try c.decodeIfPresent(String.self, forKey: .filename) ?? ""
        self.originalPath = try c.decodeIfPresent(String.self, forKey: .originalPath)
        self.originalUrl = try c.decodeIfPresent(String.self, forKey: .originalUrl)
        self.colorizedUrl = try c.decodeIfPresent(String.self, forKey: .colorizedUrl)
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "pending"
        self.skippedColored = try c.decodeIfPresent(Bool.self, forKey: .skippedColored) ?? false
        self.translated = try c.decodeIfPresent(Bool.self, forKey: .translated) ?? false
        self.qualityScore = try c.decodeIfPresent(PageQualityScore.self, forKey: .qualityScore)
        self.exemplarUsed = try c.decodeIfPresent(String.self, forKey: .exemplarUsed)
        self.exemplarsUsed = try c.decodeIfPresent([String].self, forKey: .exemplarsUsed) ?? []
        self.adapterUsed = try c.decodeIfPresent(Bool.self, forKey: .adapterUsed) ?? false
        self.autoHarvested = try c.decodeIfPresent(Bool.self, forKey: .autoHarvested) ?? false
        self.learnedToMemory = try c.decodeIfPresent(Bool.self, forKey: .learnedToMemory) ?? false
        self.engineUsed = try c.decodeIfPresent(String.self, forKey: .engineUsed)
        self.width = try c.decodeIfPresent(Int.self, forKey: .width)
        self.height = try c.decodeIfPresent(Int.self, forKey: .height)
        self.errorMessage = try c.decodeIfPresent(String.self, forKey: .errorMessage)
        self.recognizedCharacters = try c.decodeIfPresent([RecognizedCharacterDTO].self, forKey: .recognizedCharacters) ?? []
        self.translations = try c.decodeIfPresent([BubbleTranslationDTO].self, forKey: .translations) ?? []
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(index, forKey: .pageIndex)
        try c.encode(displayName, forKey: .displayName)
        try c.encode(filename, forKey: .filename)
        try c.encodeIfPresent(originalPath, forKey: .originalPath)
        try c.encodeIfPresent(originalUrl, forKey: .originalUrl)
        try c.encodeIfPresent(colorizedUrl, forKey: .colorizedUrl)
        try c.encode(status, forKey: .status)
        try c.encode(skippedColored, forKey: .skippedColored)
        try c.encode(translated, forKey: .translated)
        try c.encodeIfPresent(qualityScore, forKey: .qualityScore)
        try c.encodeIfPresent(exemplarUsed, forKey: .exemplarUsed)
        try c.encode(exemplarsUsed, forKey: .exemplarsUsed)
        try c.encode(adapterUsed, forKey: .adapterUsed)
        try c.encode(autoHarvested, forKey: .autoHarvested)
        try c.encode(learnedToMemory, forKey: .learnedToMemory)
        try c.encodeIfPresent(engineUsed, forKey: .engineUsed)
        try c.encodeIfPresent(width, forKey: .width)
        try c.encodeIfPresent(height, forKey: .height)
        try c.encodeIfPresent(errorMessage, forKey: .errorMessage)
        try c.encode(recognizedCharacters, forKey: .recognizedCharacters)
        try c.encode(translations, forKey: .translations)
    }
}

public struct MangaSessionDetail: Codable, Sendable, Equatable, Identifiable {
    public var sessionId: String
    public var batchId: String?
    public var filename: String
    public var filePath: String?
    public var ext: String
    public var totalPages: Int
    public var processedCount: Int
    public var status: String
    public var pages: [MangaPageInfo]
    public var modelProvider: String?
    public var modelName: String?
    public var style: String?
    public var saturation: Double?
    public var contrast: Double?
    public var linePreserve: Double?
    public var skipIfColored: Bool
    public var denoiseScreentone: Bool
    public var denoiseSigma: Int?
    public var recognitionMode: String?
    public var detectedPreset: String?
    public var presetTitle: String?
    public var recommendedStyle: String?
    public var isActive: Bool

    public var id: String { sessionId }

    public var progressFraction: Double {
        guard totalPages > 0 else { return 0 }
        return min(1.0, max(0.0, Double(processedCount) / Double(totalPages)))
    }

    public init(
        sessionId: String,
        batchId: String? = nil,
        filename: String,
        filePath: String? = nil,
        ext: String = "",
        totalPages: Int = 0,
        processedCount: Int = 0,
        status: String = "idle",
        pages: [MangaPageInfo] = [],
        modelProvider: String? = nil,
        modelName: String? = nil,
        style: String? = nil,
        saturation: Double? = nil,
        contrast: Double? = nil,
        linePreserve: Double? = nil,
        skipIfColored: Bool = false,
        denoiseScreentone: Bool = true,
        denoiseSigma: Int? = nil,
        recognitionMode: String? = nil,
        detectedPreset: String? = nil,
        presetTitle: String? = nil,
        recommendedStyle: String? = nil,
        isActive: Bool = false
    ) {
        self.sessionId = sessionId
        self.batchId = batchId
        self.filename = filename
        self.filePath = filePath
        self.ext = ext
        self.totalPages = totalPages
        self.processedCount = processedCount
        self.status = status
        self.pages = pages
        self.modelProvider = modelProvider
        self.modelName = modelName
        self.style = style
        self.saturation = saturation
        self.contrast = contrast
        self.linePreserve = linePreserve
        self.skipIfColored = skipIfColored
        self.denoiseScreentone = denoiseScreentone
        self.denoiseSigma = denoiseSigma
        self.recognitionMode = recognitionMode
        self.detectedPreset = detectedPreset
        self.presetTitle = presetTitle
        self.recommendedStyle = recommendedStyle
        self.isActive = isActive
    }

    private enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case batchId = "batch_id"
        case filename
        case filePath = "file_path"
        case ext
        case totalPages = "total_pages"
        case processedCount = "processed_count"
        case status
        case pages
        case modelProvider = "model_provider"
        case modelName = "model_name"
        case style
        case saturation
        case contrast
        case linePreserve = "line_preserve"
        case skipIfColored = "skip_if_colored"
        case denoiseScreentone = "denoise_screentone"
        case denoiseSigma = "denoise_sigma"
        case recognitionMode = "recognition_mode"
        case detectedPreset = "detected_preset"
        case presetId = "preset_id"
        case presetTitle = "preset_title"
        case recommendedStyle = "recommended_style"
        case isActive = "is_active"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.sessionId = try c.decodeIfPresent(String.self, forKey: .sessionId) ?? ""
        self.batchId = try c.decodeIfPresent(String.self, forKey: .batchId)
        self.filename = try c.decodeIfPresent(String.self, forKey: .filename) ?? "Untitled"
        self.filePath = try c.decodeIfPresent(String.self, forKey: .filePath)
        self.ext = try c.decodeIfPresent(String.self, forKey: .ext) ?? ""
        let decodedPages = try c.decodeIfPresent([MangaPageInfo].self, forKey: .pages) ?? []
        self.pages = decodedPages
        self.totalPages = try c.decodeIfPresent(Int.self, forKey: .totalPages) ?? decodedPages.count
        self.processedCount = try c.decodeIfPresent(Int.self, forKey: .processedCount)
            ?? decodedPages.filter { $0.isColorized }.count
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "idle"
        self.modelProvider = try c.decodeIfPresent(String.self, forKey: .modelProvider)
        self.modelName = try c.decodeIfPresent(String.self, forKey: .modelName)
        self.style = try c.decodeIfPresent(String.self, forKey: .style)
        self.saturation = try c.decodeIfPresent(Double.self, forKey: .saturation)
        self.contrast = try c.decodeIfPresent(Double.self, forKey: .contrast)
        self.linePreserve = try c.decodeIfPresent(Double.self, forKey: .linePreserve)
        self.skipIfColored = try c.decodeIfPresent(Bool.self, forKey: .skipIfColored) ?? false
        self.denoiseScreentone = try c.decodeIfPresent(Bool.self, forKey: .denoiseScreentone) ?? true
        self.denoiseSigma = try c.decodeIfPresent(Int.self, forKey: .denoiseSigma)
        self.recognitionMode = try c.decodeIfPresent(String.self, forKey: .recognitionMode)
        self.detectedPreset = try c.decodeIfPresent(String.self, forKey: .detectedPreset)
            ?? c.decodeIfPresent(String.self, forKey: .presetId)
        self.presetTitle = try c.decodeIfPresent(String.self, forKey: .presetTitle)
        self.recommendedStyle = try c.decodeIfPresent(String.self, forKey: .recommendedStyle)
        self.isActive = try c.decodeIfPresent(Bool.self, forKey: .isActive) ?? false
    }

    public func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(sessionId, forKey: .sessionId)
        try c.encodeIfPresent(batchId, forKey: .batchId)
        try c.encode(filename, forKey: .filename)
        try c.encodeIfPresent(filePath, forKey: .filePath)
        try c.encode(ext, forKey: .ext)
        try c.encode(totalPages, forKey: .totalPages)
        try c.encode(processedCount, forKey: .processedCount)
        try c.encode(status, forKey: .status)
        try c.encode(pages, forKey: .pages)
        try c.encodeIfPresent(modelProvider, forKey: .modelProvider)
        try c.encodeIfPresent(modelName, forKey: .modelName)
        try c.encodeIfPresent(style, forKey: .style)
        try c.encodeIfPresent(saturation, forKey: .saturation)
        try c.encodeIfPresent(contrast, forKey: .contrast)
        try c.encodeIfPresent(linePreserve, forKey: .linePreserve)
        try c.encode(skipIfColored, forKey: .skipIfColored)
        try c.encode(denoiseScreentone, forKey: .denoiseScreentone)
        try c.encodeIfPresent(denoiseSigma, forKey: .denoiseSigma)
        try c.encodeIfPresent(recognitionMode, forKey: .recognitionMode)
        try c.encodeIfPresent(detectedPreset, forKey: .detectedPreset)
        try c.encodeIfPresent(presetTitle, forKey: .presetTitle)
        try c.encodeIfPresent(recommendedStyle, forKey: .recommendedStyle)
        try c.encode(isActive, forKey: .isActive)
    }
}

// MARK: - AI Provider & Colorization Configuration

public struct AIModelVariant: Codable, Sendable, Equatable, Hashable, Identifiable {
    public var id: String
    public var label: String

    public init(id: String, label: String) {
        self.id = id
        self.label = label
    }
}

public enum AIProvider: String, Codable, Sendable, CaseIterable, Identifiable {
    case resnextGenerator = "resnext_generator"
    case googleNano = "google_nano"
    case appleFoundation = "apple_foundation"
    case localSmart = "local_smart"

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .resnextGenerator: return "ResNeXt Net"
        case .googleNano: return "Google Nano"
        case .appleFoundation: return "Apple AI"
        case .localSmart: return "Smart Local"
        }
    }

    public var subtitle: String {
        switch self {
        case .resnextGenerator: return "Deep Generator"
        case .googleNano: return "Google AI"
        case .appleFoundation: return "Apple Silicon"
        case .localSmart: return "Offline Palette"
        }
    }

    public var sfSymbol: String {
        switch self {
        case .resnextGenerator: return "cpu.fill"
        case .googleNano: return "sparkles"
        case .appleFoundation: return "memorychip.fill"
        case .localSmart: return "paintpalette.fill"
        }
    }

    public var emoji: String {
        switch self {
        case .resnextGenerator: return "🧬"
        case .googleNano: return "🍌"
        case .appleFoundation: return "🍏"
        case .localSmart: return "🎨"
        }
    }

    public var requiresAPIKey: Bool {
        self == .googleNano
    }

    public var variants: [AIModelVariant] {
        switch self {
        case .resnextGenerator:
            return [
                AIModelVariant(id: "resnext-v2-manga", label: "ResNeXt-based Manga Generator (Deep U-Net + FFDNet)"),
                AIModelVariant(id: "resnext-chroma-hd", label: "ResNeXt High-Res Chroma Fusion (Native Detail)"),
                AIModelVariant(id: "resnext-comicolor", label: "ResNeXt Comicolorization Pipeline"),
            ]
        case .googleNano:
            return [
                AIModelVariant(id: "gemini-3.1-flash-image", label: "Gemini 3.1 Flash Image (Nano Banana - Recommended)"),
                AIModelVariant(id: "gemini-3-pro-image", label: "Gemini 3 Pro Image (4K Studio Quality)"),
                AIModelVariant(id: "gemini-3.1-flash-lite-image", label: "Gemini 3.1 Flash Lite Image (Fast Vision)"),
                AIModelVariant(id: "gemini-2.5-flash-image", label: "Gemini 2.5 Flash Image"),
                AIModelVariant(id: "imagen-3.0-generate-002", label: "Google Imagen 3 Colorizer"),
                AIModelVariant(id: "nano-banana", label: "Google Nano Banana (Default Alias)"),
            ]
        case .appleFoundation:
            return [
                AIModelVariant(id: "apple-foundation-v1", label: "Apple Foundation Model (Vision Neural Engine)"),
                AIModelVariant(id: "apple-mlx-manga", label: "Apple MLX Silicon Acceleration"),
                AIModelVariant(id: "apple-coreml-manga", label: "Apple CoreML Pipeline"),
            ]
        case .localSmart:
            return [
                AIModelVariant(id: "semantic-manga-v2", label: "Semantic Manga Colorizer v2 (Multi-Band, Offline)"),
                AIModelVariant(id: "semantic-anime-pastel", label: "Semantic Anime Pastel Engine"),
                AIModelVariant(id: "semantic-dark-fantasy", label: "Semantic Dark Fantasy Engine"),
            ]
        }
    }

    public var defaultModelName: String {
        variants.first?.id ?? "resnext-v2-manga"
    }
}

public enum ColorAestheticStyle: String, Codable, Sendable, CaseIterable, Identifiable {
    case natural
    case geminiAnime = "gemini_anime"
    case shonenVivid = "shonen_vivid"
    case animePastel = "anime_pastel"
    case retro90s = "retro_90s"
    case darkFantasy = "dark_fantasy"
    case cyberpunk

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .natural: return "Natural Studio"
        case .geminiAnime: return "Gemini Anime Vibrant"
        case .shonenVivid: return "Shonen Vivid"
        case .animePastel: return "Soft Pastel Anime"
        case .retro90s: return "Retro 90s Anime"
        case .darkFantasy: return "Dark Fantasy"
        case .cyberpunk: return "Cyberpunk Neon"
        }
    }

    public var sfSymbol: String {
        switch self {
        case .natural: return "leaf.fill"
        case .geminiAnime: return "sparkles"
        case .shonenVivid: return "flame.fill"
        case .animePastel: return "camera.macro"
        case .retro90s: return "tv.fill"
        case .darkFantasy: return "moon.stars.fill"
        case .cyberpunk: return "bolt.fill"
        }
    }
}

public enum TranslationEngine: String, Codable, Sendable, CaseIterable, Identifiable {
    case auto
    case local
    case gemini

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .auto: return "Auto (Gemini if key set, else Manga-OCR)"
        case .local: return "Local Manga-OCR + Deep Translator"
        case .gemini: return "Google Gemini Multimodal Vision"
        }
    }
}

public enum TargetLanguage: String, Codable, Sendable, CaseIterable, Identifiable {
    case en
    case es
    case fr
    case de
    case vi
    case ja
    case ko
    case zhCN = "zh-CN"

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .en: return "English (EN)"
        case .es: return "Spanish (ES)"
        case .fr: return "French (FR)"
        case .de: return "German (DE)"
        case .vi: return "Vietnamese (VI)"
        case .ja: return "Japanese (JA)"
        case .ko: return "Korean (KO)"
        case .zhCN: return "Chinese Simplified (ZH)"
        }
    }
}

public enum RecognitionMode: String, Codable, Sendable, CaseIterable, Identifiable {
    case auto
    case offlineAI = "offline_ai"
    case heuristics
    case gemini
    case none

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .auto: return "Auto Detect"
        case .offlineAI: return "Offline AI (Manga109 YOLO + CLIP)"
        case .heuristics: return "Fast Heuristics"
        case .gemini: return "Google Gemini Vision"
        case .none: return "Disabled"
        }
    }
}

public struct ColorizeConfig: Codable, Sendable, Equatable {
    public var modelProvider: AIProvider
    public var modelName: String
    public var apiKey: String
    public var style: ColorAestheticStyle
    public var saturation: Double
    public var contrast: Double
    public var linePreserve: Double
    public var skipIfColored: Bool
    public var denoiseScreentone: Bool
    public var denoiseSigma: Int
    public var recognitionMode: RecognitionMode
    public var activeCharacterNames: [String]?
    public var translatePage: Bool
    public var translationEngine: TranslationEngine
    public var targetLanguage: TargetLanguage

    public init(
        modelProvider: AIProvider = .resnextGenerator,
        modelName: String? = nil,
        apiKey: String = "",
        style: ColorAestheticStyle = .geminiAnime,
        saturation: Double = 0.7,
        contrast: Double = 1.0,
        linePreserve: Double = 0.66,
        skipIfColored: Bool = false,
        denoiseScreentone: Bool = true,
        denoiseSigma: Int = 25,
        recognitionMode: RecognitionMode = .auto,
        activeCharacterNames: [String]? = nil,
        translatePage: Bool = false,
        translationEngine: TranslationEngine = .auto,
        targetLanguage: TargetLanguage = .en
    ) {
        self.modelProvider = modelProvider
        self.modelName = modelName ?? modelProvider.defaultModelName
        self.apiKey = apiKey
        self.style = style
        self.saturation = saturation
        self.contrast = contrast
        self.linePreserve = linePreserve
        self.skipIfColored = skipIfColored
        self.denoiseScreentone = denoiseScreentone
        self.denoiseSigma = denoiseSigma
        self.recognitionMode = recognitionMode
        self.activeCharacterNames = activeCharacterNames
        self.translatePage = translatePage
        self.translationEngine = translationEngine
        self.targetLanguage = targetLanguage
    }
}

public struct PreviewResultDTO: Codable, Sendable, Equatable {
    public var status: String
    public var pageIndex: Int
    public var colorizedUrl: String?
    public var engine: String?
    public var pageInfo: MangaPageInfo?
    public var qualityScore: PageQualityScore?
    public var recognizedCharacters: [RecognizedCharacterDTO]
    public var translations: [BubbleTranslationDTO]
    public var translated: Bool
    public var exemplarUsed: String?
    public var exemplarsUsed: [String]
    public var adapterUsed: Bool
    public var seriesKey: String?
    public var processedCount: Int
    public var totalPages: Int

    public init(
        status: String = "success",
        pageIndex: Int = 0,
        colorizedUrl: String? = nil,
        engine: String? = nil,
        pageInfo: MangaPageInfo? = nil,
        qualityScore: PageQualityScore? = nil,
        recognizedCharacters: [RecognizedCharacterDTO] = [],
        translations: [BubbleTranslationDTO] = [],
        translated: Bool = false,
        exemplarUsed: String? = nil,
        exemplarsUsed: [String] = [],
        adapterUsed: Bool = false,
        seriesKey: String? = nil,
        processedCount: Int = 0,
        totalPages: Int = 0
    ) {
        self.status = status
        self.pageIndex = pageIndex
        self.colorizedUrl = colorizedUrl
        self.engine = engine
        self.pageInfo = pageInfo
        self.qualityScore = qualityScore
        self.recognizedCharacters = recognizedCharacters
        self.translations = translations
        self.translated = translated
        self.exemplarUsed = exemplarUsed
        self.exemplarsUsed = exemplarsUsed
        self.adapterUsed = adapterUsed
        self.seriesKey = seriesKey
        self.processedCount = processedCount
        self.totalPages = totalPages
    }

    private enum CodingKeys: String, CodingKey {
        case status
        case pageIndex = "page_index"
        case colorizedUrl = "colorized_url"
        case engine
        case pageInfo = "page_info"
        case qualityScore = "quality_score"
        case recognizedCharacters = "recognized_characters"
        case translations
        case translated
        case exemplarUsed = "exemplar_used"
        case exemplarsUsed = "exemplars_used"
        case adapterUsed = "adapter_used"
        case seriesKey = "series_key"
        case processedCount = "processed_count"
        case totalPages = "total_pages"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "success"
        self.pageIndex = try c.decodeIfPresent(Int.self, forKey: .pageIndex) ?? 0
        self.colorizedUrl = try c.decodeIfPresent(String.self, forKey: .colorizedUrl)
        self.engine = try c.decodeIfPresent(String.self, forKey: .engine)
        self.pageInfo = try c.decodeIfPresent(MangaPageInfo.self, forKey: .pageInfo)
        self.qualityScore = try c.decodeIfPresent(PageQualityScore.self, forKey: .qualityScore)
        self.recognizedCharacters = try c.decodeIfPresent([RecognizedCharacterDTO].self, forKey: .recognizedCharacters) ?? []
        self.translations = try c.decodeIfPresent([BubbleTranslationDTO].self, forKey: .translations) ?? []
        self.translated = try c.decodeIfPresent(Bool.self, forKey: .translated) ?? false
        self.exemplarUsed = try c.decodeIfPresent(String.self, forKey: .exemplarUsed)
        self.exemplarsUsed = try c.decodeIfPresent([String].self, forKey: .exemplarsUsed) ?? []
        self.adapterUsed = try c.decodeIfPresent(Bool.self, forKey: .adapterUsed) ?? false
        self.seriesKey = try c.decodeIfPresent(String.self, forKey: .seriesKey)
        self.processedCount = try c.decodeIfPresent(Int.self, forKey: .processedCount) ?? 0
        self.totalPages = try c.decodeIfPresent(Int.self, forKey: .totalPages) ?? 0
    }
}

public struct BatchStatusDTO: Codable, Sendable, Equatable {
    public var isRunning: Bool
    public var totalDocs: Int
    public var completedDocs: Int
    public var currentIndex: Int
    public var currentSessionId: String?
    public var sessionIds: [String]

    public init(
        isRunning: Bool = false,
        totalDocs: Int = 0,
        completedDocs: Int = 0,
        currentIndex: Int = 0,
        currentSessionId: String? = nil,
        sessionIds: [String] = []
    ) {
        self.isRunning = isRunning
        self.totalDocs = totalDocs
        self.completedDocs = completedDocs
        self.currentIndex = currentIndex
        self.currentSessionId = currentSessionId
        self.sessionIds = sessionIds
    }

    private enum CodingKeys: String, CodingKey {
        case isRunning = "is_running"
        case totalDocs = "total_docs"
        case completedDocs = "completed_docs"
        case currentIndex = "current_index"
        case currentSessionId = "current_session_id"
        case sessionIds = "session_ids"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.isRunning = try c.decodeIfPresent(Bool.self, forKey: .isRunning) ?? false
        self.totalDocs = try c.decodeIfPresent(Int.self, forKey: .totalDocs) ?? 0
        self.completedDocs = try c.decodeIfPresent(Int.self, forKey: .completedDocs) ?? 0
        self.currentIndex = try c.decodeIfPresent(Int.self, forKey: .currentIndex) ?? 0
        self.currentSessionId = try c.decodeIfPresent(String.self, forKey: .currentSessionId)
        self.sessionIds = try c.decodeIfPresent([String].self, forKey: .sessionIds) ?? []
    }
}

// MARK: - Presets & Character Palette

public struct PresetCharacterDTO: Codable, Sendable, Equatable, Identifiable {
    public var name: String
    public var hairHex: String
    public var skinHex: String
    public var costumeHex: String
    public var extraHex: String
    public var eyeHex: String
    public var notes: String
    public var visualTraits: [String]
    public var keywords: [String]

    public var id: String { name }

    public init(
        name: String,
        hairHex: String = "",
        skinHex: String = "",
        costumeHex: String = "",
        extraHex: String = "",
        eyeHex: String = "",
        notes: String = "",
        visualTraits: [String] = [],
        keywords: [String] = []
    ) {
        self.name = name
        self.hairHex = hairHex
        self.skinHex = skinHex
        self.costumeHex = costumeHex
        self.extraHex = extraHex
        self.eyeHex = eyeHex
        self.notes = notes
        self.visualTraits = visualTraits
        self.keywords = keywords
    }

    private enum CodingKeys: String, CodingKey {
        case name
        case hairHex = "hair_hex"
        case skinHex = "skin_hex"
        case costumeHex = "costume_hex"
        case extraHex = "extra_hex"
        case eyeHex = "eye_hex"
        case notes
        case visualTraits = "visual_traits"
        case keywords
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.name = try c.decodeIfPresent(String.self, forKey: .name) ?? ""
        self.hairHex = try c.decodeIfPresent(String.self, forKey: .hairHex) ?? ""
        self.skinHex = try c.decodeIfPresent(String.self, forKey: .skinHex) ?? ""
        self.costumeHex = try c.decodeIfPresent(String.self, forKey: .costumeHex) ?? ""
        self.extraHex = try c.decodeIfPresent(String.self, forKey: .extraHex) ?? ""
        self.eyeHex = try c.decodeIfPresent(String.self, forKey: .eyeHex) ?? ""
        self.notes = try c.decodeIfPresent(String.self, forKey: .notes) ?? ""
        self.visualTraits = try c.decodeIfPresent([String].self, forKey: .visualTraits) ?? []
        self.keywords = try c.decodeIfPresent([String].self, forKey: .keywords) ?? []
    }
}

public struct MangaPresetDTO: Codable, Sendable, Equatable, Identifiable {
    public var id: String
    public var title: String
    public var aliases: [String]
    public var description: String
    public var recommendedStyle: String
    public var themeColor: String
    public var characters: [PresetCharacterDTO]
    public var promptGuidance: String

    public init(
        id: String,
        title: String,
        aliases: [String] = [],
        description: String = "",
        recommendedStyle: String = "shonen_vivid",
        themeColor: String = "#e62c39",
        characters: [PresetCharacterDTO] = [],
        promptGuidance: String = ""
    ) {
        self.id = id
        self.title = title
        self.aliases = aliases
        self.description = description
        self.recommendedStyle = recommendedStyle
        self.themeColor = themeColor
        self.characters = characters
        self.promptGuidance = promptGuidance
    }

    private enum CodingKeys: String, CodingKey {
        case id
        case title
        case aliases
        case description
        case recommendedStyle = "recommended_style"
        case themeColor = "theme_color"
        case characters
        case promptGuidance = "prompt_guidance"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.id = try c.decodeIfPresent(String.self, forKey: .id) ?? ""
        self.title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        self.aliases = try c.decodeIfPresent([String].self, forKey: .aliases) ?? []
        self.description = try c.decodeIfPresent(String.self, forKey: .description) ?? ""
        self.recommendedStyle = try c.decodeIfPresent(String.self, forKey: .recommendedStyle) ?? "shonen_vivid"
        self.themeColor = try c.decodeIfPresent(String.self, forKey: .themeColor) ?? "#e62c39"
        self.characters = try c.decodeIfPresent([PresetCharacterDTO].self, forKey: .characters) ?? []
        self.promptGuidance = try c.decodeIfPresent(String.self, forKey: .promptGuidance) ?? ""
    }
}

public struct CharacterEntryDTO: Codable, Sendable, Equatable, Identifiable {
    public var name: String
    public var hairHex: String
    public var skinHex: String
    public var costumeHex: String
    public var extraHex: String
    public var eyeHex: String
    public var notes: String
    public var visualTraits: [String]
    public var keywords: [String]
    public var boundingBox: [Double]?

    public var id: String { name }

    public init(
        name: String,
        hairHex: String = "#1A1A1A",
        skinHex: String = "#F4C5A0",
        costumeHex: String = "#3A7BFF",
        extraHex: String = "#FFCE47",
        eyeHex: String = "#3E2723",
        notes: String = "",
        visualTraits: [String] = [],
        keywords: [String] = [],
        boundingBox: [Double]? = nil
    ) {
        self.name = name
        self.hairHex = hairHex
        self.skinHex = skinHex
        self.costumeHex = costumeHex
        self.extraHex = extraHex
        self.eyeHex = eyeHex
        self.notes = notes
        self.visualTraits = visualTraits
        self.keywords = keywords
        self.boundingBox = boundingBox
    }

    private enum CodingKeys: String, CodingKey {
        case name
        case hairHex = "hair_hex"
        case skinHex = "skin_hex"
        case costumeHex = "costume_hex"
        case extraHex = "extra_hex"
        case eyeHex = "eye_hex"
        case notes
        case visualTraits = "visual_traits"
        case keywords
        case boundingBox = "bounding_box"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.name = try c.decodeIfPresent(String.self, forKey: .name) ?? ""
        self.hairHex = try c.decodeIfPresent(String.self, forKey: .hairHex) ?? ""
        self.skinHex = try c.decodeIfPresent(String.self, forKey: .skinHex) ?? ""
        self.costumeHex = try c.decodeIfPresent(String.self, forKey: .costumeHex) ?? ""
        self.extraHex = try c.decodeIfPresent(String.self, forKey: .extraHex) ?? ""
        self.eyeHex = try c.decodeIfPresent(String.self, forKey: .eyeHex) ?? ""
        self.notes = try c.decodeIfPresent(String.self, forKey: .notes) ?? ""
        self.visualTraits = try c.decodeIfPresent([String].self, forKey: .visualTraits) ?? []
        self.keywords = try c.decodeIfPresent([String].self, forKey: .keywords) ?? []
        self.boundingBox = try c.decodeIfPresent([Double].self, forKey: .boundingBox)
    }
}

public struct CharacterPaletteDTO: Codable, Sendable, Equatable {
    public var characters: [CharacterEntryDTO]
    public var presetId: String
    public var presetTitle: String

    public init(
        characters: [CharacterEntryDTO] = [],
        presetId: String = "",
        presetTitle: String = ""
    ) {
        self.characters = characters
        self.presetId = presetId
        self.presetTitle = presetTitle
    }

    private enum CodingKeys: String, CodingKey {
        case characters
        case presetId = "preset_id"
        case presetTitle = "preset_title"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.characters = try c.decodeIfPresent([CharacterEntryDTO].self, forKey: .characters) ?? []
        self.presetId = try c.decodeIfPresent(String.self, forKey: .presetId) ?? ""
        self.presetTitle = try c.decodeIfPresent(String.self, forKey: .presetTitle) ?? ""
    }
}

// MARK: - Series Memory & LoRA Adapter

public struct LearnedCharacterTraitDTO: Codable, Sendable, Equatable, Identifiable {
    public var name: String
    public var hairHex: String
    public var skinHex: String
    public var costumeHex: String
    public var eyeHex: String
    public var extraHex: String
    public var confidence: Double
    public var confirmationCount: Int
    public var lastUpdated: Double
    public var sourceSessions: [String]

    public var id: String { name }

    public init(
        name: String = "",
        hairHex: String = "",
        skinHex: String = "",
        costumeHex: String = "",
        eyeHex: String = "",
        extraHex: String = "",
        confidence: Double = 1.0,
        confirmationCount: Int = 1,
        lastUpdated: Double = 0,
        sourceSessions: [String] = []
    ) {
        self.name = name
        self.hairHex = hairHex
        self.skinHex = skinHex
        self.costumeHex = costumeHex
        self.eyeHex = eyeHex
        self.extraHex = extraHex
        self.confidence = confidence
        self.confirmationCount = confirmationCount
        self.lastUpdated = lastUpdated
        self.sourceSessions = sourceSessions
    }

    private enum CodingKeys: String, CodingKey {
        case name
        case hairHex = "hair_hex"
        case skinHex = "skin_hex"
        case costumeHex = "costume_hex"
        case eyeHex = "eye_hex"
        case extraHex = "extra_hex"
        case confidence
        case confirmationCount = "confirmation_count"
        case lastUpdated = "last_updated"
        case sourceSessions = "source_sessions"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.name = try c.decodeIfPresent(String.self, forKey: .name) ?? ""
        self.hairHex = try c.decodeIfPresent(String.self, forKey: .hairHex) ?? ""
        self.skinHex = try c.decodeIfPresent(String.self, forKey: .skinHex) ?? ""
        self.costumeHex = try c.decodeIfPresent(String.self, forKey: .costumeHex) ?? ""
        self.eyeHex = try c.decodeIfPresent(String.self, forKey: .eyeHex) ?? ""
        self.extraHex = try c.decodeIfPresent(String.self, forKey: .extraHex) ?? ""
        self.confidence = try c.decodeIfPresent(Double.self, forKey: .confidence) ?? 1.0
        self.confirmationCount = try c.decodeIfPresent(Int.self, forKey: .confirmationCount) ?? 1
        self.lastUpdated = try c.decodeIfPresent(Double.self, forKey: .lastUpdated) ?? 0
        self.sourceSessions = try c.decodeIfPresent([String].self, forKey: .sourceSessions) ?? []
    }
}

public struct SeriesExemplarDTO: Codable, Sendable, Equatable, Identifiable {
    public var pageIndex: Int
    public var sessionId: String?
    public var characterNames: [String]
    public var meanL: Double?
    public var style: String
    public var pinned: Bool
    public var createdAt: Double?
    public var imageUrl: String?
    public var imagePath: String?
    public var exists: Bool

    public var id: String { "\(sessionId ?? "series")-\(pageIndex)" }

    public init(
        pageIndex: Int = 0,
        sessionId: String? = nil,
        characterNames: [String] = [],
        meanL: Double? = nil,
        style: String = "manga",
        pinned: Bool = false,
        createdAt: Double? = nil,
        imageUrl: String? = nil,
        imagePath: String? = nil,
        exists: Bool = true
    ) {
        self.pageIndex = pageIndex
        self.sessionId = sessionId
        self.characterNames = characterNames
        self.meanL = meanL
        self.style = style
        self.pinned = pinned
        self.createdAt = createdAt
        self.imageUrl = imageUrl
        self.imagePath = imagePath
        self.exists = exists
    }

    private enum CodingKeys: String, CodingKey {
        case pageIndex = "page_index"
        case sessionId = "session_id"
        case characterNames = "character_names"
        case meanL = "mean_l"
        case style
        case pinned
        case createdAt = "created_at"
        case imageUrl = "image_url"
        case imagePath = "image_path"
        case exists
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.pageIndex = try c.decodeIfPresent(Int.self, forKey: .pageIndex) ?? 0
        self.sessionId = try c.decodeIfPresent(String.self, forKey: .sessionId)
        self.characterNames = try c.decodeIfPresent([String].self, forKey: .characterNames) ?? []
        self.meanL = try c.decodeIfPresent(Double.self, forKey: .meanL)
        self.style = try c.decodeIfPresent(String.self, forKey: .style) ?? "manga"
        self.pinned = try c.decodeIfPresent(Bool.self, forKey: .pinned) ?? false
        self.createdAt = try c.decodeIfPresent(Double.self, forKey: .createdAt)
        self.imageUrl = try c.decodeIfPresent(String.self, forKey: .imageUrl)
        self.imagePath = try c.decodeIfPresent(String.self, forKey: .imagePath)
        self.exists = try c.decodeIfPresent(Bool.self, forKey: .exists) ?? true
    }
}

public struct SeriesMemoryDTO: Codable, Sendable, Equatable {
    public var seriesKey: String
    public var title: String
    public var characters: [String: LearnedCharacterTraitDTO]
    public var exemplarPages: [SeriesExemplarDTO]
    public var approvedPagesCount: Int
    public var autoLearnedCount: Int
    public var autoRefineEnabled: Bool
    public var autoHarvestThreshold: Double
    public var autoRefineInterval: Int
    public var unrefinedPagesCount: Int
    public var qualityScores: [String: Double]
    public var preferredStyle: String?
    public var preferredSaturation: Double?
    public var preferredContrast: Double?
    public var preferredLinePreserve: Double?
    public var lastUpdated: Double

    public init(
        seriesKey: String = "",
        title: String = "",
        characters: [String: LearnedCharacterTraitDTO] = [:],
        exemplarPages: [SeriesExemplarDTO] = [],
        approvedPagesCount: Int = 0,
        autoLearnedCount: Int = 0,
        autoRefineEnabled: Bool = true,
        autoHarvestThreshold: Double = 0.82,
        autoRefineInterval: Int = 5,
        unrefinedPagesCount: Int = 0,
        qualityScores: [String: Double] = [:],
        preferredStyle: String? = nil,
        preferredSaturation: Double? = nil,
        preferredContrast: Double? = nil,
        preferredLinePreserve: Double? = nil,
        lastUpdated: Double = 0
    ) {
        self.seriesKey = seriesKey
        self.title = title
        self.characters = characters
        self.exemplarPages = exemplarPages
        self.approvedPagesCount = approvedPagesCount
        self.autoLearnedCount = autoLearnedCount
        self.autoRefineEnabled = autoRefineEnabled
        self.autoHarvestThreshold = autoHarvestThreshold
        self.autoRefineInterval = autoRefineInterval
        self.unrefinedPagesCount = unrefinedPagesCount
        self.qualityScores = qualityScores
        self.preferredStyle = preferredStyle
        self.preferredSaturation = preferredSaturation
        self.preferredContrast = preferredContrast
        self.preferredLinePreserve = preferredLinePreserve
        self.lastUpdated = lastUpdated
    }

    private enum CodingKeys: String, CodingKey {
        case seriesKey = "series_key"
        case title
        case characters
        case exemplarPages = "exemplar_pages"
        case approvedPagesCount = "approved_pages_count"
        case autoLearnedCount = "auto_learned_count"
        case autoRefineEnabled = "auto_refine_enabled"
        case autoHarvestThreshold = "auto_harvest_threshold"
        case autoRefineInterval = "auto_refine_interval"
        case unrefinedPagesCount = "unrefined_pages_count"
        case qualityScores = "quality_scores"
        case preferredStyle = "preferred_style"
        case preferredSaturation = "preferred_saturation"
        case preferredContrast = "preferred_contrast"
        case preferredLinePreserve = "preferred_line_preserve"
        case lastUpdated = "last_updated"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.seriesKey = try c.decodeIfPresent(String.self, forKey: .seriesKey) ?? ""
        self.title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        self.characters = try c.decodeIfPresent([String: LearnedCharacterTraitDTO].self, forKey: .characters) ?? [:]
        self.exemplarPages = try c.decodeIfPresent([SeriesExemplarDTO].self, forKey: .exemplarPages) ?? []
        self.approvedPagesCount = try c.decodeIfPresent(Int.self, forKey: .approvedPagesCount) ?? 0
        self.autoLearnedCount = try c.decodeIfPresent(Int.self, forKey: .autoLearnedCount) ?? 0
        self.autoRefineEnabled = try c.decodeIfPresent(Bool.self, forKey: .autoRefineEnabled) ?? true
        self.autoHarvestThreshold = try c.decodeIfPresent(Double.self, forKey: .autoHarvestThreshold) ?? 0.82
        self.autoRefineInterval = try c.decodeIfPresent(Int.self, forKey: .autoRefineInterval) ?? 5
        self.unrefinedPagesCount = try c.decodeIfPresent(Int.self, forKey: .unrefinedPagesCount) ?? 0
        self.qualityScores = try c.decodeIfPresent([String: Double].self, forKey: .qualityScores) ?? [:]
        self.preferredStyle = try c.decodeIfPresent(String.self, forKey: .preferredStyle)
        self.preferredSaturation = try c.decodeIfPresent(Double.self, forKey: .preferredSaturation)
        self.preferredContrast = try c.decodeIfPresent(Double.self, forKey: .preferredContrast)
        self.preferredLinePreserve = try c.decodeIfPresent(Double.self, forKey: .preferredLinePreserve)
        self.lastUpdated = try c.decodeIfPresent(Double.self, forKey: .lastUpdated) ?? 0
    }
}

public struct SeriesMemoryResponseDTO: Codable, Sendable, Equatable {
    public var status: String
    public var sessionId: String?
    public var seriesKey: String
    public var title: String
    public var message: String?
    public var memory: SeriesMemoryDTO?

    public init(
        status: String = "ok",
        sessionId: String? = nil,
        seriesKey: String = "",
        title: String = "",
        message: String? = nil,
        memory: SeriesMemoryDTO? = nil
    ) {
        self.status = status
        self.sessionId = sessionId
        self.seriesKey = seriesKey
        self.title = title
        self.message = message
        self.memory = memory
    }

    private enum CodingKeys: String, CodingKey {
        case status
        case sessionId = "session_id"
        case seriesKey = "series_key"
        case title
        case message
        case memory
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "ok"
        self.sessionId = try c.decodeIfPresent(String.self, forKey: .sessionId)
        self.seriesKey = try c.decodeIfPresent(String.self, forKey: .seriesKey) ?? ""
        self.title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        self.message = try c.decodeIfPresent(String.self, forKey: .message)
        self.memory = try c.decodeIfPresent(SeriesMemoryDTO.self, forKey: .memory)
    }
}

public struct AdapterStatusDTO: Codable, Sendable, Equatable {
    public var status: String
    public var seriesKey: String
    public var step: Int?
    public var totalSteps: Int?
    public var progress: Double?
    public var loss: Double?
    public var elapsed: Double?
    public var fileSize: Int?
    public var lastTrained: Double?
    public var steps: Int?
    public var samplesCount: Int?

    public var isReady: Bool { status == "ready" }
    public var isTraining: Bool { status == "training" || status == "training_started" }

    public init(
        status: String = "not_trained",
        seriesKey: String = "",
        step: Int? = nil,
        totalSteps: Int? = nil,
        progress: Double? = nil,
        loss: Double? = nil,
        elapsed: Double? = nil,
        fileSize: Int? = nil,
        lastTrained: Double? = nil,
        steps: Int? = nil,
        samplesCount: Int? = nil
    ) {
        self.status = status
        self.seriesKey = seriesKey
        self.step = step
        self.totalSteps = totalSteps
        self.progress = progress
        self.loss = loss
        self.elapsed = elapsed
        self.fileSize = fileSize
        self.lastTrained = lastTrained
        self.steps = steps
        self.samplesCount = samplesCount
    }

    private enum CodingKeys: String, CodingKey {
        case status
        case seriesKey = "series_key"
        case step
        case totalSteps = "total_steps"
        case progress
        case loss
        case elapsed
        case fileSize = "file_size"
        case lastTrained = "last_trained"
        case steps
        case samplesCount = "samples_count"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "not_trained"
        self.seriesKey = try c.decodeIfPresent(String.self, forKey: .seriesKey) ?? ""
        self.step = try c.decodeIfPresent(Int.self, forKey: .step)
        self.totalSteps = try c.decodeIfPresent(Int.self, forKey: .totalSteps)
        self.progress = try c.decodeIfPresent(Double.self, forKey: .progress)
        self.loss = try c.decodeIfPresent(Double.self, forKey: .loss)
        self.elapsed = try c.decodeIfPresent(Double.self, forKey: .elapsed)
        self.fileSize = try c.decodeIfPresent(Int.self, forKey: .fileSize)
        self.lastTrained = try c.decodeIfPresent(Double.self, forKey: .lastTrained)
        self.steps = try c.decodeIfPresent(Int.self, forKey: .steps)
        self.samplesCount = try c.decodeIfPresent(Int.self, forKey: .samplesCount)
    }
}

public struct AutoRefineSettingsDTO: Codable, Sendable, Equatable {
    public var seriesKey: String
    public var autoRefineEnabled: Bool
    public var autoHarvestThreshold: Double
    public var autoRefineInterval: Int
    public var unrefinedPagesCount: Int
    public var autoLearnedCount: Int
    public var totalExemplars: Int

    public init(
        seriesKey: String = "",
        autoRefineEnabled: Bool = true,
        autoHarvestThreshold: Double = 0.82,
        autoRefineInterval: Int = 5,
        unrefinedPagesCount: Int = 0,
        autoLearnedCount: Int = 0,
        totalExemplars: Int = 0
    ) {
        self.seriesKey = seriesKey
        self.autoRefineEnabled = autoRefineEnabled
        self.autoHarvestThreshold = autoHarvestThreshold
        self.autoRefineInterval = autoRefineInterval
        self.unrefinedPagesCount = unrefinedPagesCount
        self.autoLearnedCount = autoLearnedCount
        self.totalExemplars = totalExemplars
    }

    private enum CodingKeys: String, CodingKey {
        case seriesKey = "series_key"
        case autoRefineEnabled = "auto_refine_enabled"
        case autoHarvestThreshold = "auto_harvest_threshold"
        case autoRefineInterval = "auto_refine_interval"
        case unrefinedPagesCount = "unrefined_pages_count"
        case autoLearnedCount = "auto_learned_count"
        case totalExemplars = "total_exemplars"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.seriesKey = try c.decodeIfPresent(String.self, forKey: .seriesKey) ?? ""
        self.autoRefineEnabled = try c.decodeIfPresent(Bool.self, forKey: .autoRefineEnabled) ?? true
        self.autoHarvestThreshold = try c.decodeIfPresent(Double.self, forKey: .autoHarvestThreshold) ?? 0.82
        self.autoRefineInterval = try c.decodeIfPresent(Int.self, forKey: .autoRefineInterval) ?? 5
        self.unrefinedPagesCount = try c.decodeIfPresent(Int.self, forKey: .unrefinedPagesCount) ?? 0
        self.autoLearnedCount = try c.decodeIfPresent(Int.self, forKey: .autoLearnedCount) ?? 0
        self.totalExemplars = try c.decodeIfPresent(Int.self, forKey: .totalExemplars) ?? 0
    }
}

// MARK: - Upload, Directory Import, Translation & Recognition DTOs

public struct UploadResponseDTO: Codable, Sendable, Equatable {
    public var status: String
    public var batchId: String
    public var totalFiles: Int
    public var sessions: [MangaSessionSummary]
    public var sessionId: String
    public var filename: String
    public var totalPages: Int

    public init(
        status: String = "success",
        batchId: String = "",
        totalFiles: Int = 0,
        sessions: [MangaSessionSummary] = [],
        sessionId: String = "",
        filename: String = "",
        totalPages: Int = 0
    ) {
        self.status = status
        self.batchId = batchId
        self.totalFiles = totalFiles
        self.sessions = sessions
        self.sessionId = sessionId
        self.filename = filename
        self.totalPages = totalPages
    }

    private enum CodingKeys: String, CodingKey {
        case status
        case batchId = "batch_id"
        case totalFiles = "total_files"
        case sessions
        case sessionId = "session_id"
        case filename
        case totalPages = "total_pages"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "success"
        self.batchId = try c.decodeIfPresent(String.self, forKey: .batchId) ?? ""
        self.totalFiles = try c.decodeIfPresent(Int.self, forKey: .totalFiles) ?? 0
        self.sessions = try c.decodeIfPresent([MangaSessionSummary].self, forKey: .sessions) ?? []
        self.sessionId = try c.decodeIfPresent(String.self, forKey: .sessionId) ?? ""
        self.filename = try c.decodeIfPresent(String.self, forKey: .filename) ?? ""
        self.totalPages = try c.decodeIfPresent(Int.self, forKey: .totalPages) ?? 0
    }
}

public struct DirectoryImportResponseDTO: Codable, Sendable, Equatable {
    public var status: String
    public var importId: String
    public var batchId: String
    public var totalFiles: Int
    public var totalScannedFiles: Int
    public var importedFiles: Int
    public var processedFiles: Int
    public var failedFiles: Int
    public var createdSessions: [MangaSessionSummary]
    public var createdSessionIds: [String]
    public var message: String?

    public init(
        status: String = "started",
        importId: String = "",
        batchId: String = "",
        totalFiles: Int = 0,
        totalScannedFiles: Int = 0,
        importedFiles: Int = 0,
        processedFiles: Int = 0,
        failedFiles: Int = 0,
        createdSessions: [MangaSessionSummary] = [],
        createdSessionIds: [String] = [],
        message: String? = nil
    ) {
        self.status = status
        self.importId = importId
        self.batchId = batchId
        self.totalFiles = totalFiles
        self.totalScannedFiles = totalScannedFiles
        self.importedFiles = importedFiles
        self.processedFiles = processedFiles
        self.failedFiles = failedFiles
        self.createdSessions = createdSessions
        self.createdSessionIds = createdSessionIds
        self.message = message
    }

    private enum CodingKeys: String, CodingKey {
        case status
        case importId = "import_id"
        case batchId = "batch_id"
        case totalFiles = "total_files"
        case totalScannedFiles = "total_scanned_files"
        case importedFiles = "imported_files"
        case processedFiles = "processed_files"
        case failedFiles = "failed_files"
        case createdSessions = "created_sessions"
        case createdSessionIds = "created_session_ids"
        case message
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "started"
        self.importId = try c.decodeIfPresent(String.self, forKey: .importId) ?? ""
        self.batchId = try c.decodeIfPresent(String.self, forKey: .batchId) ?? ""
        self.totalFiles = try c.decodeIfPresent(Int.self, forKey: .totalFiles) ?? 0
        self.totalScannedFiles = try c.decodeIfPresent(Int.self, forKey: .totalScannedFiles) ?? self.totalFiles
        self.importedFiles = try c.decodeIfPresent(Int.self, forKey: .importedFiles) ?? 0
        self.processedFiles = try c.decodeIfPresent(Int.self, forKey: .processedFiles) ?? 0
        self.failedFiles = try c.decodeIfPresent(Int.self, forKey: .failedFiles) ?? 0
        self.createdSessions = try c.decodeIfPresent([MangaSessionSummary].self, forKey: .createdSessions) ?? []
        self.createdSessionIds = try c.decodeIfPresent([String].self, forKey: .createdSessionIds) ?? []
        self.message = try c.decodeIfPresent(String.self, forKey: .message)
    }
}

public struct DirectoryImportStatusDTO: Codable, Sendable, Equatable {
    public var importId: String
    public var batchId: String
    public var directory: String
    public var status: String
    public var totalFiles: Int
    public var importedFiles: Int
    public var failedFiles: Int
    public var currentFile: String?
    public var percent: Double
    public var createdSessionIds: [String]
    public var error: String?

    public init(
        importId: String = "",
        batchId: String = "",
        directory: String = "",
        status: String = "running",
        totalFiles: Int = 0,
        importedFiles: Int = 0,
        failedFiles: Int = 0,
        currentFile: String? = nil,
        percent: Double = 0,
        createdSessionIds: [String] = [],
        error: String? = nil
    ) {
        self.importId = importId
        self.batchId = batchId
        self.directory = directory
        self.status = status
        self.totalFiles = totalFiles
        self.importedFiles = importedFiles
        self.failedFiles = failedFiles
        self.currentFile = currentFile
        self.percent = percent
        self.createdSessionIds = createdSessionIds
        self.error = error
    }

    private enum CodingKeys: String, CodingKey {
        case importId = "import_id"
        case batchId = "batch_id"
        case directory
        case status
        case totalFiles = "total_files"
        case importedFiles = "imported_files"
        case failedFiles = "failed_files"
        case currentFile = "current_file"
        case percent
        case createdSessionIds = "created_session_ids"
        case error
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.importId = try c.decodeIfPresent(String.self, forKey: .importId) ?? ""
        self.batchId = try c.decodeIfPresent(String.self, forKey: .batchId) ?? ""
        self.directory = try c.decodeIfPresent(String.self, forKey: .directory) ?? ""
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "running"
        self.totalFiles = try c.decodeIfPresent(Int.self, forKey: .totalFiles) ?? 0
        self.importedFiles = try c.decodeIfPresent(Int.self, forKey: .importedFiles) ?? 0
        self.failedFiles = try c.decodeIfPresent(Int.self, forKey: .failedFiles) ?? 0
        self.currentFile = try c.decodeIfPresent(String.self, forKey: .currentFile)
        self.percent = try c.decodeIfPresent(Double.self, forKey: .percent) ?? 0
        self.createdSessionIds = try c.decodeIfPresent([String].self, forKey: .createdSessionIds) ?? []
        self.error = try c.decodeIfPresent(String.self, forKey: .error)
    }
}

public struct RecognizePageResponseDTO: Codable, Sendable, Equatable {
    public var status: String
    public var sessionId: String
    public var pageIndex: Int
    public var recognized: [RecognizedCharacterDTO]
    public var palette: CharacterPaletteDTO?
    public var message: String?

    public init(
        status: String = "ok",
        sessionId: String = "",
        pageIndex: Int = 0,
        recognized: [RecognizedCharacterDTO] = [],
        palette: CharacterPaletteDTO? = nil,
        message: String? = nil
    ) {
        self.status = status
        self.sessionId = sessionId
        self.pageIndex = pageIndex
        self.recognized = recognized
        self.palette = palette
        self.message = message
    }

    private enum CodingKeys: String, CodingKey {
        case status
        case sessionId = "session_id"
        case pageIndex = "page_index"
        case recognized
        case palette
        case message
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "ok"
        self.sessionId = try c.decodeIfPresent(String.self, forKey: .sessionId) ?? ""
        self.pageIndex = try c.decodeIfPresent(Int.self, forKey: .pageIndex) ?? 0
        self.recognized = try c.decodeIfPresent([RecognizedCharacterDTO].self, forKey: .recognized) ?? []
        self.palette = try c.decodeIfPresent(CharacterPaletteDTO.self, forKey: .palette)
        self.message = try c.decodeIfPresent(String.self, forKey: .message)
    }
}

public struct TranslatePageResponseDTO: Codable, Sendable, Equatable {
    public var status: String
    public var pageIndex: Int
    public var colorizedUrl: String?
    public var translations: [BubbleTranslationDTO]
    public var bubbleCount: Int
    public var translated: Bool

    public init(
        status: String = "success",
        pageIndex: Int = 0,
        colorizedUrl: String? = nil,
        translations: [BubbleTranslationDTO] = [],
        bubbleCount: Int = 0,
        translated: Bool = false
    ) {
        self.status = status
        self.pageIndex = pageIndex
        self.colorizedUrl = colorizedUrl
        self.translations = translations
        self.bubbleCount = bubbleCount
        self.translated = translated
    }

    private enum CodingKeys: String, CodingKey {
        case status
        case pageIndex = "page_index"
        case colorizedUrl = "colorized_url"
        case translations
        case bubbleCount = "bubble_count"
        case translated
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "success"
        self.pageIndex = try c.decodeIfPresent(Int.self, forKey: .pageIndex) ?? 0
        self.colorizedUrl = try c.decodeIfPresent(String.self, forKey: .colorizedUrl)
        self.translations = try c.decodeIfPresent([BubbleTranslationDTO].self, forKey: .translations) ?? []
        self.bubbleCount = try c.decodeIfPresent(Int.self, forKey: .bubbleCount) ?? self.translations.count
        self.translated = try c.decodeIfPresent(Bool.self, forKey: .translated) ?? !self.translations.isEmpty
    }
}

public struct TranslateSessionResponseDTO: Codable, Sendable, Equatable {
    public var status: String
    public var sessionId: String
    public var totalPages: Int
    public var targetPages: Int
    public var message: String

    public init(
        status: String = "started",
        sessionId: String = "",
        totalPages: Int = 0,
        targetPages: Int = 0,
        message: String = ""
    ) {
        self.status = status
        self.sessionId = sessionId
        self.totalPages = totalPages
        self.targetPages = targetPages
        self.message = message
    }

    private enum CodingKeys: String, CodingKey {
        case status
        case sessionId = "session_id"
        case totalPages = "total_pages"
        case targetPages = "target_pages"
        case message
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "started"
        self.sessionId = try c.decodeIfPresent(String.self, forKey: .sessionId) ?? ""
        self.totalPages = try c.decodeIfPresent(Int.self, forKey: .totalPages) ?? 0
        self.targetPages = try c.decodeIfPresent(Int.self, forKey: .targetPages) ?? 0
        self.message = try c.decodeIfPresent(String.self, forKey: .message) ?? ""
    }
}

public struct SeriesExemplarsResponseDTO: Codable, Sendable, Equatable {
    public var status: String
    public var sessionId: String
    public var seriesKey: String
    public var title: String
    public var exemplars: [SeriesExemplarDTO]

    public init(
        status: String = "ok",
        sessionId: String = "",
        seriesKey: String = "",
        title: String = "",
        exemplars: [SeriesExemplarDTO] = []
    ) {
        self.status = status
        self.sessionId = sessionId
        self.seriesKey = seriesKey
        self.title = title
        self.exemplars = exemplars
    }

    private enum CodingKeys: String, CodingKey {
        case status
        case sessionId = "session_id"
        case seriesKey = "series_key"
        case title
        case exemplars
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "ok"
        self.sessionId = try c.decodeIfPresent(String.self, forKey: .sessionId) ?? ""
        self.seriesKey = try c.decodeIfPresent(String.self, forKey: .seriesKey) ?? ""
        self.title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        self.exemplars = try c.decodeIfPresent([SeriesExemplarDTO].self, forKey: .exemplars) ?? []
    }
}

// MARK: - Export & Omnibus

public enum ExportFormat: String, Codable, Sendable, CaseIterable, Identifiable {
    case auto
    case pdf
    case epub
    case mobi
    case zip

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .auto: return "Original Format"
        case .pdf: return "PDF Document"
        case .epub: return "EPUB3 E-Book"
        case .mobi: return "Kindle MOBI"
        case .zip: return "Images ZIP"
        }
    }
}

public enum OmnibusChunkMode: String, Codable, Sendable, CaseIterable, Identifiable {
    case none
    case volumes
    case sizeMB = "size_mb"

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .none: return "Single Continuous File"
        case .volumes: return "Split by Volume Count"
        case .sizeMB: return "Auto-Split by MB Limit"
        }
    }
}

public enum EReaderDevicePreset: String, Codable, Sendable, CaseIterable, Identifiable {
    case colorsoft
    case kindlePaperwhite = "kindle_paperwhite"
    case ipadTablet = "ipad_tablet"
    case original

    public var id: String { rawValue }

    public var displayName: String {
        switch self {
        case .colorsoft: return "Kindle Colorsoft / Color E-Ink"
        case .kindlePaperwhite: return "Kindle Paperwhite / Oasis"
        case .ipadTablet: return "Tablet / iPad HD"
        case .original: return "Original Scan Resolution"
        }
    }

    public var maxDimension: Int {
        switch self {
        case .colorsoft, .kindlePaperwhite: return 1600
        case .ipadTablet: return 1920
        case .original: return 0
        }
    }

    public var jpegQuality: Int {
        switch self {
        case .colorsoft, .kindlePaperwhite: return 80
        case .ipadTablet: return 85
        case .original: return 90
        }
    }

    public var colorsoftTune: Bool {
        self == .colorsoft
    }
}

public struct CombinedOmnibusConfig: Codable, Sendable, Equatable {
    public var sessionIds: [String]?
    public var format: ExportFormat
    public var title: String?
    public var chunkBy: OmnibusChunkMode
    public var chunkSize: Int
    public var devicePreset: EReaderDevicePreset
    public var maxDimension: Int
    public var jpegQuality: Int
    public var grayscale: Bool
    public var colorsoftTune: Bool
    public var exportOriginal: Bool

    public init(
        sessionIds: [String]? = nil,
        format: ExportFormat = .epub,
        title: String? = nil,
        chunkBy: OmnibusChunkMode = .sizeMB,
        chunkSize: Int = 250,
        devicePreset: EReaderDevicePreset = .colorsoft,
        maxDimension: Int? = nil,
        jpegQuality: Int? = nil,
        grayscale: Bool = false,
        colorsoftTune: Bool? = nil,
        exportOriginal: Bool = false
    ) {
        self.sessionIds = sessionIds
        self.format = format
        self.title = title
        self.chunkBy = chunkBy
        self.chunkSize = chunkSize
        self.devicePreset = devicePreset
        self.maxDimension = maxDimension ?? devicePreset.maxDimension
        self.jpegQuality = jpegQuality ?? devicePreset.jpegQuality
        self.grayscale = grayscale
        self.colorsoftTune = colorsoftTune ?? (devicePreset.colorsoftTune && !exportOriginal)
        self.exportOriginal = exportOriginal
    }
}

public struct ExportResultDTO: Codable, Sendable, Equatable {
    public var status: String
    public var format: String
    public var downloadUrl: String
    public var filename: String
    public var totalDocuments: Int?
    public var totalVolumes: Int?
    public var title: String?
    public var isOmnibus: Bool?

    public init(
        status: String = "success",
        format: String = "pdf",
        downloadUrl: String = "",
        filename: String = "",
        totalDocuments: Int? = nil,
        totalVolumes: Int? = nil,
        title: String? = nil,
        isOmnibus: Bool? = nil
    ) {
        self.status = status
        self.format = format
        self.downloadUrl = downloadUrl
        self.filename = filename
        self.totalDocuments = totalDocuments
        self.totalVolumes = totalVolumes
        self.title = title
        self.isOmnibus = isOmnibus
    }

    private enum CodingKeys: String, CodingKey {
        case status
        case format
        case downloadUrl = "download_url"
        case filename
        case totalDocuments = "total_documents"
        case totalVolumes = "total_volumes"
        case title
        case isOmnibus = "is_omnibus"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "success"
        self.format = try c.decodeIfPresent(String.self, forKey: .format) ?? "pdf"
        self.downloadUrl = try c.decodeIfPresent(String.self, forKey: .downloadUrl) ?? ""
        self.filename = try c.decodeIfPresent(String.self, forKey: .filename) ?? ""
        self.totalDocuments = try c.decodeIfPresent(Int.self, forKey: .totalDocuments)
        self.totalVolumes = try c.decodeIfPresent(Int.self, forKey: .totalVolumes)
        self.title = try c.decodeIfPresent(String.self, forKey: .title)
        self.isOmnibus = try c.decodeIfPresent(Bool.self, forKey: .isOmnibus)
    }
}

public struct CombinedExportJobDTO: Codable, Sendable, Equatable {
    public var status: String
    public var jobId: String
    public var format: String
    public var totalVolumes: Int
    public var totalPages: Int
    public var title: String
    public var isOmnibus: Bool
    public var streamUrl: String?
    public var cancelUrl: String?
    public var downloadUrl: String?

    public init(
        status: String = "started",
        jobId: String = "",
        format: String = "epub",
        totalVolumes: Int = 0,
        totalPages: Int = 0,
        title: String = "",
        isOmnibus: Bool = false,
        streamUrl: String? = nil,
        cancelUrl: String? = nil,
        downloadUrl: String? = nil
    ) {
        self.status = status
        self.jobId = jobId
        self.format = format
        self.totalVolumes = totalVolumes
        self.totalPages = totalPages
        self.title = title
        self.isOmnibus = isOmnibus
        self.streamUrl = streamUrl
        self.cancelUrl = cancelUrl
        self.downloadUrl = downloadUrl
    }

    private enum CodingKeys: String, CodingKey {
        case status
        case jobId = "job_id"
        case format
        case totalVolumes = "total_volumes"
        case totalPages = "total_pages"
        case title
        case isOmnibus = "is_omnibus"
        case streamUrl = "stream_url"
        case cancelUrl = "cancel_url"
        case downloadUrl = "download_url"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "started"
        self.jobId = try c.decodeIfPresent(String.self, forKey: .jobId) ?? ""
        self.format = try c.decodeIfPresent(String.self, forKey: .format) ?? "epub"
        self.totalVolumes = try c.decodeIfPresent(Int.self, forKey: .totalVolumes) ?? 0
        self.totalPages = try c.decodeIfPresent(Int.self, forKey: .totalPages) ?? 0
        self.title = try c.decodeIfPresent(String.self, forKey: .title) ?? ""
        self.isOmnibus = try c.decodeIfPresent(Bool.self, forKey: .isOmnibus) ?? false
        self.streamUrl = try c.decodeIfPresent(String.self, forKey: .streamUrl)
        self.cancelUrl = try c.decodeIfPresent(String.self, forKey: .cancelUrl)
        self.downloadUrl = try c.decodeIfPresent(String.self, forKey: .downloadUrl)
    }
}

// MARK: - SSE Event Payloads

public struct PageUpdatePayload: Codable, Sendable, Equatable {
    public var pageIndex: Int
    public var status: String
    public var progress: String?
    public var skippedColored: Bool
    public var colorizedUrl: String?
    public var engine: String?
    public var exemplarUsed: String?
    public var exemplarsUsed: [String]
    public var adapterUsed: Bool
    public var qualityScore: PageQualityScore?
    public var autoHarvested: Bool
    public var recognizedCharacters: [RecognizedCharacterDTO]
    public var translations: [BubbleTranslationDTO]
    public var translated: Bool
    public var processedCount: Int?
    public var total: Int?
    public var message: String?
    public var error: String?

    public init(
        pageIndex: Int = 0,
        status: String = "processing",
        progress: String? = nil,
        skippedColored: Bool = false,
        colorizedUrl: String? = nil,
        engine: String? = nil,
        exemplarUsed: String? = nil,
        exemplarsUsed: [String] = [],
        adapterUsed: Bool = false,
        qualityScore: PageQualityScore? = nil,
        autoHarvested: Bool = false,
        recognizedCharacters: [RecognizedCharacterDTO] = [],
        translations: [BubbleTranslationDTO] = [],
        translated: Bool = false,
        processedCount: Int? = nil,
        total: Int? = nil,
        message: String? = nil,
        error: String? = nil
    ) {
        self.pageIndex = pageIndex
        self.status = status
        self.progress = progress
        self.skippedColored = skippedColored
        self.colorizedUrl = colorizedUrl
        self.engine = engine
        self.exemplarUsed = exemplarUsed
        self.exemplarsUsed = exemplarsUsed
        self.adapterUsed = adapterUsed
        self.qualityScore = qualityScore
        self.autoHarvested = autoHarvested
        self.recognizedCharacters = recognizedCharacters
        self.translations = translations
        self.translated = translated
        self.processedCount = processedCount
        self.total = total
        self.message = message
        self.error = error
    }

    private enum CodingKeys: String, CodingKey {
        case pageIndex = "page_index"
        case status
        case progress
        case skippedColored = "skipped_colored"
        case colorizedUrl = "colorized_url"
        case engine
        case exemplarUsed = "exemplar_used"
        case exemplarsUsed = "exemplars_used"
        case adapterUsed = "adapter_used"
        case qualityScore = "quality_score"
        case autoHarvested = "auto_harvested"
        case recognizedCharacters = "recognized_characters"
        case translations
        case translated
        case processedCount = "processed_count"
        case total
        case message
        case error
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.pageIndex = try c.decodeIfPresent(Int.self, forKey: .pageIndex) ?? 0
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "processing"
        self.progress = try c.decodeIfPresent(String.self, forKey: .progress)
        self.skippedColored = try c.decodeIfPresent(Bool.self, forKey: .skippedColored) ?? false
        self.colorizedUrl = try c.decodeIfPresent(String.self, forKey: .colorizedUrl)
        self.engine = try c.decodeIfPresent(String.self, forKey: .engine)
        self.exemplarUsed = try c.decodeIfPresent(String.self, forKey: .exemplarUsed)
        self.exemplarsUsed = try c.decodeIfPresent([String].self, forKey: .exemplarsUsed) ?? []
        self.adapterUsed = try c.decodeIfPresent(Bool.self, forKey: .adapterUsed) ?? false
        self.qualityScore = try c.decodeIfPresent(PageQualityScore.self, forKey: .qualityScore)
        self.autoHarvested = try c.decodeIfPresent(Bool.self, forKey: .autoHarvested) ?? false
        self.recognizedCharacters = try c.decodeIfPresent([RecognizedCharacterDTO].self, forKey: .recognizedCharacters) ?? []
        self.translations = try c.decodeIfPresent([BubbleTranslationDTO].self, forKey: .translations) ?? []
        self.translated = try c.decodeIfPresent(Bool.self, forKey: .translated) ?? false
        self.processedCount = try c.decodeIfPresent(Int.self, forKey: .processedCount)
        self.total = try c.decodeIfPresent(Int.self, forKey: .total)
        self.message = try c.decodeIfPresent(String.self, forKey: .message)
        self.error = try c.decodeIfPresent(String.self, forKey: .error)
    }
}

public struct AdapterTrainingProgressPayload: Codable, Sendable, Equatable {
    public var seriesKey: String
    public var step: Int
    public var totalSteps: Int
    public var progress: Double
    public var loss: Double
    public var status: String
    public var autoRefine: Bool

    public init(
        seriesKey: String = "",
        step: Int = 0,
        totalSteps: Int = 100,
        progress: Double = 0,
        loss: Double = 0,
        status: String = "training",
        autoRefine: Bool = false
    ) {
        self.seriesKey = seriesKey
        self.step = step
        self.totalSteps = totalSteps
        self.progress = progress
        self.loss = loss
        self.status = status
        self.autoRefine = autoRefine
    }

    private enum CodingKeys: String, CodingKey {
        case seriesKey = "series_key"
        case step
        case totalSteps = "total_steps"
        case progress
        case loss
        case status
        case autoRefine = "auto_refine"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.seriesKey = try c.decodeIfPresent(String.self, forKey: .seriesKey) ?? ""
        self.step = try c.decodeIfPresent(Int.self, forKey: .step) ?? 0
        self.totalSteps = try c.decodeIfPresent(Int.self, forKey: .totalSteps) ?? 100
        self.progress = try c.decodeIfPresent(Double.self, forKey: .progress) ?? 0
        self.loss = try c.decodeIfPresent(Double.self, forKey: .loss) ?? 0
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? "training"
        self.autoRefine = try c.decodeIfPresent(Bool.self, forKey: .autoRefine) ?? false
    }
}

public enum SSEColorizeEvent: Equatable, Sendable {
    case initial(session: MangaSessionDetail?, isActive: Bool, uncolorizedCount: Int)
    case start(total: Int, modelProvider: String?, modelName: String?)
    case pageUpdate(PageUpdatePayload)
    case adapterTrainingProgress(AdapterTrainingProgressPayload)
    case completed(totalProcessed: Int, message: String?)
    case idle(totalProcessed: Int, total: Int?)
    case cancelled(processedCount: Int, total: Int?)
    case error(message: String)
}

public struct CombinedProgressPayload: Codable, Sendable, Equatable {
    public var jobId: String
    public var percent: Int
    public var processedPages: Int
    public var totalPages: Int
    public var status: String
    public var volNum: Int?
    public var totalVols: Int?
    public var volTitle: String?
    public var partNum: Int?
    public var totalParts: Int?

    public init(
        jobId: String = "",
        percent: Int = 0,
        processedPages: Int = 0,
        totalPages: Int = 0,
        status: String = "",
        volNum: Int? = nil,
        totalVols: Int? = nil,
        volTitle: String? = nil,
        partNum: Int? = nil,
        totalParts: Int? = nil
    ) {
        self.jobId = jobId
        self.percent = percent
        self.processedPages = processedPages
        self.totalPages = totalPages
        self.status = status
        self.volNum = volNum
        self.totalVols = totalVols
        self.volTitle = volTitle
        self.partNum = partNum
        self.totalParts = totalParts
    }

    private enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case percent
        case processedPages = "processed_pages"
        case totalPages = "total_pages"
        case status
        case volNum = "vol_num"
        case totalVols = "total_vols"
        case volTitle = "vol_title"
        case partNum = "part_num"
        case totalParts = "total_parts"
    }

    public init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        self.jobId = try c.decodeIfPresent(String.self, forKey: .jobId) ?? ""
        self.percent = try c.decodeIfPresent(Int.self, forKey: .percent) ?? 0
        self.processedPages = try c.decodeIfPresent(Int.self, forKey: .processedPages) ?? 0
        self.totalPages = try c.decodeIfPresent(Int.self, forKey: .totalPages) ?? 0
        self.status = try c.decodeIfPresent(String.self, forKey: .status) ?? ""
        self.volNum = try c.decodeIfPresent(Int.self, forKey: .volNum)
        self.totalVols = try c.decodeIfPresent(Int.self, forKey: .totalVols)
        self.volTitle = try c.decodeIfPresent(String.self, forKey: .volTitle)
        self.partNum = try c.decodeIfPresent(Int.self, forKey: .partNum)
        self.totalParts = try c.decodeIfPresent(Int.self, forKey: .totalParts)
    }
}

public enum SSECombinedExportEvent: Equatable, Sendable {
    case initial(jobId: String, status: String, progress: CombinedProgressPayload)
    case progress(CombinedProgressPayload)
    case completed(jobId: String, downloadUrl: String, filename: String, totalVolumes: Int?, title: String?)
    case cancelled(jobId: String, message: String?)
    case error(jobId: String, message: String)
}
