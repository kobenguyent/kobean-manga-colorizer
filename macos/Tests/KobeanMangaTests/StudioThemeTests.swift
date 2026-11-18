import XCTest
import SwiftUI
@testable import KobeanMangaCore

final class StudioThemeTests: XCTestCase {
    func testAllSevenThemesPresentWithCorrectColorSchemes() {
        XCTAssertEqual(StudioThemeID.allCases.count, 11)

        let darkThemes: [StudioThemeID] = [
            .vscodeDarkModern,
            .pycharmDarcula,
            .cyberNeon,
            .mangaInk,
            .shonenSunrise,
            .sakuraTwilight,
            .emeraldAlchemist,
            .nordFrost
        ]

        for id in darkThemes {
            let theme = id.theme
            XCTAssertFalse(theme.isLightTheme, "\(id.rawValue) should be a dark theme")
            XCTAssertEqual(theme.preferredColorScheme, .dark)
            XCTAssertFalse(theme.displayName.isEmpty)
        }

        let lightThemes: [StudioThemeID] = [
            .vscodeLightModern,
            .pycharmLight,
            .paperStudio
        ]

        for id in lightThemes {
            let theme = id.theme
            XCTAssertTrue(theme.isLightTheme, "\(id.rawValue) should be a light theme")
            XCTAssertEqual(theme.preferredColorScheme, .light)
            XCTAssertFalse(theme.displayName.isEmpty)
        }
    }

    func testThemeHexTokensMatchProductSpec() {
        let cyber = StudioTheme.cyberNeon
        XCTAssertEqual(cyber.id.rawValue, "cyber-neon")
        XCTAssertEqual(cyber.bgDarkHex.lowercased(), "#090d16")
        XCTAssertEqual(cyber.accentPrimaryHex.lowercased(), "#06b6d4")
        XCTAssertEqual(cyber.accentSecondaryHex.lowercased(), "#8b5cf6")

        let paper = StudioTheme.paperStudio
        XCTAssertEqual(paper.id.rawValue, "paper-studio")
        XCTAssertEqual(paper.bgDarkHex.lowercased(), "#f6f5f0")
        XCTAssertEqual(paper.textPrimaryHex.lowercased(), "#1e293b")
        XCTAssertEqual(paper.accentPrimaryHex.lowercased(), "#4f46e5")
        XCTAssertEqual(paper.accentSecondaryHex.lowercased(), "#ea580c")
    }

    func testAllSemanticColorsAreAccessible() {
        for id in StudioThemeID.allCases {
            let t = id.theme
            _ = t.bgDark
            _ = t.bgCard
            _ = t.bgCardSubtle
            _ = t.bgCardBorder
            _ = t.bgInput
            _ = t.bgHeader
            _ = t.textPrimary
            _ = t.textSecondary
            _ = t.textMuted
            _ = t.accentPrimary
            _ = t.accentSecondary
            _ = t.accentPink
            _ = t.accentGreen
            _ = t.accentYellow
        }
    }

    func testColorHexRoundTripConversion() {
        let indigo = Color(studioHex: "#4f46e5")
        XCTAssertEqual(indigo.toStudioHex(), "#4F46E5")

        let shortHex = Color(studioHex: "0fc")
        XCTAssertEqual(shortHex.toStudioHex(), "#00FFCC")

        XCTAssertNil(Color.parseStudioHex("not-a-hex"))
        XCTAssertNotNil(Color.parseStudioHex("#10B981"))
    }

    @MainActor
    func testWindowZoomManagerTogglesFullSizeAndRestoresPreviousFrame() {
        let visibleFrame = NSRect(x: 0, y: 25, width: 1512, height: 915)
        let partialFrame = NSRect(x: 0, y: 25, width: 1460, height: 915)

        XCTAssertFalse(
            StudioWindowZoomManager.isFrameFillingVisibleScreen(
                partialFrame,
                visibleFrame: visibleFrame
            ),
            "1460x915 window on 1512x915 screen must not be considered full-size"
        )

        let zoomStep = StudioWindowZoomManager.nextTargetFrame(
            currentFrame: partialFrame,
            visibleFrame: visibleFrame,
            savedRestoreFrame: nil
        )
        XCTAssertEqual(zoomStep.targetFrame, visibleFrame)
        XCTAssertEqual(zoomStep.updatedRestoreFrame, partialFrame)

        XCTAssertTrue(
            StudioWindowZoomManager.isFrameFillingVisibleScreen(
                zoomStep.targetFrame,
                visibleFrame: visibleFrame
            )
        )

        let restoreStep = StudioWindowZoomManager.nextTargetFrame(
            currentFrame: zoomStep.targetFrame,
            visibleFrame: visibleFrame,
            savedRestoreFrame: zoomStep.updatedRestoreFrame
        )
        XCTAssertEqual(restoreStep.targetFrame, partialFrame)

        // When starting already at full-size with no prior restore frame, double-click restores a centered frame
        let fallbackStep = StudioWindowZoomManager.nextTargetFrame(
            currentFrame: visibleFrame,
            visibleFrame: visibleFrame,
            savedRestoreFrame: nil
        )
        XCTAssertLessThan(fallbackStep.targetFrame.width, visibleFrame.width)
        XCTAssertLessThan(fallbackStep.targetFrame.height, visibleFrame.height)
    }

    @MainActor
    func testOfficialBrandAssetsLoadValidImages() {
        let mark = StudioBrandAssets.brandMarkImage()
        XCTAssertNotNil(mark)
        XCTAssertGreaterThan(mark?.size.width ?? 0, 0)

        let appIcon = StudioBrandAssets.appIconImage()
        XCTAssertNotNil(appIcon)
        XCTAssertGreaterThan(appIcon?.size.width ?? 0, 0)

        let menuIcon = StudioBrandAssets.menuBarIconImage()
        XCTAssertNotNil(menuIcon)
        XCTAssertEqual(menuIcon?.size.width, 18)
        XCTAssertEqual(menuIcon?.size.height, 18)
    }
}
