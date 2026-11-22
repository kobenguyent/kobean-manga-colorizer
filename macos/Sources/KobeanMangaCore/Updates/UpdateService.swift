import CryptoKit
import Foundation

public struct UpdateHTTPResponse: Sendable {
    public let data: Data
    public let statusCode: Int
    public let headers: [String: String]

    public init(data: Data, statusCode: Int, headers: [String: String] = [:]) {
        self.data = data
        self.statusCode = statusCode
        self.headers = headers
    }
}

public protocol UpdateHTTPFetching: Sendable {
    func fetch(_ request: URLRequest) async throws -> UpdateHTTPResponse
    func download(from url: URL, to destination: URL, progress: (@Sendable (Double) -> Void)?) async throws -> URL
}

public enum UpdateError: LocalizedError, Equatable, Sendable {
    case invalidRepository(String)
    case httpStatus(Int, String)
    case invalidResponse
    case noReleasePublished
    case missingMacAsset
    case checksumMismatch(expected: String, actual: String)
    case networkFailure(String)

    public var errorDescription: String? {
        switch self {
        case .invalidRepository(let repo):
            return "Invalid GitHub repository '\(repo)'. Expected format 'owner/repo'."
        case .httpStatus(let code, let detail):
            return "GitHub API returned HTTP \(code): \(detail)"
        case .invalidResponse:
            return "Received an unexpected response from GitHub."
        case .noReleasePublished:
            return "No GitHub releases have been published yet for this repository."
        case .missingMacAsset:
            return "The latest release does not contain a macOS .zip or .dmg artifact."
        case .checksumMismatch(let expected, let actual):
            return "SHA-256 verification failed.\nExpected: \(expected)\nActual: \(actual)"
        case .networkFailure(let reason):
            return "Network error while contacting GitHub: \(reason)"
        }
    }
}

public enum UpdateCheckOutcome: Equatable, Sendable {
    case updateAvailable(release: GitHubRelease, latestVersion: SemanticVersion, asset: GitHubReleaseAsset?)
    case upToDate(currentVersion: SemanticVersion, latestRelease: GitHubRelease?)
}

public struct DownloadedUpdateArtifact: Equatable, Sendable {
    public let fileURL: URL
    public let sha256: String
    public let verifiedAgainstChecksums: Bool

    public init(fileURL: URL, sha256: String, verifiedAgainstChecksums: Bool) {
        self.fileURL = fileURL
        self.sha256 = sha256
        self.verifiedAgainstChecksums = verifiedAgainstChecksums
    }
}

private final class StreamingDownloadDelegate: NSObject, URLSessionDownloadDelegate, @unchecked Sendable {
    private let destination: URL
    private let progress: (@Sendable (Double) -> Void)?
    private let lock = NSLock()
    private var continuation: CheckedContinuation<URL, Error>?
    private var movedURL: URL?
    private var moveError: Error?

    init(
        destination: URL,
        progress: (@Sendable (Double) -> Void)?,
        continuation: CheckedContinuation<URL, Error>
    ) {
        self.destination = destination
        self.progress = progress
        self.continuation = continuation
    }

    private func finish(with result: Result<URL, Error>) {
        lock.lock()
        let cont = continuation
        continuation = nil
        lock.unlock()
        cont?.resume(with: result)
    }

    func urlSession(
        _ session: URLSession,
        downloadTask: URLSessionDownloadTask,
        didWriteData bytesWritten: Int64,
        totalBytesWritten: Int64,
        totalBytesExpectedToWrite: Int64
    ) {
        guard totalBytesExpectedToWrite > 0 else { return }
        let ratio = min(1.0, max(0.0, Double(totalBytesWritten) / Double(totalBytesExpectedToWrite)))
        progress?(ratio)
    }

    func urlSession(
        _ session: URLSession,
        downloadTask: URLSessionDownloadTask,
        didFinishDownloadingTo location: URL
    ) {
        if let http = downloadTask.response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            moveError = UpdateError.httpStatus(http.statusCode, "Download failed")
            return
        }
        do {
            let fm = FileManager.default
            try fm.createDirectory(at: destination.deletingLastPathComponent(), withIntermediateDirectories: true)
            if fm.fileExists(atPath: destination.path) {
                try fm.removeItem(at: destination)
            }
            try fm.moveItem(at: location, to: destination)
            movedURL = destination
        } catch {
            moveError = error
        }
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        defer { session.finishTasksAndInvalidate() }
        if let error {
            finish(with: .failure(error))
            return
        }
        if let moveError {
            finish(with: .failure(moveError))
            return
        }
        if let movedURL {
            progress?(1.0)
            finish(with: .success(movedURL))
            return
        }
        finish(with: .failure(UpdateError.invalidResponse))
    }
}

public final class URLSessionUpdateHTTPClient: UpdateHTTPFetching, @unchecked Sendable {
    private let session: URLSession

    public init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 20
        config.timeoutIntervalForResource = 300
        self.session = URLSession(configuration: config)
    }

    public func fetch(_ request: URLRequest) async throws -> UpdateHTTPResponse {
        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw UpdateError.invalidResponse
            }
            var headers: [String: String] = [:]
            for (k, v) in http.allHeaderFields {
                headers[String(describing: k).lowercased()] = String(describing: v)
            }
            return UpdateHTTPResponse(data: data, statusCode: http.statusCode, headers: headers)
        } catch let err as UpdateError {
            throw err
        } catch {
            throw UpdateError.networkFailure(error.localizedDescription)
        }
    }

    public func download(
        from url: URL,
        to destination: URL,
        progress: (@Sendable (Double) -> Void)?
    ) async throws -> URL {
        try await withCheckedThrowingContinuation { continuation in
            let delegate = StreamingDownloadDelegate(
                destination: destination,
                progress: progress,
                continuation: continuation
            )
            let config = URLSessionConfiguration.default
            config.timeoutIntervalForRequest = 30
            config.timeoutIntervalForResource = 600
            let downloadSession = URLSession(configuration: config, delegate: delegate, delegateQueue: nil)
            var request = URLRequest(url: url)
            request.setValue(AppMetadata.userAgent, forHTTPHeaderField: "User-Agent")
            let task = downloadSession.downloadTask(with: request)
            task.resume()
        }
    }
}

public final class UpdateService: Sendable {
    private let httpClient: UpdateHTTPFetching

    public init(httpClient: UpdateHTTPFetching = URLSessionUpdateHTTPClient()) {
        self.httpClient = httpClient
    }

    public func checkForUpdates(
        repository: String = AppMetadata.configuredGitHubRepo,
        currentVersion: SemanticVersion = AppMetadata.currentSemanticVersion,
        includePrereleases: Bool = false,
        architecture: String = GitHubRelease.currentArchitecture
    ) async throws -> UpdateCheckOutcome {
        let cleanRepo = repository.trimmingCharacters(in: .whitespacesAndNewlines)
        let parts = cleanRepo.split(separator: "/")
        guard parts.count == 2, !parts[0].isEmpty, !parts[1].isEmpty else {
            throw UpdateError.invalidRepository(repository)
        }

        let endpoint = includePrereleases
            ? "https://api.github.com/repos/\(cleanRepo)/releases?per_page=15"
            : "https://api.github.com/repos/\(cleanRepo)/releases/latest"

        guard let url = URL(string: endpoint) else {
            throw UpdateError.invalidRepository(repository)
        }

        var request = URLRequest(url: url)
        request.setValue("application/vnd.github+json", forHTTPHeaderField: "Accept")
        request.setValue("2022-11-28", forHTTPHeaderField: "X-GitHub-Api-Version")
        request.setValue(AppMetadata.userAgent, forHTTPHeaderField: "User-Agent")

        let response = try await httpClient.fetch(request)

        if response.statusCode == 404 {
            throw UpdateError.noReleasePublished
        }
        guard (200...299).contains(response.statusCode) else {
            let bodySnippet = String(data: response.data, encoding: .utf8)?.prefix(200) ?? "Unknown error"
            throw UpdateError.httpStatus(response.statusCode, String(bodySnippet))
        }

        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601

        let candidateRelease: GitHubRelease
        if includePrereleases {
            let releases = try decoder.decode([GitHubRelease].self, from: response.data)
            let eligible = releases
                .filter { !$0.isDraft && $0.semanticVersion != nil }
                .sorted {
                    ($0.semanticVersion ?? SemanticVersion(major: 0, minor: 0, patch: 0))
                        > ($1.semanticVersion ?? SemanticVersion(major: 0, minor: 0, patch: 0))
                }
            guard let best = eligible.first else {
                throw UpdateError.noReleasePublished
            }
            candidateRelease = best
        } else {
            candidateRelease = try decoder.decode(GitHubRelease.self, from: response.data)
        }

        guard let latestVersion = candidateRelease.semanticVersion else {
            return .upToDate(currentVersion: currentVersion, latestRelease: candidateRelease)
        }

        if latestVersion > currentVersion {
            return .updateAvailable(
                release: candidateRelease,
                latestVersion: latestVersion,
                asset: candidateRelease.preferredMacAsset(architecture: architecture)
            )
        }
        return .upToDate(currentVersion: currentVersion, latestRelease: candidateRelease)
    }

    public func downloadAndVerify(
        release: GitHubRelease,
        asset: GitHubReleaseAsset,
        destinationDirectory: URL? = nil,
        progress: (@Sendable (Double) -> Void)? = nil
    ) async throws -> DownloadedUpdateArtifact {
        let dir = destinationDirectory ?? FileManager.default.temporaryDirectory
            .appendingPathComponent("KobeanMangaUpdates", isDirectory: true)
            .appendingPathComponent(release.tagName, isDirectory: true)
        let targetFile = dir.appendingPathComponent(asset.name)

        let downloadedURL = try await httpClient.download(
            from: asset.browserDownloadURL,
            to: targetFile,
            progress: progress
        )

        let actualSHA = try Self.sha256Hex(of: downloadedURL)

        var verified = false
        if let checksumAsset = release.checksumAsset {
            var req = URLRequest(url: checksumAsset.browserDownloadURL)
            req.setValue(AppMetadata.userAgent, forHTTPHeaderField: "User-Agent")
            if let resp = try? await httpClient.fetch(req),
               (200...299).contains(resp.statusCode),
               let text = String(data: resp.data, encoding: .utf8),
               let expected = Self.parseSHA256Checksum(forAssetNamed: asset.name, in: text) {
                if expected.lowercased() != actualSHA.lowercased() {
                    try? FileManager.default.removeItem(at: downloadedURL)
                    throw UpdateError.checksumMismatch(expected: expected, actual: actualSHA)
                }
                verified = true
            }
        }

        return DownloadedUpdateArtifact(
            fileURL: downloadedURL,
            sha256: actualSHA,
            verifiedAgainstChecksums: verified
        )
    }

    public static func sha256Hex(of fileURL: URL) throws -> String {
        let handle = try FileHandle(forReadingFrom: fileURL)
        defer { try? handle.close() }
        var hasher = SHA256()
        while true {
            let chunk = handle.readData(ofLength: 65_536)
            if chunk.isEmpty { break }
            hasher.update(data: chunk)
        }
        return hasher.finalize().map { String(format: "%02x", $0) }.joined()
    }

    public static func parseSHA256Checksum(forAssetNamed assetName: String, in checksumFile: String) -> String? {
        for rawLine in checksumFile.components(separatedBy: .newlines) {
            let line = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !line.isEmpty else { continue }
            let tokens = line.split(whereSeparator: { $0 == " " || $0 == "\t" }).map(String.init)
            guard tokens.count >= 2 else { continue }
            let hash = tokens[0]
            var filePart = tokens[1]
            if filePart.hasPrefix("*") { filePart.removeFirst() }
            if filePart == assetName || URL(fileURLWithPath: filePart).lastPathComponent == assetName {
                return hash
            }
        }
        return nil
    }
}
