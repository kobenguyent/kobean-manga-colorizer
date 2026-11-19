import SwiftUI

/// Centralized motion curves, scale constants, and reduced-motion helpers
/// shared across all interactive macOS Studio controls.
public enum StudioMotion: Sendable {
    // MARK: - Scale Constants

    public static let buttonHoverScale: CGFloat = 1.012
    public static let buttonPressScale: CGFloat = 0.975
    public static let iconHoverScale: CGFloat = 1.05
    public static let iconPressScale: CGFloat = 0.93
    public static let cardHoverScale: CGFloat = 1.015
    public static let tileHoverScale: CGFloat = 1.022
    public static let swatchHoverScale: CGFloat = 1.06
    public static let dropdownPressScale: CGFloat = 0.985

    // MARK: - Offsets

    public static let dropdownChevronHoverOffset: CGFloat = 1.0
    public static let rowChevronHoverOffset: CGFloat = 2.0

    // MARK: - Canonical Animations

    public static let hoverSpring: Animation = .spring(response: 0.20, dampingFraction: 0.80)
    public static let pressSpring: Animation = .spring(response: 0.16, dampingFraction: 0.72)
    public static let dropdownSpring: Animation = .spring(response: 0.22, dampingFraction: 0.82)
    public static let selectionSpring: Animation = .spring(response: 0.24, dampingFraction: 0.82)
    public static let reducedMotionFade: Animation = .easeOut(duration: 0.12)

    // MARK: - Reduced-Motion Helpers

    public static func hoverAnimation(reduceMotion: Bool) -> Animation {
        reduceMotion ? reducedMotionFade : hoverSpring
    }

    public static func pressAnimation(reduceMotion: Bool) -> Animation {
        reduceMotion ? reducedMotionFade : pressSpring
    }

    public static func dropdownAnimation(reduceMotion: Bool) -> Animation {
        reduceMotion ? reducedMotionFade : dropdownSpring
    }

    public static func selectionAnimation(reduceMotion: Bool) -> Animation {
        reduceMotion ? reducedMotionFade : selectionSpring
    }

    /// Returns `1.0` when `reduceMotion` is enabled so scale animations cleanly degrade
    /// to pure color/border/opacity transitions without motion.
    public static func effectiveScale(_ target: CGFloat, reduceMotion: Bool) -> CGFloat {
        reduceMotion ? 1.0 : target
    }

    /// Returns `0` when `reduceMotion` is enabled so directional nudges are suppressed.
    public static func effectiveOffset(_ target: CGFloat, reduceMotion: Bool) -> CGFloat {
        reduceMotion ? 0 : target
    }
}

public extension StudioTheme {
    /// Subtle surface lift applied on hover over neutral cards, rows, and secondary controls.
    var hoverFillOverlay: Color {
        isLightTheme ? Color.black.opacity(0.045) : Color.white.opacity(0.065)
    }

    /// Slightly stronger overlay applied while a control is actively pressed.
    var pressFillOverlay: Color {
        isLightTheme ? Color.black.opacity(0.085) : Color.white.opacity(0.11)
    }

    /// Top specular sheen gradient opacity for hovered surfaces.
    var hoverTopSheen: Color {
        isLightTheme ? Color.white.opacity(0.55) : Color.white.opacity(0.12)
    }

    /// Accent-tinted border color when hovering interactive controls.
    var hoverBorderAccent: Color {
        accentPrimary.opacity(isLightTheme ? 0.55 : 0.62)
    }

    /// Soft accent glow shadow for prominent CTAs and hovered dropdowns.
    var hoverGlowColor: Color {
        accentPrimary.opacity(isLightTheme ? 0.22 : 0.32)
    }
}
