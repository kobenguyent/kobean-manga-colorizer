import Foundation
import XCTest
@testable import KobeanMangaCore

private final class MockUpdateHTTPClient: UpdateHTTPFetching, @unchecked Sendable {
    var fetchHandler: (@Sendable (URLRequest) async throws -> UpdateHTTPResponse)?
    var downloadHandler: (@Sendable (URL, URL, (@Sendable (Double) -> Void)?) async throws -> URL)?

    func fetch(_ request: URLRequest) async throws -> UpdateHTTPResponse {
        guard let handler = fetchHandler else {
            throw UpdateError.invalidResponse
        }
        return try await handler(request)
    }

    func download(
        from url: URL,
        to destination: URL,
        progress: (@Sendable (Double) -> Void)?
    ) async throws -> URL {
        guard let handler = downloadHandler else {
            throw UpdateError.invalidResponse
        }
        return try await handler(url, destination, progress)
    }
}

final class UpdateServiceTests: XCTestCase {
    func testSemanticVersionParsingAndComparison() {
        let v100 = SemanticVersion(parsing: "v1.0.0")
        let v110 = SemanticVersion(parsing: "1.1.0")
        let v110Beta1 = SemanticVersion(parsing: "v1.1.0-beta.1")
        let v110Beta2 = SemanticVersion(parsing: "v1.1.0-beta.2+build.9")
        let v200 = SemanticVersion(parsing: "2.0")

        XCTAssertEqual(v100?.description, "1.0.0")
        XCTAssertEqual(v200?.description, "2.0.0")
        XCTAssertEqual(v110Beta2?.description, "1.1.0-beta.2")
        XCTAssertNil(SemanticVersion(parsing: "not-a-version"))

        XCTAssertLessThan(v100!, v110Beta1!)
        XCTAssertLessThan(v110Beta1!, v110Beta2!)
        XCTAssertLessThan(v110Beta2!, v110!)
        XCTAssertLessThan(v110!, v200!)
    }

    func testPreferredMacAssetSelectionPrefersZipAndUniversal() {
        let release = GitHubRelease(
            tagName: "v1.2.0",
            htmlURL: URL(string: "https://github.com/kobenguyent/kobean-manga-colorizer/releases/tag/v1.2.0")!,
            assets: [
                GitHubReleaseAsset(
                    name: "KobeanMangaColorizer-1.2.0-macOS-universal.dmg",
                    browserDownloadURL: URL(string: "https://example.com/app.dmg")!,
                    size: 12_000_000
                ),
                GitHubReleaseAsset(
                    name: "KobeanMangaColorizer-1.2.0-macOS-universal.zip",
                    browserDownloadURL: URL(string: "https://example.com/app.zip")!,
                    size: 11_000_000
                ),
                GitHubReleaseAsset(
                    name: "SHA256SUMS.txt",
                    browserDownloadURL: URL(string: "https://example.com/SHA256SUMS.txt")!,
                    size: 256
                ),
            ]
        )

        XCTAssertEqual(
            release.preferredMacAsset(architecture: "arm64")?.name,
            "KobeanMangaColorizer-1.2.0-macOS-universal.zip"
        )
        XCTAssertEqual(release.checksumAsset?.name, "SHA256SUMS.txt")
    }

    func testCheckForUpdatesDetectsNewerGitHubRelease() async throws {
        let mockHTTP = MockUpdateHTTPClient()
        let json = """
        {
          "tag_name": "v1.3.0",
          "name": "Kobean Manga Colorizer v1.3.0",
          "body": "- Added native auto-update\\n- Fixed iPad MOBI export",
          "html_url": "https://github.com/kobenguyent/kobean-manga-colorizer/releases/tag/v1.3.0",
          "draft": false,
          "prerelease": false,
          "assets": [
            {
              "name": "KobeanMangaColorizer-1.3.0-macOS-universal.zip",
              "browser_download_url": "https://github.com/kobenguyent/kobean-manga-colorizer/releases/download/v1.3.0/KobeanMangaColorizer-1.3.0-macOS-universal.zip",
              "size": 10485760
            },
            {
              "name": "SHA256SUMS.txt",
              "browser_download_url": "https://github.com/kobenguyent/kobean-manga-colorizer/releases/download/v1.3.0/SHA256SUMS.txt",
              "size": 180
            }
          ]
        }
        """
        mockHTTP.fetchHandler = { req in
            XCTAssertEqual(
                req.url?.absoluteString,
                "https://api.github.com/repos/kobenguyent/kobean-manga-colorizer/releases/latest"
            )
            return UpdateHTTPResponse(data: Data(json.utf8), statusCode: 200)
        }

        let service = UpdateService(httpClient: mockHTTP)
        let outcome = try await service.checkForUpdates(
            repository: "kobenguyent/kobean-manga-colorizer",
            currentVersion: SemanticVersion(major: 1, minor: 0, patch: 0)
        )

        guard case .updateAvailable(let release, let latestVersion, let asset) = outcome else {
            return XCTFail("Expected .updateAvailable, got \(outcome)")
        }
        XCTAssertEqual(release.tagName, "v1.3.0")
        XCTAssertEqual(latestVersion, SemanticVersion(major: 1, minor: 3, patch: 0))
        XCTAssertEqual(asset?.name, "KobeanMangaColorizer-1.3.0-macOS-universal.zip")

        // Same version reports upToDate
        let upToDate = try await service.checkForUpdates(
            repository: "kobenguyent/kobean-manga-colorizer",
            currentVersion: SemanticVersion(major: 1, minor: 3, patch: 0)
        )
        guard case .upToDate(let current, _) = upToDate else {
            return XCTFail("Expected .upToDate")
        }
        XCTAssertEqual(current, SemanticVersion(major: 1, minor: 3, patch: 0))
    }

    func testCheckForUpdatesHandles404AndInvalidRepo() async {
        let mockHTTP = MockUpdateHTTPClient()
        mockHTTP.fetchHandler = { _ in
            UpdateHTTPResponse(data: Data(), statusCode: 404)
        }
        let service = UpdateService(httpClient: mockHTTP)

        do {
            _ = try await service.checkForUpdates(repository: "invalid-repo")
            XCTFail("Expected invalidRepository error")
        } catch let err as UpdateError {
            XCTAssertEqual(err, .invalidRepository("invalid-repo"))
        } catch {
            XCTFail("Unexpected error: \(error)")
        }

        do {
            _ = try await service.checkForUpdates(repository: "kobenguyent/kobean-manga-colorizer")
            XCTFail("Expected noReleasePublished error")
        } catch let err as UpdateError {
            XCTAssertEqual(err, .noReleasePublished)
        } catch {
            XCTFail("Unexpected error: \(error)")
        }
    }

    func testDownloadAndVerifyMatchesAndRejectsBadChecksum() async throws {
        let tmpDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("kobean-update-test-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tmpDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        let payload = Data("kobean-update-binary-payload".utf8)
        let sampleFile = tmpDir.appendingPathComponent("payload.bin")
        try payload.write(to: sampleFile)
        let validSHA = try UpdateService.sha256Hex(of: sampleFile)

        let asset = GitHubReleaseAsset(
            name: "KobeanMangaColorizer-1.2.0-macOS-universal.zip",
            browserDownloadURL: URL(string: "https://example.com/app.zip")!,
            size: Int64(payload.count)
        )
        let checksumAsset = GitHubReleaseAsset(
            name: "SHA256SUMS.txt",
            browserDownloadURL: URL(string: "https://example.com/SHA256SUMS.txt")!,
            size: 120
        )
        let release = GitHubRelease(
            tagName: "v1.2.0",
            htmlURL: URL(string: "https://example.com/release")!,
            assets: [asset, checksumAsset]
        )

        // 1. Valid SHA-256 passes
        let mockOK = MockUpdateHTTPClient()
        mockOK.downloadHandler = { _, dest, progress in
            try FileManager.default.createDirectory(at: dest.deletingLastPathComponent(), withIntermediateDirectories: true)
            try payload.write(to: dest)
            progress?(0.5)
            progress?(1.0)
            return dest
        }
        mockOK.fetchHandler = { _ in
            let text = "\(validSHA)  KobeanMangaColorizer-1.2.0-macOS-universal.zip\n"
            return UpdateHTTPResponse(data: Data(text.utf8), statusCode: 200)
        }

        let serviceOK = UpdateService(httpClient: mockOK)
        let artifact = try await serviceOK.downloadAndVerify(
            release: release,
            asset: asset,
            destinationDirectory: tmpDir.appendingPathComponent("ok", isDirectory: true)
        )
        XCTAssertTrue(artifact.verifiedAgainstChecksums)
        XCTAssertEqual(artifact.sha256, validSHA)
        XCTAssertTrue(FileManager.default.fileExists(atPath: artifact.fileURL.path))

        // 2. Corrupted SHA-256 rejects and deletes downloaded file
        let mockBad = MockUpdateHTTPClient()
        mockBad.downloadHandler = mockOK.downloadHandler
        mockBad.fetchHandler = { _ in
            let text = "0000000000000000000000000000000000000000000000000000000000000000  KobeanMangaColorizer-1.2.0-macOS-universal.zip\n"
            return UpdateHTTPResponse(data: Data(text.utf8), statusCode: 200)
        }
        let serviceBad = UpdateService(httpClient: mockBad)
        let badDir = tmpDir.appendingPathComponent("bad", isDirectory: true)
        do {
            _ = try await serviceBad.downloadAndVerify(
                release: release,
                asset: asset,
                destinationDirectory: badDir
            )
            XCTFail("Expected checksumMismatch")
        } catch let err as UpdateError {
            guard case .checksumMismatch = err else {
                return XCTFail("Expected checksumMismatch, got \(err)")
            }
            XCTAssertFalse(FileManager.default.fileExists(atPath: badDir.appendingPathComponent(asset.name).path))
        }
    }

    func testUpdateInstallerReplacesAppBundleFromZipEndToEnd() throws {
        let tmpDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("kobean-installer-e2e-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tmpDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        // Create installed v1.0.0 dummy .app bundle
        let targetApp = tmpDir.appendingPathComponent("KobeanMangaColorizer.app", isDirectory: true)
        try makeDummyAppBundle(at: targetApp, version: "1.0.0", bundleID: AppMetadata.bundleIdentifier)

        // Create staged v1.2.0 dummy .app bundle and zip it with ditto (exact release format)
        let srcDir = tmpDir.appendingPathComponent("src", isDirectory: true)
        let newApp = srcDir.appendingPathComponent("KobeanMangaColorizer.app", isDirectory: true)
        try makeDummyAppBundle(at: newApp, version: "1.2.0", bundleID: AppMetadata.bundleIdentifier)

        let zipURL = tmpDir.appendingPathComponent("KobeanMangaColorizer-1.2.0-macOS-universal.zip")
        let ditto = Process()
        ditto.executableURL = URL(fileURLWithPath: "/usr/bin/ditto")
        ditto.arguments = ["-c", "-k", "--sequesterRsrc", "--keepParent", newApp.path, zipURL.path]
        try ditto.run()
        ditto.waitUntilExit()
        XCTAssertEqual(ditto.terminationStatus, 0)

        // Build and run install script with a non-existent PID (simulating app already closed) and relaunch disabled
        let plan = UpdateInstallPlan(
            downloadedAssetURL: zipURL,
            targetAppURL: targetApp,
            processID: 999_999,
            relaunchAfterInstall: false,
            expectedBundleIdentifier: AppMetadata.bundleIdentifier
        )
        let script = try UpdateInstaller.buildInstallScript(plan: plan)
        XCTAssertTrue(script.contains("ditto -x -k"))
        XCTAssertTrue(script.contains("xattr -cr"))
        XCTAssertTrue(script.contains(AppMetadata.bundleIdentifier))

        let scriptURL = tmpDir.appendingPathComponent("run-update.sh")
        try script.write(to: scriptURL, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o700], ofItemAtPath: scriptURL.path)

        let runner = Process()
        runner.executableURL = URL(fileURLWithPath: "/bin/zsh")
        runner.arguments = [scriptURL.path]
        try runner.run()
        runner.waitUntilExit()
        XCTAssertEqual(runner.terminationStatus, 0)

        // Verify installed .app was atomically replaced with v1.2.0
        let plistData = try Data(contentsOf: targetApp.appendingPathComponent("Contents/Info.plist"))
        let plist = try PropertyListSerialization.propertyList(from: plistData, format: nil) as? [String: Any]
        XCTAssertEqual(plist?["CFBundleShortVersionString"] as? String, "1.2.0")
    }

    @MainActor
    func testStudioStoreDownloadAutomaticallyLaunchesUpdaterAndClosesCurrentApp() async throws {
        let tmpDir = FileManager.default.temporaryDirectory
            .appendingPathComponent("kobean-store-update-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tmpDir, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: tmpDir) }

        let payload = Data("zip-bytes".utf8)
        let tmpPayload = tmpDir.appendingPathComponent("tmp.bin")
        try payload.write(to: tmpPayload)
        let validSHA = try UpdateService.sha256Hex(of: tmpPayload)

        let asset = GitHubReleaseAsset(
            name: "KobeanMangaColorizer-2.0.0-macOS-universal.zip",
            browserDownloadURL: URL(string: "https://example.com/v2.zip")!,
            size: Int64(payload.count)
        )
        let checksumAsset = GitHubReleaseAsset(
            name: "SHA256SUMS.txt",
            browserDownloadURL: URL(string: "https://example.com/SHA256SUMS.txt")!,
            size: 128
        )
        let release = GitHubRelease(
            tagName: "v2.0.0",
            name: "Kobean Manga Colorizer v2.0.0",
            htmlURL: URL(string: "https://example.com/v2")!,
            assets: [asset, checksumAsset]
        )

        let mockHTTP = MockUpdateHTTPClient()
        mockHTTP.downloadHandler = { _, dest, progress in
            try FileManager.default.createDirectory(at: dest.deletingLastPathComponent(), withIntermediateDirectories: true)
            try payload.write(to: dest)
            progress?(1.0)
            return dest
        }
        mockHTTP.fetchHandler = { _ in
            UpdateHTTPResponse(
                data: Data("\(validSHA)  \(asset.name)\n".utf8),
                statusCode: 200
            )
        }

        let targetAppURL = tmpDir.appendingPathComponent("KobeanMangaColorizer.app", isDirectory: true)
        let suiteName = "ai.kobean.update.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)

        var capturedPlan: UpdateInstallPlan?
        var terminatedApp = false

        let store = StudioStore(
            supervisor: BackendSupervisor(),
            keychain: KeychainHelper(inMemory: true),
            userDefaults: defaults,
            updateService: UpdateService(httpClient: mockHTTP),
            updateInstallerHandler: { plan in
                capturedPlan = plan
            },
            terminateAppHandler: {
                terminatedApp = true
            },
            currentVersionProvider: { SemanticVersion(major: 1, minor: 0, patch: 0) },
            targetAppBundleProvider: { targetAppURL }
        )

        await store.downloadAndInstallUpdate(release: release, asset: asset, autoCloseAndInstall: true)

        XCTAssertEqual(capturedPlan?.mode, .replaceAndRelaunch(targetAppURL: targetAppURL))
        XCTAssertTrue(terminatedApp, "App must close automatically once update is downloaded and verified")
        XCTAssertEqual(store.updateState, .installing(release: release))
    }

    private func makeDummyAppBundle(at appURL: URL, version: String, bundleID: String) throws {
        let macOSDir = appURL.appendingPathComponent("Contents/MacOS", isDirectory: true)
        try FileManager.default.createDirectory(at: macOSDir, withIntermediateDirectories: true)
        let execURL = macOSDir.appendingPathComponent(AppMetadata.appBundleName)
        try Data("#!/bin/sh\necho \(version)\n".utf8).write(to: execURL)
        try FileManager.default.setAttributes([.posixPermissions: 0o755], ofItemAtPath: execURL.path)

        let plist: [String: Any] = [
            "CFBundleExecutable": AppMetadata.appBundleName,
            "CFBundleIdentifier": bundleID,
            "CFBundleShortVersionString": version,
            "CFBundleVersion": "1",
        ]
        let plistData = try PropertyListSerialization.data(fromPropertyList: plist, format: .xml, options: 0)
        try plistData.write(to: appURL.appendingPathComponent("Contents/Info.plist"))
    }
}
