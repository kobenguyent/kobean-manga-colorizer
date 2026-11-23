import CryptoKit
import Darwin
import Foundation

public enum BackendState: Sendable, Equatable {
    case stopped
    case starting(port: Int)
    case running(port: Int, attachedToExisting: Bool)
    case failed(String)

    public var isRunning: Bool {
        if case .running = self { return true }
        return false
    }

    public var activePort: Int? {
        switch self {
        case .starting(let port), .running(let port, _):
            return port
        default:
            return nil
        }
    }
}

public enum BackendSupervisorError: LocalizedError, Sendable, Equatable {
    case workspaceNotFound
    case pythonRunnerNotFound(workspace: String)
    case portAllocationFailed
    case bootstrapFailed(code: Int32, logs: String)
    case startupTimeout(port: Int, logs: String)
    case processExitedPrematurely(code: Int32, logs: String)

    public var errorDescription: String? {
        switch self {
        case .workspaceNotFound:
            return "Could not locate Kobean Manga Colorizer backend (main.py)."
        case .pythonRunnerNotFound(let workspace):
            return "Could not find a ready Python environment (.venv with dependencies or uv) for \(workspace). Install uv (brew install uv) or configure Workspace Root in Settings."
        case .portAllocationFailed:
            return "Unable to allocate a free local TCP port on 127.0.0.1."
        case .bootstrapFailed(let code, let logs):
            let summary = BackendSupervisor.summarizeFailureLogs(logs)
            let suffix = summary.isEmpty ? "" : "\n\(summary)"
            return "Failed to set up Python environment (uv sync exited with code \(code)).\(suffix)"
        case .startupTimeout(let port, let logs):
            let summary = BackendSupervisor.summarizeFailureLogs(logs)
            let suffix = summary.isEmpty ? "" : "\n\(summary)"
            return "Backend engine on 127.0.0.1:\(port) did not become healthy in time.\(suffix)"
        case .processExitedPrematurely(let code, let logs):
            let summary = BackendSupervisor.summarizeFailureLogs(logs)
            let suffix = summary.isEmpty ? "" : "\n\(summary)"
            return "Backend engine exited unexpectedly with code \(code).\(suffix)"
        }
    }
}

/// Thread-safe tracker so NSApplication.willTerminateNotification can synchronously
/// terminate an owned child Python process without waiting on actor hops (T-04).
private final class OwnedProcessTracker: @unchecked Sendable {
    private let lock = NSLock()
    private var process: Process?
    private var attachedToExisting: Bool = false

    func setOwned(_ proc: Process?) {
        lock.lock()
        process = proc
        attachedToExisting = (proc == nil)
        lock.unlock()
    }

    func markAttached() {
        lock.lock()
        process = nil
        attachedToExisting = true
        lock.unlock()
    }

    func clear() {
        lock.lock()
        process = nil
        attachedToExisting = false
        lock.unlock()
    }

    func terminateSynchronously(graceSeconds: TimeInterval = 2.0) {
        lock.lock()
        let proc = process
        let attached = attachedToExisting
        process = nil
        attachedToExisting = false
        lock.unlock()

        guard !attached, let proc, proc.isRunning else { return }
        let pid = proc.processIdentifier
        proc.terminate() // SIGTERM

        let deadline = Date().addingTimeInterval(graceSeconds)
        while proc.isRunning && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.05)
        }
        if proc.isRunning && pid > 0 {
            Darwin.kill(pid, SIGKILL)
        }
    }
}

private final class LogRingBuffer: @unchecked Sendable {
    private let lock = NSLock()
    private let maxLines: Int
    private var lines: [String] = []

    init(maxLines: Int = 200) {
        self.maxLines = maxLines
    }

    func append(chunk: String) {
        let newLines = chunk
            .split(whereSeparator: \.isNewline)
            .map { String($0) }
            .filter { !$0.isEmpty }
        guard !newLines.isEmpty else { return }

        lock.lock()
        lines.append(contentsOf: newLines)
        if lines.count > maxLines {
            lines.removeFirst(lines.count - maxLines)
        }
        lock.unlock()
    }

    func snapshot() -> [String] {
        lock.lock()
        defer { lock.unlock() }
        return lines
    }

    func clear() {
        lock.lock()
        lines.removeAll()
        lock.unlock()
    }
}

/// Supervises the local FastAPI + PyTorch MPS Python backend on loopback 127.0.0.1.
/// Mitigates T-02 (loopback only), T-03 (direct executableURL + args, zero shell), and
/// T-04 (cleanly kills only child processes spawned by this app).
public actor BackendSupervisor {
    public typealias HealthChecker = @Sendable (Int) async -> HealthStatus?

    public private(set) var state: BackendState = .stopped
    public private(set) var port: Int = 8000
    public private(set) var attachedToExisting: Bool = false

    private let processTracker = OwnedProcessTracker()
    private let logBuffer = LogRingBuffer(maxLines: 200)
    private let healthChecker: HealthChecker
    private var managedProcess: Process?
    private var stateChangeHandler: (@Sendable (BackendState) -> Void)?

    public init(healthChecker: HealthChecker? = nil) {
        if let healthChecker {
            self.healthChecker = healthChecker
        } else {
            self.healthChecker = { candidatePort in
                await Self.defaultProbeHealth(port: candidatePort)
            }
        }
    }

    deinit {
        processTracker.terminateSynchronously()
    }

    public var baseURL: URL? {
        guard case .running(let activePort, _) = state else { return nil }
        return URL(string: "http://127.0.0.1:\(activePort)")
    }

    public func recentLogs() -> [String] {
        logBuffer.snapshot()
    }

    public func setStateChangeHandler(_ handler: (@Sendable (BackendState) -> Void)?) {
        stateChangeHandler = handler
    }

    @discardableResult
    public func start(
        preferredPort: Int = 8000,
        workspaceHint: URL? = nil,
        dataDirectory: URL? = nil,
        startupTimeout: TimeInterval = 35.0,
        bootstrapTimeout: TimeInterval = 600.0,
        statusUpdate: (@Sendable (String) -> Void)? = nil
    ) async throws -> URL {
        if case .running(let currentPort, _) = state,
           let url = URL(string: "http://127.0.0.1:\(currentPort)") {
            if await healthChecker(currentPort)?.isHealthy == true {
                return url
            }
        }

        // 1. Attach cleanly if Kobean backend is already live on preferredPort (T-04).
        if let health = await healthChecker(preferredPort), health.isHealthy {
            self.port = preferredPort
            self.attachedToExisting = true
            self.managedProcess = nil
            self.processTracker.markAttached()
            self.state = .running(port: preferredPort, attachedToExisting: true)
            return URL(string: "http://127.0.0.1:\(preferredPort)")!
        }

        // 2. Locate workspace (main.py), effective writable data directory, and Python runner.
        guard let workspaceURL = Self.locateWorkspaceRoot(hint: workspaceHint) else {
            let err = BackendSupervisorError.workspaceNotFound
            self.state = .failed(err.localizedDescription)
            throw err
        }

        let effectiveDataDirectory = dataDirectory ?? Self.defaultDataDirectoryIfBundled(workspaceURL: workspaceURL)
        if let effectiveDataDirectory {
            try? FileManager.default.createDirectory(at: effectiveDataDirectory, withIntermediateDirectories: true)
        }

        let mainPyURL = workspaceURL.appendingPathComponent("main.py")
        self.logBuffer.clear()

        // 2b. Ensure bundled / uv-managed virtual environment has its Python dependencies synced
        //     before launching main.py. This avoids:
        //     - Getting trapped in an empty/half-installed .venv (missing fastapi/uvicorn)
        //     - `uv run` trying to build an editable wheel via hatchling inside a read-only .app bundle
        //     - Killing first-launch PyTorch downloads after the 35s server health timeout.
        let targetVenvURL = Self.targetVenvDirectory(workspaceURL: workspaceURL, dataDirectory: effectiveDataDirectory)
        let targetVenvPython = targetVenvURL.appendingPathComponent("bin/python3")
        let needsBootstrap = Self.shouldBootstrapVenv(
            workspaceURL: workspaceURL,
            venvURL: targetVenvURL,
            venvPythonURL: targetVenvPython,
            isBundled: Self.isInsideAppBundle(workspaceURL)
        )
        if needsBootstrap, let uvURL = Self.locateUVExecutable() {
            statusUpdate?("Setting up Python environment (first launch may take a few minutes)…")
            try await bootstrapEnvironmentWithUV(
                uvURL: uvURL,
                workspaceURL: workspaceURL,
                venvURL: targetVenvURL,
                dataDirectory: effectiveDataDirectory,
                timeout: bootstrapTimeout
            )
            statusUpdate?("Starting local colorization engine…")
        }

        guard let runner = Self.locatePythonRunner(
            in: workspaceURL,
            mainPyPath: mainPyURL.path,
            dataDirectory: effectiveDataDirectory
        ) else {
            let err = BackendSupervisorError.pythonRunnerNotFound(workspace: workspaceURL.path)
            self.state = .failed(err.localizedDescription)
            throw err
        }

        // 3. Pick preferredPort if free on 127.0.0.1, else allocate an ephemeral free port.
        let chosenPort: Int
        if Self.isLocalPortAvailable(preferredPort) {
            chosenPort = preferredPort
        } else if let ephemeral = Self.findAvailableLocalPort() {
            chosenPort = ephemeral
        } else {
            let err = BackendSupervisorError.portAllocationFailed
            self.state = .failed(err.localizedDescription)
            throw err
        }

        self.port = chosenPort
        self.attachedToExisting = false
        self.state = .starting(port: chosenPort)

        // 4. Spawn Foundation.Process directly (no shell interpolation - T-03; loopback only - T-02).
        let isBundled = Self.isInsideAppBundle(workspaceURL)
        let proc = Process()
        proc.currentDirectoryURL = workspaceURL
        proc.executableURL = runner.executableURL
        proc.arguments = runner.arguments(port: chosenPort)

        proc.environment = Self.enrichedEnvironment(
            dataDirectory: effectiveDataDirectory,
            venvDirectory: isBundled ? targetVenvURL : nil,
            disableBytecodeCache: isBundled
        )

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        proc.standardOutput = stdoutPipe
        proc.standardError = stderrPipe

        let ring = self.logBuffer
        stdoutPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if !data.isEmpty, let text = String(data: data, encoding: .utf8) {
                ring.append(chunk: text)
            }
        }
        stderrPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if !data.isEmpty, let text = String(data: data, encoding: .utf8) {
                ring.append(chunk: text)
            }
        }

        proc.terminationHandler = { [weak self] finished in
            stdoutPipe.fileHandleForReading.readabilityHandler = nil
            stderrPipe.fileHandleForReading.readabilityHandler = nil
            Task {
                await self?.handleChildTermination(status: finished.terminationStatus)
            }
        }

        do {
            try proc.run()
        } catch {
            self.state = .failed(error.localizedDescription)
            throw error
        }

        self.managedProcess = proc
        self.processTracker.setOwned(proc)

        // 5. Poll /api/health until ready.
        // Allow extra time on first bundled launch when neural weights (generator.zip)
        // are downloaded from HuggingFace before Uvicorn binds the loopback port.
        let weightsAlreadyPresent: Bool = {
            let fm = FileManager.default
            if fm.fileExists(atPath: workspaceURL.appendingPathComponent("networks/generator.zip").path) {
                return true
            }
            if let dataDir = effectiveDataDirectory,
               fm.fileExists(atPath: dataDir.appendingPathComponent("networks/generator.zip").path) {
                return true
            }
            return false
        }()
        let effectiveStartupTimeout = (isBundled && !weightsAlreadyPresent)
            ? max(startupTimeout, 180.0)
            : startupTimeout
        if isBundled && !weightsAlreadyPresent {
            statusUpdate?("Downloading neural colorization weights (first launch)…")
        }

        let deadline = Date().addingTimeInterval(effectiveStartupTimeout)
        while Date() < deadline {
            if !proc.isRunning {
                let logs = logBuffer.snapshot().suffix(12).joined(separator: "\n")
                let err = BackendSupervisorError.processExitedPrematurely(
                    code: proc.terminationStatus,
                    logs: logs
                )
                self.state = .failed(err.localizedDescription)
                self.managedProcess = nil
                self.processTracker.clear()
                throw err
            }

            if let health = await healthChecker(chosenPort), health.isHealthy {
                self.state = .running(port: chosenPort, attachedToExisting: false)
                return URL(string: "http://127.0.0.1:\(chosenPort)")!
            }

            try await Task.sleep(nanoseconds: 250_000_000)
        }

        let logs = logBuffer.snapshot().suffix(12).joined(separator: "\n")
        await stop()
        let err = BackendSupervisorError.startupTimeout(port: chosenPort, logs: logs)
        self.state = .failed(err.localizedDescription)
        throw err
    }

    public func stop() async {
        defer {
            managedProcess = nil
            attachedToExisting = false
            state = .stopped
        }

        guard !attachedToExisting else {
            processTracker.clear()
            return
        }

        processTracker.terminateSynchronously()
    }

    nonisolated public func terminateOwnedProcessSynchronously() {
        processTracker.terminateSynchronously()
    }

    private func handleChildTermination(status: Int32) {
        guard !attachedToExisting else { return }
        if case .stopped = state { return }
        let tail = logBuffer.snapshot().suffix(8).joined(separator: "\n")
        let suffix = tail.isEmpty ? "" : "\n\(tail)"
        if status != 0 {
            state = .failed("Backend exited (code \(status))\(suffix)")
        } else {
            state = .stopped
        }
        managedProcess = nil
        processTracker.clear()
        stateChangeHandler?(state)
    }

    // MARK: - Discovery & Port Helpers

    public struct PythonRunner: Sendable, Equatable {
        public let executableURL: URL
        public let baseArguments: [String]
        public let mainPyPath: String

        public func arguments(port: Int) -> [String] {
            baseArguments + [mainPyPath, "--host", "127.0.0.1", "--port", "\(port)", "--no-open"]
        }
    }

    public static func locateWorkspaceRoot(
        hint: URL? = nil,
        infoDictionaryWorkspacePath: String? = Bundle.main.object(forInfoDictionaryKey: "KobeanWorkspacePath") as? String
    ) -> URL? {
        let fm = FileManager.default
        var candidates: [URL] = []

        if let hint {
            candidates.append(hint.standardizedFileURL)
        }
        if let envPath = ProcessInfo.processInfo.environment["KOBEAN_WORKSPACE_DIR"], !envPath.isEmpty {
            candidates.append(URL(fileURLWithPath: envPath).standardizedFileURL)
        }
        if let infoPath = infoDictionaryWorkspacePath, !infoPath.isEmpty {
            candidates.append(URL(fileURLWithPath: infoPath).standardizedFileURL)
        }
        if let resourceURL = Bundle.main.resourceURL {
            candidates.append(resourceURL.appendingPathComponent("backend"))
        }

        func addParents(startingFrom startURL: URL) {
            var current = startURL.standardizedFileURL
            for _ in 0..<7 {
                candidates.append(current)
                let parent = current.deletingLastPathComponent()
                if parent == current { break }
                current = parent
            }
        }

        addParents(startingFrom: URL(fileURLWithPath: fm.currentDirectoryPath))
        if let execURL = Bundle.main.executableURL {
            addParents(startingFrom: execURL.deletingLastPathComponent())
        }

        candidates.append(
            fm.homeDirectoryForCurrentUser
                .appendingPathComponent("Developer")
                .appendingPathComponent("kobean-manga-colorizer")
        )

        var seen = Set<String>()
        for dir in candidates {
            let path = dir.path
            guard seen.insert(path).inserted else { continue }
            let mainPy = dir.appendingPathComponent("main.py")
            if fm.fileExists(atPath: mainPy.path) {
                return dir
            }
        }
        return nil
    }

    public static func defaultApplicationSupportDirectory() -> URL {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support", isDirectory: true)
        return base.appendingPathComponent(AppMetadata.appBundleName, isDirectory: true)
    }

    public static func isInsideAppBundle(_ url: URL) -> Bool {
        let bundlePath = Bundle.main.bundleURL.standardizedFileURL.path
        guard Bundle.main.bundleURL.pathExtension.lowercased() == "app" else { return false }
        return url.standardizedFileURL.path.hasPrefix(bundlePath)
    }

    public static func defaultDataDirectoryIfBundled(workspaceURL: URL) -> URL? {
        guard isInsideAppBundle(workspaceURL) else { return nil }
        return defaultApplicationSupportDirectory()
    }

    private func bootstrapEnvironmentWithUV(
        uvURL: URL,
        workspaceURL: URL,
        venvURL: URL,
        dataDirectory: URL?,
        timeout: TimeInterval
    ) async throws {
        let fm = FileManager.default
        let lockFile = workspaceURL.appendingPathComponent("uv.lock")
        let hasLock = fm.fileExists(atPath: lockFile.path)

        let proc = Process()
        proc.currentDirectoryURL = workspaceURL
        proc.executableURL = uvURL
        var args = ["sync", "--no-install-project", "--no-dev"]
        if hasLock {
            args.insert("--frozen", at: 1)
        }
        proc.arguments = args
        proc.environment = Self.enrichedEnvironment(
            dataDirectory: dataDirectory,
            venvDirectory: venvURL
        )

        let stdoutPipe = Pipe()
        let stderrPipe = Pipe()
        proc.standardOutput = stdoutPipe
        proc.standardError = stderrPipe

        let ring = self.logBuffer
        ring.append(chunk: "[Bootstrap] Running: \(uvURL.path) \(args.joined(separator: " "))")
        stdoutPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if !data.isEmpty, let text = String(data: data, encoding: .utf8) {
                ring.append(chunk: text)
            }
        }
        stderrPipe.fileHandleForReading.readabilityHandler = { handle in
            let data = handle.availableData
            if !data.isEmpty, let text = String(data: data, encoding: .utf8) {
                ring.append(chunk: text)
            }
        }

        do {
            try proc.run()
        } catch {
            stdoutPipe.fileHandleForReading.readabilityHandler = nil
            stderrPipe.fileHandleForReading.readabilityHandler = nil
            self.state = .failed(error.localizedDescription)
            throw error
        }

        self.managedProcess = proc
        self.processTracker.setOwned(proc)

        defer {
            stdoutPipe.fileHandleForReading.readabilityHandler = nil
            stderrPipe.fileHandleForReading.readabilityHandler = nil
            self.managedProcess = nil
            self.processTracker.clear()
        }

        let deadline = Date().addingTimeInterval(timeout)
        while proc.isRunning && Date() < deadline {
            try await Task.sleep(nanoseconds: 250_000_000)
        }

        if proc.isRunning {
            self.processTracker.terminateSynchronously()
            let logs = logBuffer.snapshot().suffix(20).joined(separator: "\n")
            let err = BackendSupervisorError.bootstrapFailed(code: -1, logs: "Timed out after \(Int(timeout))s.\n\(logs)")
            self.state = .failed(err.localizedDescription)
            throw err
        }

        // Drain any remaining buffered pipe output before inspecting logs
        let trailingOut = stdoutPipe.fileHandleForReading.readDataToEndOfFile()
        if !trailingOut.isEmpty, let text = String(data: trailingOut, encoding: .utf8) {
            ring.append(chunk: text)
        }
        let trailingErr = stderrPipe.fileHandleForReading.readDataToEndOfFile()
        if !trailingErr.isEmpty, let text = String(data: trailingErr, encoding: .utf8) {
            ring.append(chunk: text)
        }

        if proc.terminationStatus != 0 {
            let logs = logBuffer.snapshot().suffix(20).joined(separator: "\n")
            let err = BackendSupervisorError.bootstrapFailed(code: proc.terminationStatus, logs: logs)
            self.state = .failed(err.localizedDescription)
            throw err
        }

        if hasLock, let sig = Self.lockfileSignature(at: lockFile) {
            let stampURL = venvURL.appendingPathComponent(".kobean-lock-signature")
            try? sig.write(to: stampURL, atomically: true, encoding: .utf8)
        }
    }

    public static func enrichedEnvironment(
        base: [String: String] = ProcessInfo.processInfo.environment,
        dataDirectory: URL?,
        venvDirectory: URL?,
        disableBytecodeCache: Bool = false
    ) -> [String: String] {
        var env = base
        env["PYTHONUNBUFFERED"] = "1"
        if disableBytecodeCache {
            env["PYTHONDONTWRITEBYTECODE"] = "1"
        }
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        let extraPaths = [
            "/opt/homebrew/bin",
            "/usr/local/bin",
            "\(home)/.local/bin",
            "\(home)/.cargo/bin",
        ]
        let existingPath = env["PATH"] ?? "/usr/bin:/bin:/usr/sbin:/sbin"
        let existingParts = existingPath.split(separator: ":").map(String.init)
        var merged = extraPaths.filter { !existingParts.contains($0) }
        merged.append(contentsOf: existingParts)
        env["PATH"] = merged.joined(separator: ":")

        if let dataDirectory {
            env["KOBEAN_DATA_DIR"] = dataDirectory.standardizedFileURL.path
        }
        if let venvDirectory {
            env["UV_PROJECT_ENVIRONMENT"] = venvDirectory.standardizedFileURL.path
        }
        return env
    }

    public static func targetVenvDirectory(workspaceURL: URL, dataDirectory: URL?) -> URL {
        if let dataDirectory, isInsideAppBundle(workspaceURL) {
            return dataDirectory.appendingPathComponent(".venv", isDirectory: true)
        }
        return workspaceURL.appendingPathComponent(".venv", isDirectory: true)
    }

    public static func lockfileSignature(at lockFileURL: URL) -> String? {
        guard let data = try? Data(contentsOf: lockFileURL) else { return nil }
        let digest = SHA256.hash(data: data)
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    /// Fast, zero-subprocess check that a `.venv/bin/python3` actually has core backend
    /// packages (`fastapi` and `uvicorn`) installed in its `site-packages`, preventing an
    /// empty or half-installed `.venv` from trapping startup in a `ModuleNotFoundError` loop.
    public static func isVenvHealthy(_ pythonURL: URL) -> Bool {
        let fm = FileManager.default
        guard fm.isExecutableFile(atPath: pythonURL.path) else { return false }

        // Resolve `<venv>/bin/python3` -> `<venv>/lib/python*/site-packages`
        let venvRoot = pythonURL.deletingLastPathComponent().deletingLastPathComponent()
        let libDir = venvRoot.appendingPathComponent("lib", isDirectory: true)
        guard let libEntries = try? fm.contentsOfDirectory(
            at: libDir,
            includingPropertiesForKeys: nil,
            options: [.skipsHiddenFiles]
        ) else {
            return false
        }

        for entry in libEntries where entry.lastPathComponent.hasPrefix("python") {
            let sitePackages = entry.appendingPathComponent("site-packages", isDirectory: true)
            let fastapiDir = sitePackages.appendingPathComponent("fastapi")
            let uvicornDir = sitePackages.appendingPathComponent("uvicorn")
            if fm.fileExists(atPath: fastapiDir.path) && fm.fileExists(atPath: uvicornDir.path) {
                return true
            }
        }
        return false
    }

    public static func shouldBootstrapVenv(
        workspaceURL: URL,
        venvURL: URL,
        venvPythonURL: URL,
        isBundled: Bool
    ) -> Bool {
        let fm = FileManager.default
        let pyproject = workspaceURL.appendingPathComponent("pyproject.toml")
        guard fm.fileExists(atPath: pyproject.path) else { return false }

        if !isVenvHealthy(venvPythonURL) {
            // In non-bundled dev workspaces, also allow an existing healthy `venv/` before syncing.
            if !isBundled {
                let altVenvPython = workspaceURL.appendingPathComponent("venv/bin/python3")
                if isVenvHealthy(altVenvPython) {
                    return false
                }
            }
            return true
        }

        // For bundled app releases, re-sync automatically if an app update changed uv.lock.
        if isBundled {
            let lockFile = workspaceURL.appendingPathComponent("uv.lock")
            let stampURL = venvURL.appendingPathComponent(".kobean-lock-signature")
            if let expected = lockfileSignature(at: lockFile) {
                let current = (try? String(contentsOf: stampURL, encoding: .utf8))?
                    .trimmingCharacters(in: .whitespacesAndNewlines)
                if current != expected {
                    return true
                }
            }
        }
        return false
    }

    public static func locateUVExecutable() -> URL? {
        let fm = FileManager.default
        let home = fm.homeDirectoryForCurrentUser
        var uvCandidates = [
            URL(fileURLWithPath: "/opt/homebrew/bin/uv"),
            URL(fileURLWithPath: "/usr/local/bin/uv"),
            home.appendingPathComponent(".local/bin/uv"),
            home.appendingPathComponent(".cargo/bin/uv"),
        ]
        if let pathEnv = ProcessInfo.processInfo.environment["PATH"] {
            for dir in pathEnv.split(separator: ":") {
                uvCandidates.append(URL(fileURLWithPath: String(dir)).appendingPathComponent("uv"))
            }
        }
        var seen = Set<String>()
        for uvURL in uvCandidates {
            let path = uvURL.standardizedFileURL.path
            guard seen.insert(path).inserted else { continue }
            if fm.isExecutableFile(atPath: path) {
                return URL(fileURLWithPath: path)
            }
        }
        return nil
    }

    /// Surfaces the root error line (e.g. `ModuleNotFoundError: No module named 'fastapi'`)
    /// ahead of verbose traceback frames so compact UI banners show actionable diagnostics.
    public static func summarizeFailureLogs(_ logs: String) -> String {
        let lines = logs
            .split(whereSeparator: \.isNewline)
            .map { String($0).trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        guard !lines.isEmpty else { return "" }

        if lines.count > 1,
           let first = lines.first,
           first.hasPrefix("Traceback (most recent call last)"),
           let rootCause = lines.last,
           rootCause != first {
            return "\(rootCause)\n" + lines.joined(separator: "\n")
        }
        return lines.joined(separator: "\n")
    }

    public static func locatePythonRunner(
        in workspaceURL: URL,
        mainPyPath: String,
        dataDirectory: URL? = nil
    ) -> PythonRunner? {
        let fm = FileManager.default
        var venvCandidates = [
            workspaceURL.appendingPathComponent(".venv/bin/python3"),
            workspaceURL.appendingPathComponent("venv/bin/python3"),
        ]
        if isInsideAppBundle(workspaceURL) {
            let appSupportVenv = (dataDirectory ?? defaultApplicationSupportDirectory())
                .appendingPathComponent(".venv/bin/python3")
            venvCandidates.insert(appSupportVenv, at: 0)
        } else if let dataDirectory {
            venvCandidates.insert(
                dataDirectory.appendingPathComponent(".venv/bin/python3"),
                at: 0
            )
        }

        // Only accept virtualenvs that actually have backend dependencies installed.
        for pyURL in venvCandidates where isVenvHealthy(pyURL) {
            return PythonRunner(executableURL: pyURL, baseArguments: [], mainPyPath: mainPyPath)
        }

        if let uvURL = locateUVExecutable() {
            return PythonRunner(executableURL: uvURL, baseArguments: ["run", "--no-sync", "python"], mainPyPath: mainPyPath)
        }

        let systemPythonCandidates = [
            URL(fileURLWithPath: "/opt/homebrew/bin/python3"),
            URL(fileURLWithPath: "/usr/local/bin/python3"),
            URL(fileURLWithPath: "/usr/bin/python3"),
        ]
        for pyURL in systemPythonCandidates where fm.isExecutableFile(atPath: pyURL.path) {
            return PythonRunner(executableURL: pyURL, baseArguments: [], mainPyPath: mainPyPath)
        }

        return nil
    }

    public static func isLocalPortAvailable(_ port: Int) -> Bool {
        guard (1...65535).contains(port) else { return false }
        let sock = Darwin.socket(AF_INET, SOCK_STREAM, 0)
        guard sock >= 0 else { return false }
        defer { Darwin.close(sock) }

        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = in_port_t(UInt16(port).bigEndian)
        addr.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))

        let bindResult = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(sock, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        return bindResult == 0
    }

    public static func findAvailableLocalPort() -> Int? {
        let sock = Darwin.socket(AF_INET, SOCK_STREAM, 0)
        guard sock >= 0 else { return nil }
        defer { Darwin.close(sock) }

        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = 0
        addr.sin_addr = in_addr(s_addr: inet_addr("127.0.0.1"))

        let bindResult = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.bind(sock, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        guard bindResult == 0 else { return nil }

        var assigned = sockaddr_in()
        var len = socklen_t(MemoryLayout<sockaddr_in>.size)
        let nameResult = withUnsafeMutablePointer(to: &assigned) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.getsockname(sock, $0, &len)
            }
        }
        guard nameResult == 0 else { return nil }
        return Int(UInt16(bigEndian: assigned.sin_port))
    }

    private static func defaultProbeHealth(port: Int) async -> HealthStatus? {
        guard let url = URL(string: "http://127.0.0.1:\(port)/api/health") else { return nil }
        var req = URLRequest(url: url)
        req.timeoutInterval = 1.5
        do {
            let (data, resp) = try await URLSession.shared.data(for: req)
            guard let http = resp as? HTTPURLResponse, http.statusCode == 200 else { return nil }
            let health = try JSONDecoder().decode(HealthStatus.self, from: data)
            guard health.service == "kobean-manga-colorizer" || health.isHealthy else { return nil }
            return health
        } catch {
            return nil
        }
    }
}
