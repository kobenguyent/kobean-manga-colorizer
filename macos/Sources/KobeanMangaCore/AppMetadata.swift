import Foundation

public enum AppMetadata {
    public static let appName = "Kobean Manga Colorizer"
    public static let appBundleName = "KobeanMangaColorizer"
    public static let bundleIdentifier = "ai.kobean.manga-colorizer.macos"
    public static let defaultGitHubRepo = "kobenguyent/kobean-manga-colorizer"
    public static let fallbackVersion = "1.0.0"

    public static var currentVersionString: String {
        if let version = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String,
           !version.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return version
        }
        return fallbackVersion
    }

    public static var currentSemanticVersion: SemanticVersion {
        SemanticVersion(parsing: currentVersionString) ?? SemanticVersion(major: 1, minor: 0, patch: 0)
    }

    public static var buildNumber: String {
        (Bundle.main.infoDictionary?["CFBundleVersion"] as? String) ?? "1"
    }

    public static var configuredGitHubRepo: String {
        if let repo = Bundle.main.infoDictionary?["KobeanGitHubRepo"] as? String,
           !repo.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return repo
        }
        return defaultGitHubRepo
    }

    public static var userAgent: String {
        "\(appBundleName)/\(currentVersionString) (macOS)"
    }
}
