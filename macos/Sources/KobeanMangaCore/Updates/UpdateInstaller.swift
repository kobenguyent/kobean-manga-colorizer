import Foundation

public enum UpdateInstallMode: Equatable, Sendable {
    case replaceAndRelaunch(targetAppURL: URL)
    case openArtifactAndQuit
}

public struct UpdateInstallPlan: Equatable, Sendable {
    public let downloadedAssetURL: URL
    public let mode: UpdateInstallMode
    public let processID: Int32
    public let relaunchAfterInstall: Bool
    public let expectedBundleIdentifier: String?

    public init(
        downloadedAssetURL: URL,
        targetAppURL: URL? = UpdateInstaller.currentAppBundleURL(),
        processID: Int32 = ProcessInfo.processInfo.processIdentifier,
        relaunchAfterInstall: Bool = true,
        expectedBundleIdentifier: String? = AppMetadata.bundleIdentifier
    ) {
        self.downloadedAssetURL = downloadedAssetURL
        if let targetAppURL, targetAppURL.pathExtension.lowercased() == "app" {
            self.mode = .replaceAndRelaunch(targetAppURL: targetAppURL)
        } else {
            self.mode = .openArtifactAndQuit
        }
        self.processID = processID
        self.relaunchAfterInstall = relaunchAfterInstall
        self.expectedBundleIdentifier = expectedBundleIdentifier
    }
}

public enum UpdateInstallerError: LocalizedError, Equatable, Sendable {
    case assetNotFound(String)
    case unsupportedArchive(String)
    case failedToLaunchHelper(String)

    public var errorDescription: String? {
        switch self {
        case .assetNotFound(let path):
            return "Downloaded update package was not found at \(path)."
        case .unsupportedArchive(let name):
            return "Unsupported update package format: \(name). Expected .zip or .dmg."
        case .failedToLaunchHelper(let reason):
            return "Could not launch update helper: \(reason)"
        }
    }
}

/// Detached macOS self-updater:
/// Stages and validates the downloaded `.zip` or `.dmg`, clears macOS quarantine flags,
/// waits for the currently running Kobean Manga Colorizer process to exit cleanly,
/// atomically swaps the installed `.app` bundle (with automatic rollback on failure and
/// native macOS admin elevation fallback if `/Applications` requires elevation),
/// and relaunches the updated application.
public enum UpdateInstaller {
    public static func currentAppBundleURL() -> URL? {
        let bundleURL = Bundle.main.bundleURL
        return bundleURL.pathExtension.lowercased() == "app" ? bundleURL : nil
    }

    public static func shellSingleQuote(_ value: String) -> String {
        "'" + value.replacingOccurrences(of: "'", with: "'\\''") + "'"
    }

    public static func buildInstallScript(
        plan: UpdateInstallPlan,
        selfScriptPath: String? = nil
    ) throws -> String {
        let assetPath = plan.downloadedAssetURL.path
        let ext = plan.downloadedAssetURL.pathExtension.lowercased()
        guard ext == "zip" || ext == "dmg" else {
            throw UpdateInstallerError.unsupportedArchive(plan.downloadedAssetURL.lastPathComponent)
        }

        let quotedAsset = shellSingleQuote(assetPath)
        let cleanupSelfLine = selfScriptPath.map {
            "  rm -f \(shellSingleQuote($0)) 2>/dev/null || true"
        } ?? ""

        switch plan.mode {
        case .openArtifactAndQuit:
            return """
            #!/bin/zsh
            set -euo pipefail
            trap '' HUP
            APP_PID=\(plan.processID)
            ASSET=\(quotedAsset)

            cleanup() {
            \(cleanupSelfLine)
              true
            }
            trap cleanup EXIT

            for _ in {1..50}; do
              if ! kill -0 "$APP_PID" 2>/dev/null; then
                break
              fi
              sleep 0.1
            done

            open "$ASSET"
            """

        case .replaceAndRelaunch(let targetAppURL):
            let quotedTarget = shellSingleQuote(targetAppURL.path)
            let extractBlock: String
            if ext == "dmg" {
                extractBlock = """
                MOUNT_DIR="$WORK_DIR/mount"
                mkdir -p "$MOUNT_DIR"
                hdiutil attach -nobrowse -readonly -mountpoint "$MOUNT_DIR" "$ASSET" >/dev/null
                MOUNTED=1
                SRC_APP="$(find "$MOUNT_DIR" -maxdepth 2 -name '*.app' -print -quit)"
                if [[ -z "$SRC_APP" || ! -d "$SRC_APP" ]]; then
                  echo "No .app bundle found inside DMG" >&2
                  exit 1
                fi
                ditto "$SRC_APP" "$STAGED_APP"
                hdiutil detach "$MOUNT_DIR" -quiet || hdiutil detach "$MOUNT_DIR" -force -quiet || true
                MOUNTED=0
                """
            } else {
                extractBlock = """
                EXTRACT_DIR="$WORK_DIR/extract"
                mkdir -p "$EXTRACT_DIR"
                ditto -x -k "$ASSET" "$EXTRACT_DIR"
                SRC_APP="$(find "$EXTRACT_DIR" -maxdepth 2 -name '*.app' -print -quit)"
                if [[ -z "$SRC_APP" || ! -d "$SRC_APP" ]]; then
                  echo "No .app bundle found inside ZIP" >&2
                  exit 1
                fi
                mv "$SRC_APP" "$STAGED_APP"
                """
            }

            let bundleIDCheckBlock: String
            if let expectedID = plan.expectedBundleIdentifier, !expectedID.isEmpty {
                let quotedExpectedID = shellSingleQuote(expectedID)
                bundleIDCheckBlock = """
                EXPECTED_BUNDLE_ID=\(quotedExpectedID)
                STAGED_BUNDLE_ID="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$STAGED_APP/Contents/Info.plist" 2>/dev/null || true)"
                if [[ -n "$STAGED_BUNDLE_ID" && "$STAGED_BUNDLE_ID" != "$EXPECTED_BUNDLE_ID" ]]; then
                  echo "Bundle identifier mismatch: expected $EXPECTED_BUNDLE_ID, got $STAGED_BUNDLE_ID" >&2
                  exit 1
                fi
                """
            } else {
                bundleIDCheckBlock = ""
            }

            let relaunchBlock = plan.relaunchAfterInstall
                ? """
                sleep 0.2
                open -n "$TARGET_APP" || open "$TARGET_APP"
                """
                : "# Relaunch disabled for automated verification"

            return """
            #!/bin/zsh
            set -euo pipefail
            trap '' HUP

            APP_PID=\(plan.processID)
            ASSET=\(quotedAsset)
            TARGET_APP=\(quotedTarget)
            PARENT_DIR="$(dirname "$TARGET_APP")"
            WORK_DIR="$(mktemp -d /tmp/kobean-updater.XXXXXX)"
            STAGED_APP="$WORK_DIR/\(AppMetadata.appBundleName).app"
            BACKUP_APP="$WORK_DIR/\(AppMetadata.appBundleName)-previous.app"
            MOUNT_DIR=""
            MOUNTED=0

            cleanup() {
              if [[ "$MOUNTED" -eq 1 && -n "$MOUNT_DIR" ]]; then
                hdiutil detach "$MOUNT_DIR" -quiet || hdiutil detach "$MOUNT_DIR" -force -quiet || true
              fi
              rm -rf "$WORK_DIR" 2>/dev/null || true
            \(cleanupSelfLine)
            }
            trap cleanup EXIT

            # 1. Stage & verify updated app bundle FIRST while the running app shuts down
            \(extractBlock)

            if [[ ! -d "$STAGED_APP/Contents/MacOS" ]]; then
              echo "Extracted bundle is missing Contents/MacOS" >&2
              exit 1
            fi
            \(bundleIDCheckBlock)

            # Clear download quarantine attributes so ad-hoc signed builds launch cleanly
            xattr -cr "$STAGED_APP" 2>/dev/null || true

            # 2. Wait for current app instance to exit cleanly (up to 6s), then terminate if wedged
            for _ in {1..60}; do
              if ! kill -0 "$APP_PID" 2>/dev/null; then
                break
              fi
              sleep 0.1
            done
            if kill -0 "$APP_PID" 2>/dev/null; then
              kill -TERM "$APP_PID" 2>/dev/null || true
              for _ in {1..20}; do
                if ! kill -0 "$APP_PID" 2>/dev/null; then
                  break
                fi
                sleep 0.1
              done
            fi

            # 3. Atomically replace TARGET_APP (with rollback protection)
            if [[ -w "$PARENT_DIR" ]] && [[ ! -e "$TARGET_APP" || -w "$TARGET_APP" ]]; then
              if [[ -e "$TARGET_APP" ]]; then
                mv "$TARGET_APP" "$BACKUP_APP"
              fi
              if ! mv "$STAGED_APP" "$TARGET_APP"; then
                if [[ -e "$BACKUP_APP" ]]; then
                  mv "$BACKUP_APP" "$TARGET_APP" 2>/dev/null || true
                fi
                open "$ASSET" 2>/dev/null || true
                exit 1
              fi
              rm -rf "$BACKUP_APP" 2>/dev/null || true
            else
              # Native macOS admin elevation fallback for root-owned /Applications
              if ! osascript - "$STAGED_APP" "$TARGET_APP" <<'APPLESCRIPT'
            on run argv
              set stagedApp to quoted form of (item 1 of argv)
              set targetApp to quoted form of (item 2 of argv)
              do shell script "rm -rf " & targetApp & " && mv " & stagedApp & " " & targetApp with administrator privileges
            end run
            APPLESCRIPT
              then
                open "$ASSET" 2>/dev/null || true
                exit 1
              fi
            fi

            # 4. Relaunch updated application
            \(relaunchBlock)
            """
        }
    }

    public static func launchDetachedInstaller(plan: UpdateInstallPlan) throws {
        guard FileManager.default.fileExists(atPath: plan.downloadedAssetURL.path) else {
            throw UpdateInstallerError.assetNotFound(plan.downloadedAssetURL.path)
        }

        let scriptURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("kobean-updater-\(UUID().uuidString).sh")
        let script = try buildInstallScript(plan: plan, selfScriptPath: scriptURL.path)

        do {
            try script.write(to: scriptURL, atomically: true, encoding: .utf8)
            try FileManager.default.setAttributes(
                [.posixPermissions: 0o700],
                ofItemAtPath: scriptURL.path
            )
        } catch {
            throw UpdateInstallerError.failedToLaunchHelper(error.localizedDescription)
        }

        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = [scriptURL.path]
        process.standardInput = FileHandle.nullDevice

        let logPath = "/tmp/kobean-manga-updater.log"
        FileManager.default.createFile(atPath: logPath, contents: nil)
        if let logHandle = FileHandle(forWritingAtPath: logPath) {
            logHandle.seekToEndOfFile()
            process.standardOutput = logHandle
            process.standardError = logHandle
        } else {
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
        }

        do {
            try process.run()
        } catch {
            try? FileManager.default.removeItem(at: scriptURL)
            throw UpdateInstallerError.failedToLaunchHelper(error.localizedDescription)
        }
    }
}
