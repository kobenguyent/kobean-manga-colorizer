import Foundation

public enum SSEParser {
    private struct TypeProbe: Decodable {
        let type: String?
    }

    private struct InitPayload: Decodable {
        let session: MangaSessionDetail?
        let isActive: Bool?
        let uncolorizedCount: Int?

        private enum CodingKeys: String, CodingKey {
            case session
            case isActive = "is_active"
            case uncolorizedCount = "uncolorized_count"
        }
    }

    private struct StartPayload: Decodable {
        let total: Int?
        let modelProvider: String?
        let modelName: String?

        private enum CodingKeys: String, CodingKey {
            case total
            case modelProvider = "model_provider"
            case modelName = "model_name"
        }
    }

    private struct TerminalPayload: Decodable {
        let totalProcessed: Int?
        let processedCount: Int?
        let total: Int?
        let message: String?
        let error: String?

        private enum CodingKeys: String, CodingKey {
            case totalProcessed = "total_processed"
            case processedCount = "processed_count"
            case total
            case message
            case error
        }
    }

    private struct CombinedInitPayload: Decodable {
        let jobId: String?
        let status: String?
        let progress: CombinedProgressPayload?

        private enum CodingKeys: String, CodingKey {
            case jobId = "job_id"
            case status
            case progress
        }
    }

    private struct CombinedTerminalPayload: Decodable {
        let jobId: String?
        let downloadUrl: String?
        let filename: String?
        let totalVolumes: Int?
        let title: String?
        let message: String?
        let error: String?

        private enum CodingKeys: String, CodingKey {
            case jobId = "job_id"
            case downloadUrl = "download_url"
            case filename
            case totalVolumes = "total_volumes"
            case title
            case message
            case error
        }
    }

    public static func extractJSONPayload(from line: String) -> Data? {
        let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.hasPrefix("data:") else { return nil }
        let jsonPart = trimmed.dropFirst(5).trimmingCharacters(in: .whitespaces)
        guard !jsonPart.isEmpty else { return nil }
        return jsonPart.data(using: .utf8)
    }

    public static func parseColorizeLine(_ line: String) -> SSEColorizeEvent? {
        guard let data = extractJSONPayload(from: line) else { return nil }
        return try? decodeColorizeEvent(from: data)
    }

    public static func decodeColorizeEvent(from data: Data) throws -> SSEColorizeEvent? {
        let decoder = JSONDecoder()
        let probe = try decoder.decode(TypeProbe.self, from: data)
        guard let eventType = probe.type else { return nil }

        switch eventType {
        case "init":
            let payload = try decoder.decode(InitPayload.self, from: data)
            return .initial(
                session: payload.session,
                isActive: payload.isActive ?? false,
                uncolorizedCount: payload.uncolorizedCount ?? 0
            )
        case "start":
            let payload = try decoder.decode(StartPayload.self, from: data)
            return .start(
                total: payload.total ?? 0,
                modelProvider: payload.modelProvider,
                modelName: payload.modelName
            )
        case "page_update":
            let payload = try decoder.decode(PageUpdatePayload.self, from: data)
            return .pageUpdate(payload)
        case "adapter_training_progress":
            let payload = try decoder.decode(AdapterTrainingProgressPayload.self, from: data)
            return .adapterTrainingProgress(payload)
        case "completed":
            let payload = try decoder.decode(TerminalPayload.self, from: data)
            return .completed(
                totalProcessed: payload.totalProcessed ?? payload.processedCount ?? 0,
                message: payload.message
            )
        case "idle":
            let payload = try decoder.decode(TerminalPayload.self, from: data)
            return .idle(
                totalProcessed: payload.totalProcessed ?? payload.processedCount ?? 0,
                total: payload.total
            )
        case "cancelled":
            let payload = try decoder.decode(TerminalPayload.self, from: data)
            return .cancelled(
                processedCount: payload.processedCount ?? payload.totalProcessed ?? 0,
                total: payload.total
            )
        case "error":
            let payload = try decoder.decode(TerminalPayload.self, from: data)
            let msg = payload.error ?? payload.message ?? "Unknown colorization error"
            return .error(message: msg)
        default:
            return nil
        }
    }

    public static func parseCombinedExportLine(_ line: String) -> SSECombinedExportEvent? {
        guard let data = extractJSONPayload(from: line) else { return nil }
        return try? decodeCombinedExportEvent(from: data)
    }

    public static func decodeCombinedExportEvent(from data: Data) throws -> SSECombinedExportEvent? {
        let decoder = JSONDecoder()
        let probe = try decoder.decode(TypeProbe.self, from: data)
        guard let eventType = probe.type else { return nil }

        switch eventType {
        case "init":
            let payload = try decoder.decode(CombinedInitPayload.self, from: data)
            let jobId = payload.jobId ?? ""
            return .initial(
                jobId: jobId,
                status: payload.status ?? "processing",
                progress: payload.progress ?? CombinedProgressPayload(jobId: jobId)
            )
        case "progress":
            let payload = try decoder.decode(CombinedProgressPayload.self, from: data)
            return .progress(payload)
        case "completed":
            let payload = try decoder.decode(CombinedTerminalPayload.self, from: data)
            return .completed(
                jobId: payload.jobId ?? "",
                downloadUrl: payload.downloadUrl ?? "",
                filename: payload.filename ?? "",
                totalVolumes: payload.totalVolumes,
                title: payload.title
            )
        case "cancelled":
            let payload = try decoder.decode(CombinedTerminalPayload.self, from: data)
            return .cancelled(
                jobId: payload.jobId ?? "",
                message: payload.message
            )
        case "error":
            let payload = try decoder.decode(CombinedTerminalPayload.self, from: data)
            let msg = payload.error ?? payload.message ?? "Combined export failed"
            return .error(jobId: payload.jobId ?? "", message: msg)
        default:
            return nil
        }
    }
}
