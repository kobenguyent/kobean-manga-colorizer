import SwiftUI
import XCTest
@testable import KobeanMangaCore

final class StudioMotionTests: XCTestCase {
    func testReducedMotionSuppressesScaleAndOffset() {
        XCTAssertEqual(
            StudioMotion.effectiveScale(StudioMotion.buttonHoverScale, reduceMotion: true),
            1.0
        )
        XCTAssertEqual(
            StudioMotion.effectiveScale(StudioMotion.buttonPressScale, reduceMotion: true),
            1.0
        )
        XCTAssertEqual(
            StudioMotion.effectiveOffset(StudioMotion.rowChevronHoverOffset, reduceMotion: true),
            0.0
        )
        XCTAssertEqual(
            StudioMotion.effectiveScale(StudioMotion.buttonHoverScale, reduceMotion: false),
            StudioMotion.buttonHoverScale
        )
        XCTAssertEqual(
            StudioMotion.effectiveOffset(StudioMotion.dropdownChevronHoverOffset, reduceMotion: false),
            StudioMotion.dropdownChevronHoverOffset
        )
    }

    func testScaleConstantsStayWithinSafeNonClippingBounds() {
        let hoverScales: [CGFloat] = [
            StudioMotion.buttonHoverScale,
            StudioMotion.iconHoverScale,
            StudioMotion.cardHoverScale,
            StudioMotion.tileHoverScale,
            StudioMotion.swatchHoverScale,
        ]
        for scale in hoverScales {
            XCTAssertGreaterThan(scale, 1.0)
            XCTAssertLessThanOrEqual(scale, 1.08)
        }

        let pressScales: [CGFloat] = [
            StudioMotion.buttonPressScale,
            StudioMotion.iconPressScale,
            StudioMotion.dropdownPressScale,
        ]
        for scale in pressScales {
            XCTAssertLessThan(scale, 1.0)
            XCTAssertGreaterThanOrEqual(scale, 0.90)
        }
    }

    func testAllThemesExposeValidHoverColorTokens() {
        XCTAssertEqual(StudioTheme.allThemes.count, 11)
        for theme in StudioTheme.allThemes {
            _ = theme.hoverFillOverlay
            _ = theme.pressFillOverlay
            _ = theme.hoverTopSheen
            _ = theme.hoverBorderAccent
            _ = theme.hoverGlowColor
        }
    }
}
