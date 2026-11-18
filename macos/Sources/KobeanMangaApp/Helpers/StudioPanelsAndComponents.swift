import AppKit
import Foundation
import KobeanMangaCore
import SwiftUI
import UniformTypeIdentifiers

@MainActor
enum StudioFilePanels {
    static let supportedFileTypes: [UTType] = {
        var types: [UTType] = [.pdf, .epub, .zip, .png, .jpeg, .webP, .bmp, .gif, .tiff]
        if let cbz = UTType(filenameExtension: "cbz") {
            types.append(cbz)
        }
        return types
    }()

    static func pickFiles() -> [URL] {
        let panel = NSOpenPanel()
        panel.title = "Import Manga Files"
        panel.prompt = "Import"
        panel.allowsMultipleSelection = true
        panel.canChooseDirectories = false
        panel.canChooseFiles = true
        panel.allowedContentTypes = supportedFileTypes
        return panel.runModal() == .OK ? panel.urls : []
    }

    static func pickFolder() -> URL? {
        let panel = NSOpenPanel()
        panel.title = "Import Manga Directory"
        panel.prompt = "Select Folder"
        panel.allowsMultipleSelection = false
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        return panel.runModal() == .OK ? panel.url : nil
    }

    static func pickSaveDestination(suggestedFilename: String) -> URL? {
        let panel = NSSavePanel()
        panel.title = "Save Exported Manga"
        panel.nameFieldStringValue = suggestedFilename
        panel.canCreateDirectories = true
        return panel.runModal() == .OK ? panel.url : nil
    }
}

struct StudioRemoteImageView: View {
    let url: URL?
    let placeholderText: String
    let theme: StudioTheme
    var contentMode: ContentMode = .fit
    var maxPixelDimension: CGFloat? = nil

    @State private var loadedImage: NSImage?
    @State private var isLoading: Bool = false
    @State private var loadFailed: Bool = false

    var body: some View {
        ZStack {
            if let image = loadedImage {
                Image(nsImage: image)
                    .resizable()
                    .interpolation(.high)
                    .aspectRatio(contentMode: contentMode)
                    .transition(.opacity)
            } else if isLoading {
                VStack(spacing: 8) {
                    ProgressView()
                        .controlSize(.small)
                    Text("Loading...")
                        .font(.caption2)
                        .foregroundStyle(theme.textMuted)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .transition(.opacity)
            } else {
                VStack(spacing: 6) {
                    Image(systemName: loadFailed ? "exclamationmark.triangle" : "photo")
                        .font(.title3)
                        .foregroundStyle(loadFailed ? theme.accentYellow : theme.textMuted)
                    Text(loadFailed ? "Preview unavailable" : placeholderText)
                        .font(.caption)
                        .foregroundStyle(theme.textMuted)
                        .multilineTextAlignment(.center)
                }
                .padding(12)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .transition(.opacity)
            }
        }
        .animation(.easeOut(duration: 0.16), value: loadedImage != nil)
        .task(id: taskIdentifier) {
            await loadImageIfNeeded()
        }
    }

    private var taskIdentifier: String {
        guard let url else { return "nil" }
        return StudioImageCache.cacheKey(for: url, maxPixelDimension: maxPixelDimension)
    }

    private func loadImageIfNeeded() async {
        guard let url else {
            loadedImage = nil
            isLoading = false
            loadFailed = false
            return
        }

        if let cached = StudioImageCache.shared.image(for: url, maxPixelDimension: maxPixelDimension) {
            loadedImage = cached
            isLoading = false
            loadFailed = false
            return
        }

        isLoading = true
        loadFailed = false
        do {
            let decoded = try await StudioImageCache.shared.loadImage(
                from: url,
                maxPixelDimension: maxPixelDimension
            )
            if !Task.isCancelled {
                loadedImage = decoded
                loadFailed = false
            }
        } catch {
            if !Task.isCancelled {
                loadFailed = true
            }
        }
        isLoading = false
    }
}

struct StudioBadgePill: View {
    let text: String
    var systemImage: String? = nil
    let foreground: Color
    let background: Color
    let border: Color

    var body: some View {
        HStack(spacing: 4) {
            if let systemImage {
                Image(systemName: systemImage)
                    .font(.caption2.weight(.semibold))
            }
            Text(text)
                .font(.caption2.weight(.semibold))
                .monospacedDigit()
                .lineLimit(1)
        }
        .foregroundStyle(foreground)
        .padding(.horizontal, 9)
        .padding(.vertical, 3.5)
        .background {
            Capsule()
                .fill(.ultraThinMaterial)
                .overlay(Capsule().fill(background))
                .overlay(
                    Capsule()
                        .fill(
                            LinearGradient(
                                colors: [Color.white.opacity(0.14), Color.clear],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                )
        }
        .overlay(
            Capsule()
                .strokeBorder(
                    LinearGradient(
                        colors: [border.opacity(0.95), border.opacity(0.45)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    lineWidth: 0.85
                )
        )
        .shadow(color: .black.opacity(0.16), radius: 4, y: 1)
    }
}

struct StudioCardSurface<Content: View>: View {
    let theme: StudioTheme
    var padding: CGFloat = 12
    @ViewBuilder let content: () -> Content

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 11, style: .continuous)
        content()
            .padding(padding)
            .background {
                ZStack {
                    shape.fill(theme.bgCard)
                    shape.fill(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(theme.isLightTheme ? 0.55 : 0.045),
                                Color.white.opacity(theme.isLightTheme ? 0.12 : 0.01),
                                Color.clear,
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        )
                    )
                }
            }
            .overlay(
                shape.strokeBorder(
                    LinearGradient(
                        colors: [
                            theme.isLightTheme
                                ? Color.white.opacity(0.85)
                                : Color.white.opacity(0.14),
                            theme.bgCardBorder,
                            theme.bgCardBorder.opacity(0.75),
                        ],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    ),
                    lineWidth: 0.85
                )
            )
            .shadow(
                color: Color.black.opacity(theme.isLightTheme ? 0.05 : 0.22),
                radius: 8,
                y: 3
            )
    }
}

struct StudioHairline: View {
    let theme: StudioTheme

    var body: some View {
        Rectangle()
            .fill(theme.bgCardBorder)
            .frame(height: 1)
    }
}

struct StudioVerticalHairline: View {
    let theme: StudioTheme
    var height: CGFloat? = 18

    var body: some View {
        Rectangle()
            .fill(theme.bgCardBorder)
            .frame(width: 1, height: height)
    }
}

struct StudioSegmentItem<Value: Hashable>: Identifiable {
    let value: Value
    let title: String
    let icon: String?

    var id: Value { value }

    init(value: Value, title: String, icon: String? = nil) {
        self.value = value
        self.title = title
        self.icon = icon
    }
}

struct StudioSegmentedControl<Value: Hashable>: View {
    let items: [StudioSegmentItem<Value>]
    @Binding var selection: Value
    let theme: StudioTheme
    var fullWidth: Bool = false

    @Namespace private var segmentNamespace
    @State private var hoveredValue: Value?

    init(
        items: [(value: Value, title: String, icon: String?)],
        selection: Binding<Value>,
        theme: StudioTheme,
        fullWidth: Bool = false
    ) {
        self.items = items.map { StudioSegmentItem(value: $0.value, title: $0.title, icon: $0.icon) }
        self._selection = selection
        self.theme = theme
        self.fullWidth = fullWidth
    }

    var body: some View {
        HStack(spacing: 3) {
            ForEach(items) { item in
                let isSelected = selection == item.value
                let isHovered = !isSelected && hoveredValue == item.value
                Button {
                    withAnimation(.spring(response: 0.22, dampingFraction: 0.82)) {
                        selection = item.value
                    }
                } label: {
                    HStack(spacing: 5) {
                        if let icon = item.icon {
                            Image(systemName: icon)
                                .font(.caption2.weight(.semibold))
                        }
                        Text(item.title)
                            .font(.caption.weight(isSelected ? .semibold : .medium))
                            .lineLimit(1)
                    }
                    .foregroundStyle(
                        isSelected
                            ? (theme.isLightTheme ? theme.accentPrimary : theme.textPrimary)
                            : (isHovered ? theme.textPrimary : theme.textSecondary)
                    )
                    .padding(.horizontal, 10)
                    .padding(.vertical, 5)
                    .frame(maxWidth: fullWidth ? .infinity : nil)
                    .background {
                        if isSelected {
                            let pill = RoundedRectangle(cornerRadius: 6.5, style: .continuous)
                            pill
                                .fill(
                                    LinearGradient(
                                        colors: [
                                            theme.accentPrimary.opacity(theme.isLightTheme ? 0.20 : 0.28),
                                            theme.accentPrimary.opacity(theme.isLightTheme ? 0.10 : 0.14),
                                        ],
                                        startPoint: .top,
                                        endPoint: .bottom
                                    )
                                )
                                .overlay(
                                    pill.fill(
                                        LinearGradient(
                                            colors: [
                                                Color.white.opacity(theme.isLightTheme ? 0.45 : 0.14),
                                                Color.clear,
                                            ],
                                            startPoint: .top,
                                            endPoint: .bottom
                                        )
                                    )
                                )
                                .overlay(
                                    pill.strokeBorder(
                                        LinearGradient(
                                            colors: [
                                                theme.accentPrimary.opacity(0.65),
                                                theme.accentPrimary.opacity(0.28),
                                            ],
                                            startPoint: .topLeading,
                                            endPoint: .bottomTrailing
                                        ),
                                        lineWidth: 0.85
                                    )
                                )
                                .shadow(
                                    color: theme.accentPrimary.opacity(theme.isLightTheme ? 0.14 : 0.24),
                                    radius: 5,
                                    y: 1
                                )
                                .matchedGeometryEffect(id: "activeSegmentPill", in: segmentNamespace)
                        } else if isHovered {
                            RoundedRectangle(cornerRadius: 6.5, style: .continuous)
                                .fill(theme.textPrimary.opacity(0.06))
                                .transition(.opacity)
                        }
                    }
                }
                .buttonStyle(.plain)
                .contentShape(RoundedRectangle(cornerRadius: 6.5, style: .continuous))
                .onHover { hovering in
                    withAnimation(.easeOut(duration: 0.14)) {
                        hoveredValue = hovering ? item.value : (hoveredValue == item.value ? nil : hoveredValue)
                    }
                }
            }
        }
        .padding(3)
        .background {
            RoundedRectangle(cornerRadius: 8.5, style: .continuous)
                .fill(theme.bgInput)
                .overlay(
                    RoundedRectangle(cornerRadius: 8.5, style: .continuous)
                        .fill(
                            LinearGradient(
                                colors: [
                                    Color.black.opacity(theme.isLightTheme ? 0.02 : 0.16),
                                    Color.clear,
                                ],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                )
        }
        .overlay(
            RoundedRectangle(cornerRadius: 8.5, style: .continuous)
                .strokeBorder(
                    LinearGradient(
                        colors: [
                            theme.bgCardBorder.opacity(0.9),
                            Color.white.opacity(theme.isLightTheme ? 0.5 : 0.08),
                        ],
                        startPoint: .top,
                        endPoint: .bottom
                    ),
                    lineWidth: 0.85
                )
        )
    }
}

struct StudioToolbarIconButton: View {
    let title: String
    let systemImage: String
    var isActive: Bool = false
    var isDisabled: Bool = false
    let theme: StudioTheme
    let action: () -> Void

    @State private var isHovered: Bool = false

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 6.5, style: .continuous)
        Button(action: action) {
            Image(systemName: systemImage)
                .font(.system(size: 12, weight: .medium))
                .foregroundStyle(
                    isDisabled
                        ? theme.textMuted.opacity(0.45)
                        : (isActive ? theme.accentPrimary : (isHovered ? theme.textPrimary : theme.textSecondary))
                )
                .frame(width: 26, height: 24)
                .background {
                    if isActive {
                        shape.fill(
                            LinearGradient(
                                colors: [
                                    theme.accentPrimary.opacity(0.24),
                                    theme.accentPrimary.opacity(0.12),
                                ],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                        )
                    } else if isHovered && !isDisabled {
                        shape.fill(theme.bgInput)
                    }
                }
                .overlay(
                    shape.strokeBorder(
                        isActive
                            ? theme.accentPrimary.opacity(0.48)
                            : (isHovered && !isDisabled ? theme.bgCardBorder : Color.clear),
                        lineWidth: 0.8
                    )
                )
                .scaleEffect(isHovered && !isDisabled ? 1.04 : 1.0)
                .contentShape(shape)
        }
        .buttonStyle(.plain)
        .disabled(isDisabled)
        .animation(.spring(response: 0.22, dampingFraction: 0.78), value: isHovered)
        .animation(.spring(response: 0.22, dampingFraction: 0.78), value: isActive)
        .onHover { hovering in
            isHovered = hovering
        }
        .help(title)
    }
}

struct StudioToggleRow: View {
    let title: String
    var subtitle: String? = nil
    @Binding var isOn: Bool
    let theme: StudioTheme

    var body: some View {
        HStack(alignment: .center, spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(.callout)
                    .foregroundStyle(theme.textPrimary)
                if let subtitle, !subtitle.isEmpty {
                    Text(subtitle)
                        .font(.caption2)
                        .foregroundStyle(theme.textMuted)
                }
            }
            Spacer(minLength: 8)
            Toggle("", isOn: $isOn)
                .labelsHidden()
                .toggleStyle(.switch)
                .controlSize(.small)
                .tint(theme.accentPrimary)
        }
        .contentShape(Rectangle())
    }
}

struct StudioPaneContainer<Content: View>: View {
    let theme: StudioTheme
    var background: Color? = nil
    var cornerRadius: CGFloat = 10
    @ViewBuilder let content: () -> Content

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
        content()
            .background {
                ZStack {
                    shape.fill(background ?? theme.bgHeader)
                    shape.fill(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(theme.isLightTheme ? 0.42 : 0.032),
                                Color.clear,
                            ],
                            startPoint: .top,
                            endPoint: .center
                        )
                    )
                }
            }
            .clipShape(shape)
            .overlay(
                shape
                    .strokeBorder(
                        LinearGradient(
                            colors: [
                                theme.isLightTheme
                                    ? Color.white.opacity(0.85)
                                    : Color.white.opacity(0.15),
                                theme.bgCardBorder,
                                theme.bgCardBorder.opacity(0.82),
                            ],
                            startPoint: .topLeading,
                            endPoint: .bottomTrailing
                        ),
                        lineWidth: 1
                    )
                    .allowsHitTesting(false)
            )
            .shadow(
                color: Color.black.opacity(theme.isLightTheme ? 0.05 : 0.26),
                radius: 10,
                y: 3
            )
    }
}

struct StudioFieldLabel: View {
    let title: String
    var badgeText: String? = nil
    let theme: StudioTheme

    var body: some View {
        HStack(alignment: .firstTextBaseline) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(theme.textSecondary)
                .textCase(.uppercase)
                .tracking(0.4)
            Spacer()
            if let badgeText, !badgeText.isEmpty {
                Text(badgeText)
                    .font(.caption2.weight(.semibold))
                    .monospacedDigit()
                    .foregroundStyle(theme.accentPrimary)
            }
        }
    }
}

struct StudioBrandLogoView: View {
    enum Style {
        case appIcon
        case markOnly
    }

    var size: CGFloat = 64
    var style: Style = .appIcon
    var showGlow: Bool = false
    let theme: StudioTheme

    var body: some View {
        let image: NSImage? = {
            switch style {
            case .appIcon:
                return StudioBrandAssets.appIconImage() ?? StudioBrandAssets.brandMarkImage()
            case .markOnly:
                return StudioBrandAssets.brandMarkImage() ?? StudioBrandAssets.appIconImage()
            }
        }()

        Group {
            if let image {
                Image(nsImage: image)
                    .resizable()
                    .interpolation(.high)
                    .antialiased(true)
                    .aspectRatio(contentMode: .fit)
                    .frame(width: size, height: size)
                    .shadow(
                        color: showGlow ? theme.accentPrimary.opacity(0.28) : Color.clear,
                        radius: showGlow ? 16 : 0,
                        y: showGlow ? 4 : 0
                    )
            } else {
                RoundedRectangle(cornerRadius: size * 0.225, style: .continuous)
                    .fill(theme.accentPrimary.opacity(0.18))
                    .frame(width: size, height: size)
            }
        }
        .accessibilityHidden(true)
    }
}

final class StudioHeaderInteractiveMarkerView: NSView {
    override var mouseDownCanMoveWindow: Bool { false }
}

struct StudioHeaderControlExcludeView: NSViewRepresentable {
    func makeNSView(context: Context) -> StudioHeaderInteractiveMarkerView {
        StudioHeaderInteractiveMarkerView(frame: .zero)
    }

    func updateNSView(_ nsView: StudioHeaderInteractiveMarkerView, context: Context) {}
}

extension View {
    func studioHeaderInteractiveControl() -> some View {
        background(StudioHeaderControlExcludeView())
    }
}

final class StudioHeaderSurfaceNSView: NSView {
    private var eventMonitor: Any?
    private var windowObservers: [NSObjectProtocol] = []

    override var mouseDownCanMoveWindow: Bool { true }

    override func layout() {
        super.layout()
        alignTrafficLights()
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        teardownMonitor()

        guard let window else { return }
        window.styleMask.insert(.resizable)
        window.collectionBehavior.insert(.fullScreenPrimary)
        let unbounded = NSSize(
            width: CGFloat.greatestFiniteMagnitude,
            height: CGFloat.greatestFiniteMagnitude
        )
        window.maxSize = unbounded
        window.contentMaxSize = unbounded

        alignTrafficLights()
        DispatchQueue.main.async { [weak self] in
            self?.alignTrafficLights()
        }

        let center = NotificationCenter.default
        let names: [Notification.Name] = [
            NSWindow.didResizeNotification,
            NSWindow.didEndLiveResizeNotification,
            NSWindow.didBecomeKeyNotification,
            NSWindow.didResignKeyNotification,
            NSWindow.didExitFullScreenNotification,
        ]
        for name in names {
            let token = center.addObserver(forName: name, object: window, queue: .main) {
                [weak self] _ in
                self?.alignTrafficLights()
            }
            windowObservers.append(token)
        }

        eventMonitor = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown, .leftMouseUp]) {
            [weak self] event in
            guard let self,
                  let window = self.window,
                  event.window === window,
                  !window.styleMask.contains(.fullScreen),
                  window.attachedSheet == nil
            else {
                return event
            }

            let windowPoint = event.locationInWindow
            let localPoint = self.convert(windowPoint, from: nil)
            guard self.bounds.contains(localPoint) else {
                return event
            }

            // Exclude macOS traffic light buttons
            if windowPoint.x < 76 {
                return event
            }
            for buttonType in [NSWindow.ButtonType.closeButton, .miniaturizeButton, .zoomButton] {
                if let btn = window.standardWindowButton(buttonType), !btn.isHidden {
                    let buttonPoint = btn.convert(windowPoint, from: nil)
                    if btn.bounds.insetBy(dx: -4, dy: -4).contains(buttonPoint) {
                        return event
                    }
                }
            }

            // Exclude interactive toolbar buttons and menus in the header bar
            if let rootView = window.contentView,
               Self.isPointInsideInteractiveControl(in: rootView, windowPoint: windowPoint)
            {
                return event
            }

            if event.clickCount >= 2 {
                if event.type == .leftMouseDown && event.clickCount == 2 {
                    Task { @MainActor in
                        StudioWindowZoomManager.shared.toggleFullSize(for: window)
                    }
                }
                return nil
            }

            return event
        }
    }

    override func removeFromSuperview() {
        teardownMonitor()
        super.removeFromSuperview()
    }

    deinit {
        if let monitor = eventMonitor {
            NSEvent.removeMonitor(monitor)
        }
        for token in windowObservers {
            NotificationCenter.default.removeObserver(token)
        }
    }

    private func teardownMonitor() {
        if let monitor = eventMonitor {
            NSEvent.removeMonitor(monitor)
            eventMonitor = nil
        }
        for token in windowObservers {
            NotificationCenter.default.removeObserver(token)
        }
        windowObservers.removeAll()
    }

    private func alignTrafficLights() {
        guard let window,
              !window.styleMask.contains(.fullScreen),
              self.bounds.height > 0
        else { return }

        let headerCenterInWindow = self.convert(
            NSPoint(x: self.bounds.midX, y: self.bounds.midY),
            to: nil
        )
        let startXInWindow: CGFloat = 14.0
        let spacingX: CGFloat = 20.0
        let buttons: [NSWindow.ButtonType] = [.closeButton, .miniaturizeButton, .zoomButton]

        for (index, type) in buttons.enumerated() {
            guard let btn = window.standardWindowButton(type),
                  let superview = btn.superview
            else { continue }

            let btnRectInWindow = btn.convert(btn.bounds, to: nil)
            let desiredOriginInWindow = NSPoint(
                x: startXInWindow + CGFloat(index) * spacingX,
                y: round(headerCenterInWindow.y - btnRectInWindow.height / 2.0)
            )
            let desiredOriginInSuperview = superview.convert(desiredOriginInWindow, from: nil)
            if abs(btn.frame.origin.x - desiredOriginInSuperview.x) > 0.5 ||
                abs(btn.frame.origin.y - desiredOriginInSuperview.y) > 0.5
            {
                btn.setFrameOrigin(desiredOriginInSuperview)
            }
        }
    }

    private static func isPointInsideInteractiveControl(in view: NSView, windowPoint: NSPoint) -> Bool {
        guard !view.isHidden, view.alphaValue > 0.01 else { return false }
        if view is StudioHeaderInteractiveMarkerView {
            let localPoint = view.convert(windowPoint, from: nil)
            if view.bounds.insetBy(dx: -2, dy: -2).contains(localPoint) {
                return true
            }
        }
        for subview in view.subviews {
            if isPointInsideInteractiveControl(in: subview, windowPoint: windowPoint) {
                return true
            }
        }
        return false
    }
}

struct StudioWindowHeaderSurface: NSViewRepresentable {
    func makeNSView(context: Context) -> StudioHeaderSurfaceNSView {
        StudioHeaderSurfaceNSView(frame: .zero)
    }

    func updateNSView(_ nsView: StudioHeaderSurfaceNSView, context: Context) {
        nsView.needsLayout = true
    }
}
