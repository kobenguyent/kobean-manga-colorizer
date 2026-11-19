import KobeanMangaCore
import SwiftUI

// MARK: - Unified Studio Control Sizing & Variants

enum StudioControlSize {
    case mini
    case small
    case regular
    case large

    var font: Font {
        switch self {
        case .mini: return .caption2.weight(.medium)
        case .small: return .caption.weight(.medium)
        case .regular: return .callout.weight(.medium)
        case .large: return .callout.weight(.semibold)
        }
    }

    var horizontalPadding: CGFloat {
        switch self {
        case .mini: return 7
        case .small: return 10
        case .regular: return 12
        case .large: return 16
        }
    }

    var verticalPadding: CGFloat {
        switch self {
        case .mini: return 3.5
        case .small: return 5
        case .regular: return 7
        case .large: return 9.5
        }
    }

    var cornerRadius: CGFloat {
        switch self {
        case .mini: return 5.5
        case .small: return 6.5
        case .regular: return 8
        case .large: return 9.5
        }
    }
}

enum StudioActionButtonVariant {
    case prominent
    case secondary
    case destructive
    case ghost
}

// MARK: - StudioActionButtonStyle

struct StudioActionButtonStyle: ButtonStyle {
    let variant: StudioActionButtonVariant
    let theme: StudioTheme
    var size: StudioControlSize = .regular
    var tint: Color? = nil

    func makeBody(configuration: Configuration) -> some View {
        StudioActionButtonBody(
            configuration: configuration,
            variant: variant,
            theme: theme,
            size: size,
            tint: tint
        )
    }

    private struct StudioActionButtonBody: View {
        let configuration: Configuration
        let variant: StudioActionButtonVariant
        let theme: StudioTheme
        let size: StudioControlSize
        let tint: Color?

        @Environment(\.isEnabled) private var isEnabled
        @Environment(\.accessibilityReduceMotion) private var reduceMotion
        @State private var isHovered: Bool = false

        private var effectiveHover: Bool {
            isHovered && isEnabled
        }

        private var effectivePress: Bool {
            configuration.isPressed && isEnabled
        }

        private var accentColor: Color {
            switch variant {
            case .destructive:
                return Color.red
            case .prominent, .secondary, .ghost:
                return tint ?? theme.accentPrimary
            }
        }

        private var foregroundColor: Color {
            if !isEnabled {
                return variant == .prominent
                    ? Color.white.opacity(0.55)
                    : theme.textMuted.opacity(0.55)
            }
            switch variant {
            case .prominent:
                return Color.white
            case .secondary:
                if let tint {
                    return effectiveHover ? tint : theme.textPrimary
                }
                return effectiveHover ? theme.textPrimary : theme.textPrimary.opacity(0.92)
            case .destructive:
                return effectiveHover ? Color.red : Color.red.opacity(0.88)
            case .ghost:
                return effectiveHover ? theme.textPrimary : theme.textSecondary
            }
        }

        private var currentScale: CGFloat {
            if effectivePress {
                return StudioMotion.effectiveScale(StudioMotion.buttonPressScale, reduceMotion: reduceMotion)
            }
            if effectiveHover {
                return StudioMotion.effectiveScale(StudioMotion.buttonHoverScale, reduceMotion: reduceMotion)
            }
            return 1.0
        }

        var body: some View {
            let shape = RoundedRectangle(cornerRadius: size.cornerRadius, style: .continuous)

            configuration.label
                .font(size.font)
                .foregroundStyle(foregroundColor)
                .padding(.horizontal, size.horizontalPadding)
                .padding(.vertical, size.verticalPadding)
                .background {
                    backgroundSurface(shape: shape)
                }
                .overlay {
                    borderOverlay(shape: shape)
                }
                .shadow(
                    color: shadowColor,
                    radius: shadowRadius,
                    y: shadowY
                )
                .scaleEffect(currentScale)
                .opacity(isEnabled ? 1.0 : 0.62)
                .contentShape(shape)
                .animation(StudioMotion.hoverAnimation(reduceMotion: reduceMotion), value: effectiveHover)
                .animation(StudioMotion.pressAnimation(reduceMotion: reduceMotion), value: effectivePress)
                .onHover { hovering in
                    isHovered = hovering
                }
                .onChange(of: isEnabled) { _, enabled in
                    if !enabled {
                        isHovered = false
                    }
                }
                .onDisappear {
                    isHovered = false
                }
        }

        @ViewBuilder
        private func backgroundSurface(shape: RoundedRectangle) -> some View {
            switch variant {
            case .prominent:
                ZStack {
                    shape.fill(
                        LinearGradient(
                            colors: [
                                accentColor.opacity(effectiveHover ? 1.0 : 0.94),
                                accentColor.opacity(effectiveHover ? 0.86 : 0.78),
                            ],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                    shape.fill(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(effectiveHover ? 0.24 : 0.12),
                                Color.clear,
                            ],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                    if effectivePress {
                        shape.fill(Color.black.opacity(0.14))
                    }
                }

            case .secondary:
                ZStack {
                    shape.fill(theme.bgInput)
                    if effectiveHover {
                        shape.fill(
                            LinearGradient(
                                colors: [
                                    (tint ?? theme.accentPrimary).opacity(theme.isLightTheme ? 0.08 : 0.14),
                                    theme.hoverFillOverlay,
                                ],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                        shape.fill(
                            LinearGradient(
                                colors: [theme.hoverTopSheen, Color.clear],
                                startPoint: .top,
                                endPoint: .center
                            )
                        )
                    }
                    if effectivePress {
                        shape.fill(theme.pressFillOverlay)
                    }
                }

            case .destructive:
                ZStack {
                    shape.fill(Color.red.opacity(effectiveHover ? 0.18 : 0.08))
                    if effectivePress {
                        shape.fill(Color.red.opacity(0.12))
                    }
                }

            case .ghost:
                ZStack {
                    if effectivePress {
                        shape.fill(theme.pressFillOverlay)
                    } else if effectiveHover {
                        shape.fill(theme.hoverFillOverlay)
                    }
                }
            }
        }

        @ViewBuilder
        private func borderOverlay(shape: RoundedRectangle) -> some View {
            switch variant {
            case .prominent:
                shape.strokeBorder(
                    LinearGradient(
                        colors: [
                            Color.white.opacity(effectiveHover ? 0.36 : 0.20),
                            accentColor.opacity(0.45),
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    ),
                    lineWidth: 0.85
                )

            case .secondary:
                shape.strokeBorder(
                    effectiveHover
                        ? accentColor.opacity(theme.isLightTheme ? 0.50 : 0.58)
                        : theme.bgCardBorder,
                    lineWidth: effectiveHover ? 1.0 : 0.85
                )

            case .destructive:
                shape.strokeBorder(
                    Color.red.opacity(effectiveHover ? 0.65 : 0.30),
                    lineWidth: 0.85
                )

            case .ghost:
                shape.strokeBorder(
                    effectiveHover ? theme.bgCardBorder.opacity(0.85) : Color.clear,
                    lineWidth: 0.75
                )
            }
        }

        private var shadowColor: Color {
            guard isEnabled else { return .clear }
            switch variant {
            case .prominent:
                return accentColor.opacity(effectiveHover ? (theme.isLightTheme ? 0.30 : 0.42) : 0.16)
            case .secondary:
                return effectiveHover
                    ? (tint ?? theme.accentPrimary).opacity(theme.isLightTheme ? 0.12 : 0.18)
                    : Color.black.opacity(theme.isLightTheme ? 0.04 : 0.14)
            case .destructive:
                return effectiveHover ? Color.red.opacity(0.22) : .clear
            case .ghost:
                return .clear
            }
        }

        private var shadowRadius: CGFloat {
            switch variant {
            case .prominent: return effectiveHover ? 8 : 3
            case .secondary: return effectiveHover ? 6 : 2
            case .destructive: return effectiveHover ? 6 : 0
            case .ghost: return 0
            }
        }

        private var shadowY: CGFloat {
            effectiveHover && !effectivePress ? 2 : 1
        }
    }
}

extension View {
    func studioButtonStyle(
        _ variant: StudioActionButtonVariant,
        theme: StudioTheme,
        size: StudioControlSize = .regular,
        tint: Color? = nil
    ) -> some View {
        buttonStyle(StudioActionButtonStyle(variant: variant, theme: theme, size: size, tint: tint))
    }
}

// MARK: - StudioInlineIconButtonStyle (compact plain icons: xmark, trash, pin, chevrons, +/-)

struct StudioInlineIconButtonStyle: ButtonStyle {
    let theme: StudioTheme
    var tint: Color? = nil
    var isDestructive: Bool = false
    var cornerRadius: CGFloat = 5.5
    var paddingHorizontal: CGFloat = 5
    var paddingVertical: CGFloat = 4

    func makeBody(configuration: Configuration) -> some View {
        InlineIconBody(
            configuration: configuration,
            theme: theme,
            tint: tint,
            isDestructive: isDestructive,
            cornerRadius: cornerRadius,
            paddingHorizontal: paddingHorizontal,
            paddingVertical: paddingVertical
        )
    }

    private struct InlineIconBody: View {
        let configuration: Configuration
        let theme: StudioTheme
        let tint: Color?
        let isDestructive: Bool
        let cornerRadius: CGFloat
        let paddingHorizontal: CGFloat
        let paddingVertical: CGFloat

        @Environment(\.isEnabled) private var isEnabled
        @Environment(\.accessibilityReduceMotion) private var reduceMotion
        @State private var isHovered: Bool = false

        private var effectiveHover: Bool { isHovered && isEnabled }
        private var effectivePress: Bool { configuration.isPressed && isEnabled }

        private var hoverForeground: Color {
            if isDestructive { return .red }
            return tint ?? theme.textPrimary
        }

        private var scale: CGFloat {
            if effectivePress {
                return StudioMotion.effectiveScale(StudioMotion.iconPressScale, reduceMotion: reduceMotion)
            }
            if effectiveHover {
                return StudioMotion.effectiveScale(StudioMotion.iconHoverScale, reduceMotion: reduceMotion)
            }
            return 1.0
        }

        var body: some View {
            let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
            configuration.label
                .foregroundStyle(
                    !isEnabled
                        ? theme.textMuted.opacity(0.45)
                        : (effectiveHover ? hoverForeground : (tint ?? theme.textSecondary))
                )
                .padding(.horizontal, paddingHorizontal)
                .padding(.vertical, paddingVertical)
                .background {
                    if effectivePress {
                        shape.fill(isDestructive ? Color.red.opacity(0.22) : theme.pressFillOverlay)
                    } else if effectiveHover {
                        shape.fill(isDestructive ? Color.red.opacity(0.14) : theme.hoverFillOverlay)
                    }
                }
                .scaleEffect(scale)
                .contentShape(shape)
                .animation(StudioMotion.hoverAnimation(reduceMotion: reduceMotion), value: effectiveHover)
                .animation(StudioMotion.pressAnimation(reduceMotion: reduceMotion), value: effectivePress)
                .onHover { hovering in
                    isHovered = hovering
                }
                .onChange(of: isEnabled) { _, enabled in
                    if !enabled { isHovered = false }
                }
                .onDisappear {
                    isHovered = false
                }
        }
    }
}

// MARK: - StudioDropdownPicker (Native Menu-backed Dropdown with Smooth Hover)

struct StudioDropdownOption<Value: Hashable>: Identifiable {
    let value: Value
    let title: String
    let systemImage: String?

    var id: Value { value }

    init(value: Value, title: String, systemImage: String? = nil) {
        self.value = value
        self.title = title
        self.systemImage = systemImage
    }
}

struct StudioDropdownPicker<Value: Hashable>: View {
    @Binding var selection: Value
    let options: [StudioDropdownOption<Value>]
    let theme: StudioTheme
    var size: StudioControlSize = .regular
    var placeholder: String = "Select…"

    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var isHovered: Bool = false

    private var selectedOption: StudioDropdownOption<Value>? {
        options.first(where: { $0.value == selection })
    }

    private var effectiveHover: Bool {
        isHovered && isEnabled
    }

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: size.cornerRadius, style: .continuous)

        Menu {
            ForEach(options) { option in
                Button {
                    selection = option.value
                } label: {
                    HStack {
                        if let icon = option.systemImage {
                            Image(systemName: icon)
                        }
                        Text(option.title)
                        if option.value == selection {
                            Image(systemName: "checkmark")
                        }
                    }
                }
            }
        } label: {
            HStack(spacing: 6) {
                if let icon = selectedOption?.systemImage {
                    Image(systemName: icon)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(effectiveHover ? theme.accentPrimary : theme.textSecondary)
                }

                Text(selectedOption?.title ?? placeholder)
                    .font(size == .small ? .caption.weight(.medium) : .callout.weight(.medium))
                    .foregroundStyle(isEnabled ? theme.textPrimary : theme.textMuted)
                    .lineLimit(1)
                    .truncationMode(.tail)

                Spacer(minLength: 4)

                Image(systemName: "chevron.up.chevron.down")
                    .font(.system(size: size == .small ? 8.5 : 9.5, weight: .semibold))
                    .foregroundStyle(effectiveHover ? theme.accentPrimary : theme.textMuted)
                    .offset(
                        y: effectiveHover
                            ? StudioMotion.effectiveOffset(StudioMotion.dropdownChevronHoverOffset, reduceMotion: reduceMotion)
                            : 0
                    )
            }
            .padding(.horizontal, size == .small ? 9 : 10)
            .padding(.vertical, size == .small ? 5 : 6.5)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background {
                ZStack {
                    shape.fill(theme.bgInput)
                    if effectiveHover {
                        shape.fill(theme.hoverFillOverlay)
                        shape.fill(
                            LinearGradient(
                                colors: [theme.hoverTopSheen, Color.clear],
                                startPoint: .top,
                                endPoint: .center
                            )
                        )
                    }
                }
            }
            .overlay(
                shape.strokeBorder(
                    effectiveHover ? theme.hoverBorderAccent : theme.bgCardBorder,
                    lineWidth: effectiveHover ? 1.0 : 0.85
                )
            )
            .shadow(
                color: effectiveHover ? theme.hoverGlowColor.opacity(0.55) : .clear,
                radius: effectiveHover ? 6 : 0,
                y: effectiveHover ? 1 : 0
            )
            .contentShape(shape)
        }
        .menuStyle(.button)
        .buttonStyle(.plain)
        .menuIndicator(.hidden)
        .opacity(isEnabled ? 1.0 : 0.6)
        .animation(StudioMotion.dropdownAnimation(reduceMotion: reduceMotion), value: effectiveHover)
        .onHover { hovering in
            isHovered = hovering
        }
        .onChange(of: isEnabled) { _, enabled in
            if !enabled { isHovered = false }
        }
        .onDisappear {
            isHovered = false
        }
    }
}

// MARK: - StudioHoverMenuTrigger (Custom Menu Triggers: Theme Switcher, Zoom %)

struct StudioHoverMenuTrigger<Content: View>: View {
    let theme: StudioTheme
    var cornerRadius: CGFloat = 6.5
    var showChrome: Bool = true
    @ViewBuilder let content: (_ isHovered: Bool) -> Content

    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var isHovered: Bool = false

    private var effectiveHover: Bool { isHovered && isEnabled }

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        content(effectiveHover)
            .background {
                if showChrome {
                    ZStack {
                        shape.fill(theme.bgInput)
                        if effectiveHover {
                            shape.fill(theme.hoverFillOverlay)
                        }
                    }
                } else if effectiveHover {
                    shape.fill(theme.hoverFillOverlay)
                }
            }
            .overlay {
                if showChrome {
                    shape.strokeBorder(
                        effectiveHover ? theme.hoverBorderAccent : theme.bgCardBorder,
                        lineWidth: effectiveHover ? 0.95 : 0.75
                    )
                }
            }
            .shadow(
                color: showChrome && effectiveHover ? theme.hoverGlowColor.opacity(0.45) : .clear,
                radius: effectiveHover ? 5 : 0,
                y: effectiveHover ? 1 : 0
            )
            .scaleEffect(
                effectiveHover
                    ? StudioMotion.effectiveScale(StudioMotion.buttonHoverScale, reduceMotion: reduceMotion)
                    : 1.0
            )
            .contentShape(shape)
            .animation(StudioMotion.dropdownAnimation(reduceMotion: reduceMotion), value: effectiveHover)
            .onHover { hovering in
                isHovered = hovering
            }
            .onChange(of: isEnabled) { _, enabled in
                if !enabled { isHovered = false }
            }
            .onDisappear {
                isHovered = false
            }
    }
}

// MARK: - Reusable Row & Swatch Hover Modifiers

struct StudioHoverRowModifier: ViewModifier {
    let theme: StudioTheme
    var cornerRadius: CGFloat = 8
    var isSelected: Bool = false
    var showIdleBorder: Bool = false
    var scaleOnHover: Bool = false

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var isHovered: Bool = false

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        content
            .background {
                if isSelected {
                    shape.fill(theme.accentPrimary.opacity(0.14))
                } else if isHovered {
                    shape.fill(theme.hoverFillOverlay)
                }
            }
            .overlay(
                shape.strokeBorder(
                    isSelected
                        ? theme.accentPrimary.opacity(0.65)
                        : (isHovered ? theme.hoverBorderAccent.opacity(0.75) : (showIdleBorder ? theme.bgCardBorder : Color.clear)),
                    lineWidth: isSelected ? 1.15 : 0.85
                )
            )
            .scaleEffect(
                scaleOnHover && isHovered
                    ? StudioMotion.effectiveScale(StudioMotion.cardHoverScale, reduceMotion: reduceMotion)
                    : 1.0
            )
            .contentShape(shape)
            .animation(StudioMotion.hoverAnimation(reduceMotion: reduceMotion), value: isHovered)
            .onHover { hovering in
                isHovered = hovering
            }
            .onDisappear {
                isHovered = false
            }
    }
}

extension View {
    func studioHoverRow(
        theme: StudioTheme,
        cornerRadius: CGFloat = 8,
        isSelected: Bool = false,
        showIdleBorder: Bool = false,
        scaleOnHover: Bool = false
    ) -> some View {
        modifier(
            StudioHoverRowModifier(
                theme: theme,
                cornerRadius: cornerRadius,
                isSelected: isSelected,
                showIdleBorder: showIdleBorder,
                scaleOnHover: scaleOnHover
            )
        )
    }
}
