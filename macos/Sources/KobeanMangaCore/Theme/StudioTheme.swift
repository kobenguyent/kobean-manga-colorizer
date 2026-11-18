import AppKit
import SwiftUI

public enum StudioThemeID: String, Codable, Sendable, CaseIterable, Identifiable {
    // Classic IDE Dark & Light Themes (VS Code & PyCharm / JetBrains)
    case vscodeDarkModern = "vscode-dark-modern"
    case vscodeLightModern = "vscode-light-modern"
    case pycharmDarcula = "pycharm-darcula"
    case pycharmLight = "pycharm-light"

    // Studio Editorial & Manga Themes
    case cyberNeon = "cyber-neon"
    case mangaInk = "manga-ink"
    case shonenSunrise = "shonen-sunrise"
    case sakuraTwilight = "sakura-twilight"
    case emeraldAlchemist = "emerald-alchemist"
    case nordFrost = "nord-frost"
    case paperStudio = "paper-studio"

    public var id: String { rawValue }

    public var theme: StudioTheme {
        switch self {
        case .vscodeDarkModern: return .vscodeDarkModern
        case .vscodeLightModern: return .vscodeLightModern
        case .pycharmDarcula: return .pycharmDarcula
        case .pycharmLight: return .pycharmLight
        case .cyberNeon: return .cyberNeon
        case .mangaInk: return .mangaInk
        case .shonenSunrise: return .shonenSunrise
        case .sakuraTwilight: return .sakuraTwilight
        case .emeraldAlchemist: return .emeraldAlchemist
        case .nordFrost: return .nordFrost
        case .paperStudio: return .paperStudio
        }
    }
}

public struct StudioTheme: Sendable, Equatable, Identifiable {
    public let id: StudioThemeID
    public let displayName: String
    public let tagline: String
    public let isLightTheme: Bool

    public let bgDarkHex: String
    public let bgCardHex: String
    public let bgCardSubtleHex: String
    public let bgCardBorderHex: String
    public let bgInputHex: String
    public let bgHeaderHex: String
    public let textPrimaryHex: String
    public let textSecondaryHex: String
    public let textMutedHex: String
    public let accentPrimaryHex: String
    public let accentSecondaryHex: String
    public let accentPinkHex: String
    public let accentGreenHex: String
    public let accentYellowHex: String

    public let bgCardAlpha: Double
    public let bgCardSubtleAlpha: Double
    public let bgCardBorderAlpha: Double
    public let bgInputAlpha: Double
    public let bgHeaderAlpha: Double

    public var preferredColorScheme: ColorScheme {
        isLightTheme ? .light : .dark
    }

    public var bgDark: Color { Color(studioHex: bgDarkHex) }
    public var bgCard: Color { Color(studioHex: bgCardHex, alpha: bgCardAlpha) }
    public var bgCardSubtle: Color { Color(studioHex: bgCardSubtleHex, alpha: bgCardSubtleAlpha) }
    public var bgCardBorder: Color { Color(studioHex: bgCardBorderHex, alpha: bgCardBorderAlpha) }
    public var bgInput: Color { Color(studioHex: bgInputHex, alpha: bgInputAlpha) }
    public var bgHeader: Color { Color(studioHex: bgHeaderHex, alpha: bgHeaderAlpha) }
    public var textPrimary: Color { Color(studioHex: textPrimaryHex) }
    public var textSecondary: Color { Color(studioHex: textSecondaryHex) }
    public var textMuted: Color { Color(studioHex: textMutedHex) }
    public var accentPrimary: Color { Color(studioHex: accentPrimaryHex) }
    public var accentSecondary: Color { Color(studioHex: accentSecondaryHex) }
    public var accentPink: Color { Color(studioHex: accentPinkHex) }
    public var accentGreen: Color { Color(studioHex: accentGreenHex) }
    public var accentYellow: Color { Color(studioHex: accentYellowHex) }

    public static let vscodeDarkModern = StudioTheme(
        id: .vscodeDarkModern,
        displayName: "VS Code Dark+",
        tagline: "Dark Modern · Editor Slate & Azure",
        isLightTheme: false,
        bgDarkHex: "#1e1e1e",
        bgCardHex: "#252526",
        bgCardSubtleHex: "#2d2d2d",
        bgCardBorderHex: "#3c3c3c",
        bgInputHex: "#313131",
        bgHeaderHex: "#181818",
        textPrimaryHex: "#cccccc",
        textSecondaryHex: "#9d9d9d",
        textMutedHex: "#6e7681",
        accentPrimaryHex: "#0078d4",
        accentSecondaryHex: "#3794ff",
        accentPinkHex: "#c586c0",
        accentGreenHex: "#4ec9b0",
        accentYellowHex: "#dcdcaa",
        bgCardAlpha: 0.96,
        bgCardSubtleAlpha: 0.92,
        bgCardBorderAlpha: 0.85,
        bgInputAlpha: 0.95,
        bgHeaderAlpha: 0.98
    )

    public static let vscodeLightModern = StudioTheme(
        id: .vscodeLightModern,
        displayName: "VS Code Light+",
        tagline: "Light Modern · Crisp Daylight & Blue",
        isLightTheme: true,
        bgDarkHex: "#ffffff",
        bgCardHex: "#f8f8f8",
        bgCardSubtleHex: "#f3f3f3",
        bgCardBorderHex: "#e5e5e5",
        bgInputHex: "#ffffff",
        bgHeaderHex: "#f3f3f3",
        textPrimaryHex: "#3b3b3b",
        textSecondaryHex: "#616161",
        textMutedHex: "#868686",
        accentPrimaryHex: "#005fb8",
        accentSecondaryHex: "#0078d4",
        accentPinkHex: "#af00db",
        accentGreenHex: "#107c41",
        accentYellowHex: "#b89500",
        bgCardAlpha: 0.98,
        bgCardSubtleAlpha: 0.96,
        bgCardBorderAlpha: 1.0,
        bgInputAlpha: 1.0,
        bgHeaderAlpha: 0.98
    )

    public static let pycharmDarcula = StudioTheme(
        id: .pycharmDarcula,
        displayName: "PyCharm Darcula",
        tagline: "JetBrains Darcula · Graphite & Blue",
        isLightTheme: false,
        bgDarkHex: "#1e1f22",
        bgCardHex: "#2b2d30",
        bgCardSubtleHex: "#26282e",
        bgCardBorderHex: "#393b40",
        bgInputHex: "#35373b",
        bgHeaderHex: "#2b2d30",
        textPrimaryHex: "#dfe1e5",
        textSecondaryHex: "#adb0b8",
        textMutedHex: "#6f737a",
        accentPrimaryHex: "#3574f0",
        accentSecondaryHex: "#548af7",
        accentPinkHex: "#c77dbb",
        accentGreenHex: "#57965c",
        accentYellowHex: "#e0bb65",
        bgCardAlpha: 0.96,
        bgCardSubtleAlpha: 0.92,
        bgCardBorderAlpha: 0.90,
        bgInputAlpha: 0.94,
        bgHeaderAlpha: 0.98
    )

    public static let pycharmLight = StudioTheme(
        id: .pycharmLight,
        displayName: "PyCharm Light",
        tagline: "JetBrains Islands Light · Alabaster & Cobalt",
        isLightTheme: true,
        bgDarkHex: "#ffffff",
        bgCardHex: "#f7f8fa",
        bgCardSubtleHex: "#ebecf0",
        bgCardBorderHex: "#d3d5db",
        bgInputHex: "#ffffff",
        bgHeaderHex: "#f7f8fa",
        textPrimaryHex: "#1e1f22",
        textSecondaryHex: "#4e5157",
        textMutedHex: "#8c8f96",
        accentPrimaryHex: "#3574f0",
        accentSecondaryHex: "#2e5cb8",
        accentPinkHex: "#a74c9b",
        accentGreenHex: "#368746",
        accentYellowHex: "#c27d1a",
        bgCardAlpha: 0.98,
        bgCardSubtleAlpha: 0.96,
        bgCardBorderAlpha: 0.95,
        bgInputAlpha: 1.0,
        bgHeaderAlpha: 0.98
    )

    public static let cyberNeon = StudioTheme(
        id: .cyberNeon,
        displayName: "Cyber Neon",
        tagline: "Deep Obsidian · Cyan & Violet",
        isLightTheme: false,
        bgDarkHex: "#090d16",
        bgCardHex: "#121826",
        bgCardSubtleHex: "#0f172a",
        bgCardBorderHex: "#ffffff",
        bgInputHex: "#1e293b",
        bgHeaderHex: "#090d16",
        textPrimaryHex: "#f8fafc",
        textSecondaryHex: "#94a3b8",
        textMutedHex: "#64748b",
        accentPrimaryHex: "#06b6d4",
        accentSecondaryHex: "#8b5cf6",
        accentPinkHex: "#ec4899",
        accentGreenHex: "#10b981",
        accentYellowHex: "#eab308",
        bgCardAlpha: 0.75,
        bgCardSubtleAlpha: 0.70,
        bgCardBorderAlpha: 0.08,
        bgInputAlpha: 0.60,
        bgHeaderAlpha: 0.88
    )

    public static let mangaInk = StudioTheme(
        id: .mangaInk,
        displayName: "Manga Ink",
        tagline: "Monochrome Ink · Screentone Slate",
        isLightTheme: false,
        bgDarkHex: "#0a0b0e",
        bgCardHex: "#13151a",
        bgCardSubtleHex: "#111318",
        bgCardBorderHex: "#ffffff",
        bgInputHex: "#1c1f26",
        bgHeaderHex: "#0a0b0e",
        textPrimaryHex: "#f8fafc",
        textSecondaryHex: "#a1a1aa",
        textMutedHex: "#71717a",
        accentPrimaryHex: "#e2e8f0",
        accentSecondaryHex: "#94a3b8",
        accentPinkHex: "#cbd5e1",
        accentGreenHex: "#34d399",
        accentYellowHex: "#fbbf24",
        bgCardAlpha: 0.82,
        bgCardSubtleAlpha: 0.75,
        bgCardBorderAlpha: 0.10,
        bgInputAlpha: 0.70,
        bgHeaderAlpha: 0.92
    )

    public static let shonenSunrise = StudioTheme(
        id: .shonenSunrise,
        displayName: "Shonen Sunrise",
        tagline: "Warm Charcoal · Amber & Crimson",
        isLightTheme: false,
        bgDarkHex: "#0f0a09",
        bgCardHex: "#1b1210",
        bgCardSubtleHex: "#180f0d",
        bgCardBorderHex: "#f59e0b",
        bgInputHex: "#2b1b17",
        bgHeaderHex: "#0f0a09",
        textPrimaryHex: "#fff7ed",
        textSecondaryHex: "#fdba74",
        textMutedHex: "#9a6850",
        accentPrimaryHex: "#f59e0b",
        accentSecondaryHex: "#ef4444",
        accentPinkHex: "#f97316",
        accentGreenHex: "#10b981",
        accentYellowHex: "#fbbf24",
        bgCardAlpha: 0.82,
        bgCardSubtleAlpha: 0.75,
        bgCardBorderAlpha: 0.14,
        bgInputAlpha: 0.65,
        bgHeaderAlpha: 0.92
    )

    public static let sakuraTwilight = StudioTheme(
        id: .sakuraTwilight,
        displayName: "Sakura Twilight",
        tagline: "Plum Twilight · Sakura & Lavender",
        isLightTheme: false,
        bgDarkHex: "#0f0a17",
        bgCardHex: "#1c122a",
        bgCardSubtleHex: "#170e24",
        bgCardBorderHex: "#f472b6",
        bgInputHex: "#2d1c44",
        bgHeaderHex: "#0f0a17",
        textPrimaryHex: "#fdf2f8",
        textSecondaryHex: "#e9d5ff",
        textMutedHex: "#9d8ba8",
        accentPrimaryHex: "#f472b6",
        accentSecondaryHex: "#c084fc",
        accentPinkHex: "#fb7185",
        accentGreenHex: "#34d399",
        accentYellowHex: "#fde047",
        bgCardAlpha: 0.80,
        bgCardSubtleAlpha: 0.75,
        bgCardBorderAlpha: 0.15,
        bgInputAlpha: 0.65,
        bgHeaderAlpha: 0.92
    )

    public static let emeraldAlchemist = StudioTheme(
        id: .emeraldAlchemist,
        displayName: "Emerald Alchemist",
        tagline: "Deep Forest · Emerald & Teal",
        isLightTheme: false,
        bgDarkHex: "#06120d",
        bgCardHex: "#0d1e16",
        bgCardSubtleHex: "#0a1a13",
        bgCardBorderHex: "#10b981",
        bgInputHex: "#143024",
        bgHeaderHex: "#06120d",
        textPrimaryHex: "#f0fdf4",
        textSecondaryHex: "#a7f3d0",
        textMutedHex: "#5eead4",
        accentPrimaryHex: "#10b981",
        accentSecondaryHex: "#2dd4bf",
        accentPinkHex: "#84cc16",
        accentGreenHex: "#10b981",
        accentYellowHex: "#facc15",
        bgCardAlpha: 0.82,
        bgCardSubtleAlpha: 0.75,
        bgCardBorderAlpha: 0.15,
        bgInputAlpha: 0.65,
        bgHeaderAlpha: 0.92
    )

    public static let nordFrost = StudioTheme(
        id: .nordFrost,
        displayName: "Nord Frost",
        tagline: "Polar Slate · Sky & Indigo",
        isLightTheme: false,
        bgDarkHex: "#0b111e",
        bgCardHex: "#121c30",
        bgCardSubtleHex: "#0f182a",
        bgCardBorderHex: "#38bdf8",
        bgInputHex: "#1b2b48",
        bgHeaderHex: "#0b111e",
        textPrimaryHex: "#f0f9ff",
        textSecondaryHex: "#bae6fd",
        textMutedHex: "#628ea6",
        accentPrimaryHex: "#38bdf8",
        accentSecondaryHex: "#6366f1",
        accentPinkHex: "#2dd4bf",
        accentGreenHex: "#34d399",
        accentYellowHex: "#fde047",
        bgCardAlpha: 0.80,
        bgCardSubtleAlpha: 0.75,
        bgCardBorderAlpha: 0.14,
        bgInputAlpha: 0.65,
        bgHeaderAlpha: 0.92
    )

    public static let paperStudio = StudioTheme(
        id: .paperStudio,
        displayName: "Paper Studio",
        tagline: "Editorial Manga Paper · Indigo & Vermilion",
        isLightTheme: true,
        bgDarkHex: "#f6f5f0",
        bgCardHex: "#ffffff",
        bgCardSubtleHex: "#f1efe8",
        bgCardBorderHex: "#000000",
        bgInputHex: "#ffffff",
        bgHeaderHex: "#f6f5f0",
        textPrimaryHex: "#1e293b",
        textSecondaryHex: "#475569",
        textMutedHex: "#64748b",
        accentPrimaryHex: "#4f46e5",
        accentSecondaryHex: "#ea580c",
        accentPinkHex: "#d946ef",
        accentGreenHex: "#059669",
        accentYellowHex: "#d97706",
        bgCardAlpha: 0.92,
        bgCardSubtleAlpha: 1.0,
        bgCardBorderAlpha: 0.08,
        bgInputAlpha: 1.0,
        bgHeaderAlpha: 0.94
    )

    public static let allThemes: [StudioTheme] = StudioThemeID.allCases.map(\.theme)
}

public extension Color {
    static func parseStudioHex(_ hex: String) -> (red: Double, green: Double, blue: Double)? {
        let cleaned = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        guard cleaned.count == 3 || cleaned.count == 6,
              cleaned.allSatisfy({ $0.isHexDigit }) else {
            return nil
        }
        var int: UInt64 = 0
        Scanner(string: cleaned).scanHexInt64(&int)
        let r, g, b: UInt64
        if cleaned.count == 3 {
            r = ((int >> 8) & 0xF) * 17
            g = ((int >> 4) & 0xF) * 17
            b = (int & 0xF) * 17
        } else {
            r = (int >> 16) & 0xFF
            g = (int >> 8) & 0xFF
            b = int & 0xFF
        }
        return (Double(r) / 255.0, Double(g) / 255.0, Double(b) / 255.0)
    }

    init(studioHex hex: String, alpha: Double = 1.0) {
        let rgb = Self.parseStudioHex(hex) ?? (0, 0, 0)
        self.init(
            .sRGB,
            red: rgb.red,
            green: rgb.green,
            blue: rgb.blue,
            opacity: alpha
        )
    }

    func toStudioHex() -> String {
        let nsColor = NSColor(self).usingColorSpace(.sRGB) ?? NSColor.black
        let r = Int((min(1, max(0, nsColor.redComponent)) * 255.0).rounded())
        let g = Int((min(1, max(0, nsColor.greenComponent)) * 255.0).rounded())
        let b = Int((min(1, max(0, nsColor.blueComponent)) * 255.0).rounded())
        return String(format: "#%02X%02X%02X", r, g, b)
    }
}

@MainActor
public final class StudioWindowZoomManager {
    public static let shared = StudioWindowZoomManager()
    private var savedRestoreFrames: [ObjectIdentifier: NSRect] = [:]

    private init() {}

    public static func isFrameFillingVisibleScreen(
        _ frame: NSRect,
        visibleFrame: NSRect,
        tolerance: CGFloat = 4.0
    ) -> Bool {
        abs(frame.width - visibleFrame.width) <= tolerance &&
            abs(frame.height - visibleFrame.height) <= tolerance &&
            abs(frame.origin.x - visibleFrame.origin.x) <= tolerance &&
            abs(frame.origin.y - visibleFrame.origin.y) <= tolerance
    }

    public static func defaultRestoredFrame(within visibleFrame: NSRect) -> NSRect {
        let width = min(max(round(visibleFrame.width * 0.86), 1080), max(1080, visibleFrame.width - 48))
        let height = min(max(round(visibleFrame.height * 0.86), 700), max(700, visibleFrame.height - 48))
        let originX = round(visibleFrame.origin.x + (visibleFrame.width - width) / 2.0)
        let originY = round(visibleFrame.origin.y + (visibleFrame.height - height) / 2.0)
        return NSRect(x: originX, y: originY, width: width, height: height)
    }

    public static func nextTargetFrame(
        currentFrame: NSRect,
        visibleFrame: NSRect,
        savedRestoreFrame: NSRect?
    ) -> (targetFrame: NSRect, updatedRestoreFrame: NSRect?) {
        if isFrameFillingVisibleScreen(currentFrame, visibleFrame: visibleFrame) {
            if let saved = savedRestoreFrame,
               !isFrameFillingVisibleScreen(saved, visibleFrame: visibleFrame)
            {
                return (saved, saved)
            }
            let fallback = defaultRestoredFrame(within: visibleFrame)
            return (fallback, fallback)
        } else {
            return (visibleFrame, currentFrame)
        }
    }

    public func toggleFullSize(for window: NSWindow) {
        guard !window.styleMask.contains(.fullScreen),
              window.attachedSheet == nil,
              let screen = window.screen ?? NSScreen.main
        else {
            return
        }

        let key = ObjectIdentifier(window)
        let result = Self.nextTargetFrame(
            currentFrame: window.frame,
            visibleFrame: screen.visibleFrame,
            savedRestoreFrame: savedRestoreFrames[key]
        )
        if let updatedRestore = result.updatedRestoreFrame {
            savedRestoreFrames[key] = updatedRestore
        }
        window.setFrame(result.targetFrame, display: true, animate: true)
    }
}

@MainActor
public enum StudioBrandAssets {
    private static var cachedBrandMark: NSImage?
    private static var cachedAppIcon: NSImage?
    private static var cachedMenuBarIcon: NSImage?

    private static func candidateWorkspaceRoots() -> [URL] {
        var roots: [URL] = []
        if let infoPath = Bundle.main.object(forInfoDictionaryKey: "KobeanWorkspacePath") as? String,
           !infoPath.isEmpty
        {
            roots.append(URL(fileURLWithPath: infoPath))
        }
        let cwd = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        roots.append(cwd)
        roots.append(cwd.deletingLastPathComponent())
        let sourceDir = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        roots.append(sourceDir)
        return roots
    }

    public static func brandMarkImage() -> NSImage? {
        if let cachedBrandMark {
            return cachedBrandMark
        }
        if let bundledURL = Bundle.main.url(forResource: "brand-icon", withExtension: "png"),
           let image = NSImage(contentsOf: bundledURL)
        {
            cachedBrandMark = image
            return image
        }
        for root in candidateWorkspaceRoots() {
            let candidate = root.appendingPathComponent("static/brand-icon.png")
            if FileManager.default.fileExists(atPath: candidate.path),
               let image = NSImage(contentsOf: candidate)
            {
                cachedBrandMark = image
                return image
            }
        }
        return appIconImage()
    }

    public static func appIconImage() -> NSImage? {
        if let cachedAppIcon {
            return cachedAppIcon
        }
        if let bundledURL = Bundle.main.url(forResource: "AppIcon", withExtension: "icns"),
           let image = NSImage(contentsOf: bundledURL)
        {
            cachedAppIcon = image
            return image
        }
        for root in candidateWorkspaceRoots() {
            let candidate = root.appendingPathComponent("macos/AppIcon.icns")
            if FileManager.default.fileExists(atPath: candidate.path),
               let image = NSImage(contentsOf: candidate)
            {
                cachedAppIcon = image
                return image
            }
        }
        if let mark = brandMarkImage() {
            cachedAppIcon = mark
            return mark
        }
        return NSApplication.shared.applicationIconImage
    }

    public static func menuBarIconImage() -> NSImage? {
        if let cachedMenuBarIcon {
            return cachedMenuBarIcon
        }
        guard let source = brandMarkImage() ?? appIconImage(),
              let copy = source.copy() as? NSImage
        else {
            return nil
        }
        copy.size = NSSize(width: 18, height: 18)
        copy.isTemplate = false
        cachedMenuBarIcon = copy
        return copy
    }

    public static func applyOfficialApplicationIcon() {
        if let icon = appIconImage() {
            NSApplication.shared.applicationIconImage = icon
        }
    }
}
