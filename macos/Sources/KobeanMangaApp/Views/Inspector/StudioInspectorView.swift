import KobeanMangaCore
import SwiftUI

struct StudioInspectorView: View {
    @Bindable var store: StudioStore

    var body: some View {
        let theme = store.currentTheme

        VStack(spacing: 0) {
            StudioSegmentedControl(
                items: [
                    (.engine, "Engine", "cpu"),
                    (.palette, "Palette", "paintpalette.fill"),
                    (.export, "Export", "square.and.arrow.up"),
                ],
                selection: $store.selectedInspectorTab,
                theme: theme,
                fullWidth: true
            )
            .padding(12)
            .background(theme.bgHeader)

            StudioHairline(theme: theme)

            ZStack(alignment: .top) {
                ScrollView {
                    VStack(spacing: 14) {
                        EngineTuningTab(store: store, theme: theme)
                    }
                    .padding(12)
                }
                .opacity(store.selectedInspectorTab == .engine ? 1 : 0)
                .scaleEffect(store.selectedInspectorTab == .engine ? 1.0 : 0.985, anchor: .top)
                .offset(y: store.selectedInspectorTab == .engine ? 0 : 4)
                .allowsHitTesting(store.selectedInspectorTab == .engine)
                .accessibilityHidden(store.selectedInspectorTab != .engine)

                ScrollView {
                    VStack(spacing: 14) {
                        PaletteSeriesTab(store: store, theme: theme)
                    }
                    .padding(12)
                }
                .opacity(store.selectedInspectorTab == .palette ? 1 : 0)
                .scaleEffect(store.selectedInspectorTab == .palette ? 1.0 : 0.985, anchor: .top)
                .offset(y: store.selectedInspectorTab == .palette ? 0 : 4)
                .allowsHitTesting(store.selectedInspectorTab == .palette)
                .accessibilityHidden(store.selectedInspectorTab != .palette)

                ScrollView {
                    VStack(spacing: 14) {
                        ExportOmnibusTab(store: store, theme: theme)
                    }
                    .padding(12)
                }
                .opacity(store.selectedInspectorTab == .export ? 1 : 0)
                .scaleEffect(store.selectedInspectorTab == .export ? 1.0 : 0.985, anchor: .top)
                .offset(y: store.selectedInspectorTab == .export ? 0 : 4)
                .allowsHitTesting(store.selectedInspectorTab == .export)
                .accessibilityHidden(store.selectedInspectorTab != .export)
            }
            .animation(.spring(response: 0.24, dampingFraction: 0.84), value: store.selectedInspectorTab)

            if store.selectedInspectorTab == .engine {
                StudioHairline(theme: theme)
                EngineActionDock(store: store, theme: theme)
                    .transition(.move(edge: .bottom).combined(with: .opacity))
            }
        }
        .animation(.spring(response: 0.24, dampingFraction: 0.84), value: store.selectedInspectorTab)
        .background(theme.bgHeader)
    }
}

// MARK: - Sticky Inspector Bottom Action Dock

private struct EngineActionDock: View {
    @Bindable var store: StudioStore
    let theme: StudioTheme

    private var hasSession: Bool {
        store.activeSession != nil
    }

    private var hasPages: Bool {
        !(store.activeSession?.pages.isEmpty ?? true)
    }

    private var primaryColorizeTitle: String {
        if !store.selectedPageIndices.isEmpty {
            return "Start Colorize Selected (\(store.selectedPageIndices.count))"
        }
        if let total = store.activeSession?.pages.count, total > 0 {
            return "Select All & Colorize (\(total))"
        }
        return "Start Colorize Selected (0)"
    }

    var body: some View {
        VStack(spacing: 8) {
            Button {
                Task { await store.previewCurrentPage() }
            } label: {
                Label(
                    store.isPreviewing ? "Generating Preview…" : "Preview Current Page",
                    systemImage: "sparkles"
                )
                .frame(maxWidth: .infinity)
            }
            .studioButtonStyle(.secondary, theme: theme, size: .regular)
            .disabled(!hasSession || store.isPreviewing || store.isColorizing)

            Button {
                Task {
                    if store.selectedPageIndices.isEmpty {
                        store.selectAllPages()
                    }
                    await store.startColorization(forceRecolorize: false)
                }
            } label: {
                Label(primaryColorizeTitle, systemImage: "wand.and.stars")
                    .monospacedDigit()
                    .frame(maxWidth: .infinity)
            }
            .studioButtonStyle(.prominent, theme: theme, size: .regular)
            .disabled(!hasSession || !hasPages || store.isColorizing)

            HStack(spacing: 8) {
                Button {
                    Task { await store.resumeColorization() }
                } label: {
                    Label("Resume", systemImage: "play.fill")
                        .frame(maxWidth: .infinity)
                }
                .studioButtonStyle(.secondary, theme: theme, size: .small)
                .disabled(!hasSession || store.isColorizing)

                Button {
                    Task { await store.startBatchColorization() }
                } label: {
                    Label("Batch Queue", systemImage: "square.stack.3d.up")
                        .frame(maxWidth: .infinity)
                }
                .studioButtonStyle(.secondary, theme: theme, size: .small, tint: theme.accentSecondary)
                .disabled(store.sessions.isEmpty || store.isColorizing)
            }
        }
        .padding(12)
        .background(theme.bgHeader)
    }
}

// MARK: - Tab 1: Engine & Tuning

private struct EngineTuningTab: View {
    @Bindable var store: StudioStore
    let theme: StudioTheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var apiKeyDraft: String = ""
    @State private var hoveredProvider: AIProvider?
    @Namespace private var providerSelectionNamespace

    private var needsGeminiKey: Bool {
        store.colorizeConfig.modelProvider == .googleNano
            || (store.colorizeConfig.translatePage && store.colorizeConfig.translationEngine == .gemini)
    }

    var body: some View {
        StudioCardSurface(theme: theme) {
            VStack(alignment: .leading, spacing: 10) {
                StudioFieldLabel(title: "AI Colorization Provider", theme: theme)

                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                    ForEach(AIProvider.allCases) { provider in
                        let selected = store.colorizeConfig.modelProvider == provider
                        let isHovered = hoveredProvider == provider
                        let shape = RoundedRectangle(cornerRadius: 9, style: .continuous)
                        Button {
                            withAnimation(.spring(response: 0.24, dampingFraction: 0.80)) {
                                store.selectAIProvider(provider)
                            }
                        } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                HStack {
                                    Image(systemName: provider.sfSymbol)
                                        .foregroundStyle(selected ? theme.accentPrimary : (isHovered ? theme.textPrimary : theme.textSecondary))
                                    Spacer()
                                    if selected {
                                        Image(systemName: "checkmark.circle.fill")
                                            .font(.caption)
                                            .foregroundStyle(theme.accentPrimary)
                                            .transition(.scale.combined(with: .opacity))
                                    }
                                }
                                Text(provider.displayName)
                                    .font(.caption.weight(.semibold))
                                    .foregroundStyle(theme.textPrimary)
                                Text(provider.subtitle)
                                    .font(.caption2)
                                    .foregroundStyle(theme.textMuted)
                            }
                            .padding(8.5)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background {
                                ZStack {
                                    shape.fill(theme.bgInput)
                                    if selected {
                                        shape.fill(
                                            LinearGradient(
                                                colors: [
                                                    theme.accentPrimary.opacity(0.24),
                                                    theme.accentPrimary.opacity(0.10),
                                                ],
                                                startPoint: .topLeading,
                                                endPoint: .bottomTrailing
                                            )
                                        )
                                        .overlay(
                                            shape.fill(
                                                LinearGradient(
                                                    colors: [Color.white.opacity(theme.isLightTheme ? 0.45 : 0.12), Color.clear],
                                                    startPoint: .top,
                                                    endPoint: .bottom
                                                )
                                            )
                                        )
                                        .overlay(
                                            shape.strokeBorder(
                                                LinearGradient(
                                                    colors: [theme.accentPrimary, theme.accentPrimary.opacity(0.45)],
                                                    startPoint: .topLeading,
                                                    endPoint: .bottomTrailing
                                                ),
                                                lineWidth: 1.25
                                            )
                                        )
                                        .shadow(color: theme.accentPrimary.opacity(0.22), radius: 6, y: 1)
                                        .matchedGeometryEffect(id: "activeProviderGlass", in: providerSelectionNamespace)
                                    } else {
                                        if isHovered {
                                            shape.fill(theme.hoverFillOverlay)
                                            shape.fill(
                                                LinearGradient(
                                                    colors: [theme.hoverTopSheen, Color.clear],
                                                    startPoint: .top,
                                                    endPoint: .center
                                                )
                                            )
                                        }
                                        shape.strokeBorder(
                                            isHovered ? theme.hoverBorderAccent : theme.bgCardBorder,
                                            lineWidth: isHovered ? 1.0 : 0.85
                                        )
                                    }
                                }
                            }
                            .shadow(
                                color: !selected && isHovered ? theme.hoverGlowColor.opacity(0.35) : .clear,
                                radius: !selected && isHovered ? 6 : 0,
                                y: 1
                            )
                            .scaleEffect(
                                isHovered && !selected
                                    ? StudioMotion.effectiveScale(StudioMotion.cardHoverScale, reduceMotion: reduceMotion)
                                    : 1.0
                            )
                            .contentShape(shape)
                        }
                        .buttonStyle(.plain)
                        .animation(StudioMotion.hoverAnimation(reduceMotion: reduceMotion), value: isHovered)
                        .onHover { hovering in
                            hoveredProvider = hovering ? provider : (hoveredProvider == provider ? nil : hoveredProvider)
                        }
                    }
                }
                .onDisappear {
                    hoveredProvider = nil
                }

                VStack(alignment: .leading, spacing: 5) {
                    StudioFieldLabel(title: "Model Variant", theme: theme)
                    StudioDropdownPicker(
                        selection: $store.colorizeConfig.modelName,
                        options: store.colorizeConfig.modelProvider.variants.map {
                            StudioDropdownOption(value: $0.id, title: $0.label)
                        },
                        theme: theme,
                        size: .regular
                    )
                    .onChange(of: store.colorizeConfig.modelName) { _, _ in
                        store.persistColorizePreferences()
                    }
                }

                if needsGeminiKey {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            StudioFieldLabel(title: "Google Gemini API Key", theme: theme)
                            StudioBadgePill(
                                text: store.geminiAPIKey.isEmpty ? "Not Stored" : "In Keychain",
                                systemImage: "key.fill",
                                foreground: store.geminiAPIKey.isEmpty ? theme.accentYellow : theme.accentGreen,
                                background: (store.geminiAPIKey.isEmpty ? theme.accentYellow : theme.accentGreen).opacity(0.12),
                                border: (store.geminiAPIKey.isEmpty ? theme.accentYellow : theme.accentGreen).opacity(0.3)
                            )
                        }

                        HStack(spacing: 6) {
                            SecureField("AIzaSy...", text: $apiKeyDraft)
                                .textFieldStyle(.roundedBorder)
                            Button("Save") {
                                store.saveGeminiAPIKey(apiKeyDraft)
                            }
                            .studioButtonStyle(.prominent, theme: theme, size: .small)
                        }
                    }
                    .padding(.top, 4)
                }
            }
        }
        .onAppear {
            apiKeyDraft = store.geminiAPIKey
        }

        StudioCardSurface(theme: theme) {
            VStack(alignment: .leading, spacing: 12) {
                StudioFieldLabel(title: "Aesthetic & Neural Tuning", theme: theme)

                VStack(alignment: .leading, spacing: 5) {
                    Text("Color Aesthetic")
                        .font(.caption.weight(.medium))
                        .foregroundStyle(theme.textSecondary)
                    StudioDropdownPicker(
                        selection: $store.colorizeConfig.style,
                        options: ColorAestheticStyle.allCases.map {
                            StudioDropdownOption(value: $0, title: $0.displayName, systemImage: $0.sfSymbol)
                        },
                        theme: theme,
                        size: .regular
                    )
                    .onChange(of: store.colorizeConfig.style) { _, _ in
                        store.persistColorizePreferences()
                    }
                }

                sliderRow(
                    title: "Line Art Preservation",
                    valueText: "\(Int((store.colorizeConfig.linePreserve * 100).rounded()))%",
                    value: $store.colorizeConfig.linePreserve,
                    range: 0.50...1.00,
                    step: 0.01
                )

                sliderRow(
                    title: "Color Saturation",
                    valueText: String(format: "%.2fx", store.colorizeConfig.saturation),
                    value: $store.colorizeConfig.saturation,
                    range: 0.50...2.50,
                    step: 0.05
                )

                sliderRow(
                    title: "Luminance Contrast",
                    valueText: String(format: "%.2fx", store.colorizeConfig.contrast),
                    value: $store.colorizeConfig.contrast,
                    range: 0.50...1.50,
                    step: 0.05
                )

                StudioHairline(theme: theme)

                StudioToggleRow(
                    title: "Skip Already-Colored Pages",
                    subtitle: "Preserve native full-color spreads",
                    isOn: $store.colorizeConfig.skipIfColored,
                    theme: theme
                )
                .onChange(of: store.colorizeConfig.skipIfColored) { _, _ in
                    store.persistColorizePreferences()
                }

                StudioToggleRow(
                    title: "FFDNet Screentone Denoising",
                    subtitle: "Clean halftone dots before coloring",
                    isOn: $store.colorizeConfig.denoiseScreentone,
                    theme: theme
                )
                .onChange(of: store.colorizeConfig.denoiseScreentone) { _, _ in
                    store.persistColorizePreferences()
                }

                if store.colorizeConfig.denoiseScreentone {
                    HStack {
                        Text("Denoise Sigma")
                            .font(.caption)
                            .foregroundStyle(theme.textSecondary)
                        Slider(
                            value: Binding(
                                get: { Double(store.colorizeConfig.denoiseSigma) },
                                set: { store.colorizeConfig.denoiseSigma = Int($0.rounded()) }
                            ),
                            in: 5...50,
                            step: 1
                        )
                        .tint(theme.accentSecondary)
                        Text("\(store.colorizeConfig.denoiseSigma)")
                            .font(.caption.weight(.semibold))
                            .monospacedDigit()
                            .foregroundStyle(theme.accentSecondary)
                            .frame(width: 28, alignment: .trailing)
                    }
                }

                StudioHairline(theme: theme)

                StudioToggleRow(
                    title: "Translate Manga Speech Bubbles",
                    subtitle: "Detect, OCR, and typeset dialogue",
                    isOn: $store.colorizeConfig.translatePage,
                    theme: theme
                )
                .onChange(of: store.colorizeConfig.translatePage) { _, _ in
                    store.persistColorizePreferences()
                }

                if store.colorizeConfig.translatePage {
                    VStack(alignment: .leading, spacing: 5) {
                        StudioFieldLabel(title: "Translation Engine", theme: theme)
                        StudioDropdownPicker(
                            selection: $store.colorizeConfig.translationEngine,
                            options: TranslationEngine.allCases.map {
                                StudioDropdownOption(value: $0, title: $0.displayName)
                            },
                            theme: theme,
                            size: .small
                        )
                        .onChange(of: store.colorizeConfig.translationEngine) { _, _ in
                            store.persistColorizePreferences()
                        }
                    }

                    VStack(alignment: .leading, spacing: 5) {
                        StudioFieldLabel(title: "Target Language", theme: theme)
                        StudioDropdownPicker(
                            selection: $store.colorizeConfig.targetLanguage,
                            options: TargetLanguage.allCases.map {
                                StudioDropdownOption(value: $0, title: $0.displayName)
                            },
                            theme: theme,
                            size: .small
                        )
                        .onChange(of: store.colorizeConfig.targetLanguage) { _, _ in
                            store.persistColorizePreferences()
                        }
                    }
                }
            }
        }
    }

    private func sliderRow(
        title: String,
        valueText: String,
        value: Binding<Double>,
        range: ClosedRange<Double>,
        step: Double
    ) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(title)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(theme.textSecondary)
                Spacer()
                Text(valueText)
                    .font(.caption.weight(.bold))
                    .monospacedDigit()
                    .foregroundStyle(theme.accentPrimary)
            }
            Slider(value: value, in: range, step: step)
                .tint(theme.accentPrimary)
                .onChange(of: value.wrappedValue) { _, _ in
                    store.persistColorizePreferences()
                }
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
        .studioHoverRow(theme: theme, cornerRadius: 7)
        .padding(.horizontal, -6)
    }
}

// MARK: - Tab 2: Palette & Series Memory

private struct PaletteSeriesTab: View {
    @Bindable var store: StudioStore
    let theme: StudioTheme

    @State private var selectedPresetId: String = ""
    @State private var onlineQuery: String = ""
    @State private var newChar = CharacterEntryDTO(name: "")

    var body: some View {
        StudioCardSurface(theme: theme) {
            VStack(alignment: .leading, spacing: 10) {
                StudioFieldLabel(title: "Manga Preset & Web Lookup", theme: theme)

                HStack(spacing: 6) {
                    StudioDropdownPicker(
                        selection: $selectedPresetId,
                        options: [StudioDropdownOption(value: "", title: "Custom / None")] + store.presets.map {
                            StudioDropdownOption(value: $0.id, title: $0.title)
                        },
                        theme: theme,
                        size: .small
                    )

                    Button("Apply") {
                        guard !selectedPresetId.isEmpty else { return }
                        Task { await store.applyPreset(presetId: selectedPresetId) }
                    }
                    .studioButtonStyle(.prominent, theme: theme, size: .small)
                    .disabled(store.activeSession == nil || selectedPresetId.isEmpty)
                }

                HStack(spacing: 6) {
                    TextField("Search online palette (e.g. Dandadan)", text: $onlineQuery)
                        .textFieldStyle(.roundedBorder)
                    Button("Search") {
                        Task { await store.searchOnlinePreset(query: onlineQuery) }
                    }
                    .studioButtonStyle(.secondary, theme: theme, size: .small)
                    .disabled(onlineQuery.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
        .onAppear {
            selectedPresetId = store.activePalette.presetId
        }
        .onChange(of: store.activePalette.presetId) { _, newId in
            selectedPresetId = newId
        }

        StudioCardSurface(theme: theme) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    StudioFieldLabel(title: "Page Character Scan", theme: theme)
                    Button {
                        Task { await store.recognizeCurrentPageCharacters() }
                    } label: {
                        Label(store.isRecognizingCharacters ? "Scanning…" : "Scan (YOLO+CLIP)", systemImage: "viewfinder")
                    }
                    .studioButtonStyle(.secondary, theme: theme, size: .small)
                    .disabled(store.activeSession == nil || store.isRecognizingCharacters)
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("Recognition Mode")
                        .font(.caption2)
                        .foregroundStyle(theme.textMuted)
                    StudioDropdownPicker(
                        selection: $store.colorizeConfig.recognitionMode,
                        options: RecognitionMode.allCases.map {
                            StudioDropdownOption(value: $0, title: $0.displayName)
                        },
                        theme: theme,
                        size: .small
                    )
                }
            }
        }

        StudioCardSurface(theme: theme) {
            VStack(alignment: .leading, spacing: 10) {
                StudioFieldLabel(
                    title: "Character Palette",
                    badgeText: "\(store.activePalette.characters.count)",
                    theme: theme
                )

                if store.activePalette.characters.isEmpty {
                    Text("No characters configured yet. Apply a manga preset or add one below.")
                        .font(.caption)
                        .foregroundStyle(theme.textMuted)
                } else {
                    ForEach(store.activePalette.characters) { char in
                        CharacterPaletteCard(
                            character: char,
                            theme: theme,
                            onSave: { updated in
                                Task { await store.upsertCharacter(updated) }
                            },
                            onDelete: {
                                Task { await store.deleteCharacter(name: char.name) }
                            }
                        )
                    }
                }

                StudioHairline(theme: theme)

                VStack(alignment: .leading, spacing: 8) {
                    Text("Add / Update Character")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(theme.textSecondary)

                    TextField("Character name (e.g. Arale)", text: $newChar.name)
                        .textFieldStyle(.roundedBorder)

                    HStack(spacing: 8) {
                        CharacterColorSwatchButton(label: "Hair", hex: $newChar.hairHex, theme: theme)
                        CharacterColorSwatchButton(label: "Eyes", hex: $newChar.eyeHex, theme: theme)
                        CharacterColorSwatchButton(label: "Skin", hex: $newChar.skinHex, theme: theme)
                    }
                    HStack(spacing: 8) {
                        CharacterColorSwatchButton(label: "Outfit", hex: $newChar.costumeHex, theme: theme)
                        CharacterColorSwatchButton(label: "Extra", hex: $newChar.extraHex, theme: theme)
                        Spacer()
                        Button {
                            let toSave = newChar
                            newChar = CharacterEntryDTO(name: "")
                            Task { await store.upsertCharacter(toSave) }
                        } label: {
                            Label("Add", systemImage: "plus")
                        }
                        .studioButtonStyle(.prominent, theme: theme, size: .small, tint: theme.accentSecondary)
                        .disabled(store.activeSession == nil || newChar.name.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                }
            }
        }

        StudioCardSurface(theme: theme) {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Label("Series Memory & LoRA", systemImage: "brain.head.profile")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(theme.textPrimary)
                    Spacer()
                    if let status = store.adapterStatus {
                        StudioBadgePill(
                            text: status.isReady ? "LoRA Ready" : (status.isTraining ? "Training" : "Untrained"),
                            foreground: status.isReady ? theme.accentGreen : (status.isTraining ? theme.accentYellow : theme.textMuted),
                            background: theme.bgInput,
                            border: theme.bgCardBorder
                        )
                    }
                }

                let learned = store.seriesMemoryResponse?.memory?.approvedPagesCount ?? 0
                Text("\(store.seriesMemoryResponse?.title ?? "Active Series") · \(learned) learned · \(store.seriesExemplars.count) exemplar(s)")
                    .font(.caption)
                    .monospacedDigit()
                    .foregroundStyle(theme.textSecondary)

                Button {
                    store.showExemplarSheet = true
                } label: {
                    Label("Open Exemplar & LoRA Studio…", systemImage: "slider.horizontal.3")
                        .frame(maxWidth: .infinity)
                }
                .studioButtonStyle(.secondary, theme: theme, size: .regular)
                .disabled(store.activeSession == nil)
            }
        }
    }
}

private struct CharacterPaletteCard: View {
    @State private var draft: CharacterEntryDTO
    let theme: StudioTheme
    let onSave: (CharacterEntryDTO) -> Void
    let onDelete: () -> Void

    init(
        character: CharacterEntryDTO,
        theme: StudioTheme,
        onSave: @escaping (CharacterEntryDTO) -> Void,
        onDelete: @escaping () -> Void
    ) {
        self._draft = State(initialValue: character)
        self.theme = theme
        self.onSave = onSave
        self.onDelete = onDelete
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(draft.name)
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(theme.textPrimary)
                Spacer()
                Button("Save") { onSave(draft) }
                    .studioButtonStyle(.secondary, theme: theme, size: .mini)
                Button(role: .destructive, action: onDelete) {
                    Image(systemName: "trash")
                        .font(.caption)
                }
                .buttonStyle(StudioInlineIconButtonStyle(theme: theme, isDestructive: true))
            }

            if !draft.notes.isEmpty {
                Text(draft.notes)
                    .font(.caption2)
                    .foregroundStyle(theme.textMuted)
                    .lineLimit(2)
            }

            HStack(spacing: 8) {
                CharacterColorSwatchButton(label: "Hair", hex: $draft.hairHex, theme: theme)
                CharacterColorSwatchButton(label: "Eyes", hex: $draft.eyeHex, theme: theme)
                CharacterColorSwatchButton(label: "Skin", hex: $draft.skinHex, theme: theme)
                CharacterColorSwatchButton(label: "Outfit", hex: $draft.costumeHex, theme: theme)
                CharacterColorSwatchButton(label: "Extra", hex: $draft.extraHex, theme: theme)
            }
        }
        .padding(8)
        .background(theme.bgCardSubtle, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .strokeBorder(theme.bgCardBorder, lineWidth: 1)
        )
    }
}

private struct CharacterColorSwatchButton: View {
    let label: String
    @Binding var hex: String
    let theme: StudioTheme

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var showPickerPopover: Bool = false
    @State private var isHovered: Bool = false

    private var resolvedColor: Color {
        Color(studioHex: hex.isEmpty ? "#808080" : hex)
    }

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 6, style: .continuous)
        Button {
            showPickerPopover.toggle()
        } label: {
            VStack(spacing: 3) {
                Text(label)
                    .font(.caption2)
                    .foregroundStyle(isHovered ? theme.textPrimary : theme.textMuted)
                RoundedRectangle(cornerRadius: 6, style: .continuous)
                    .fill(resolvedColor)
                    .frame(width: 28, height: 22)
                    .overlay(
                        RoundedRectangle(cornerRadius: 6, style: .continuous)
                            .strokeBorder(
                                isHovered || showPickerPopover ? theme.accentPrimary : theme.bgCardBorder,
                                lineWidth: isHovered || showPickerPopover ? 1.4 : 1
                            )
                    )
                    .shadow(
                        color: isHovered ? resolvedColor.opacity(0.45) : .clear,
                        radius: isHovered ? 5 : 0,
                        y: 1
                    )
                    .scaleEffect(
                        isHovered
                            ? StudioMotion.effectiveScale(StudioMotion.swatchHoverScale, reduceMotion: reduceMotion)
                            : 1.0
                    )
                Text(hex.isEmpty ? "—" : hex.uppercased())
                    .font(.system(size: 9, design: .monospaced))
                    .foregroundStyle(isHovered ? theme.textPrimary : theme.textSecondary)
                    .lineLimit(1)
                    .frame(width: 48)
            }
            .padding(.vertical, 3)
            .padding(.horizontal, 2)
            .background(
                (isHovered ? theme.bgInput : theme.bgInput.opacity(0.45)),
                in: shape
            )
            .overlay(
                shape.strokeBorder(
                    isHovered ? theme.hoverBorderAccent.opacity(0.65) : Color.clear,
                    lineWidth: 0.75
                )
            )
            .contentShape(shape)
        }
        .buttonStyle(.plain)
        .animation(StudioMotion.hoverAnimation(reduceMotion: reduceMotion), value: isHovered)
        .onHover { hovering in
            isHovered = hovering
        }
        .onDisappear {
            isHovered = false
        }
        .popover(isPresented: $showPickerPopover, arrowEdge: .bottom) {
            VStack(alignment: .leading, spacing: 10) {
                Text("\(label) Color")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(theme.textPrimary)

                ColorPicker(
                    "Pick Color",
                    selection: Binding(
                        get: { resolvedColor },
                        set: { hex = $0.toStudioHex() }
                    ),
                    supportsOpacity: false
                )

                TextField("#RRGGBB", text: $hex)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(.caption, design: .monospaced))
                    .frame(width: 130)
            }
            .padding(12)
        }
    }
}

// MARK: - Tab 3: Export & Omnibus

private struct ExportOmnibusTab: View {
    @Bindable var store: StudioStore
    let theme: StudioTheme

    var body: some View {
        StudioCardSurface(theme: theme) {
            VStack(alignment: .leading, spacing: 8) {
                StudioFieldLabel(title: "Single-Document Export", theme: theme)

                LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 6) {
                    ForEach([ExportFormat.pdf, .epub, .mobi, .zip, .auto]) { fmt in
                        Button {
                            Task { await store.exportCurrentSession(format: fmt) }
                        } label: {
                            Text(fmt.displayName)
                                .font(.caption.weight(.medium))
                                .frame(maxWidth: .infinity)
                        }
                        .studioButtonStyle(.secondary, theme: theme, size: .small)
                        .disabled(store.activeSession == nil || store.isExporting)
                    }
                }

                StudioHairline(theme: theme)

                Button {
                    Task { await store.exportSelectedBatch(format: .auto) }
                } label: {
                    Label("Batch Export Queue ZIP", systemImage: "archivebox.fill")
                        .frame(maxWidth: .infinity)
                }
                .studioButtonStyle(.secondary, theme: theme, size: .regular)
                .disabled(store.sessions.isEmpty || store.isExporting)
            }
        }

        StudioCardSurface(theme: theme) {
            VStack(alignment: .leading, spacing: 10) {
                StudioFieldLabel(title: "Combined E-Reader Omnibus", theme: theme)

                StudioSegmentedControl(
                    items: [
                        (.epub, "EPUB3", nil),
                        (.mobi, "MOBI", nil),
                        (.pdf, "PDF", nil),
                    ],
                    selection: $store.omnibusConfig.format,
                    theme: theme,
                    fullWidth: true
                )

                TextField(
                    "Collection Title (auto-detected if blank)",
                    text: Binding(
                        get: { store.omnibusConfig.title ?? "" },
                        set: { store.omnibusConfig.title = $0.isEmpty ? nil : $0 }
                    )
                )
                .textFieldStyle(.roundedBorder)

                VStack(alignment: .leading, spacing: 4) {
                    Text("Split Mode")
                        .font(.caption2)
                        .foregroundStyle(theme.textMuted)
                    StudioDropdownPicker(
                        selection: $store.omnibusConfig.chunkBy,
                        options: OmnibusChunkMode.allCases.map {
                            StudioDropdownOption(value: $0, title: $0.displayName)
                        },
                        theme: theme,
                        size: .regular
                    )
                }

                if store.omnibusConfig.chunkBy != .none {
                    Stepper(
                        value: $store.omnibusConfig.chunkSize,
                        in: store.omnibusConfig.chunkBy == .volumes ? 1...20 : 50...2000,
                        step: store.omnibusConfig.chunkBy == .volumes ? 1 : 50
                    ) {
                        Text(
                            store.omnibusConfig.chunkBy == .volumes
                                ? "Volumes per part: \(store.omnibusConfig.chunkSize)"
                                : "Max MB per part: \(store.omnibusConfig.chunkSize) MB"
                        )
                        .font(.caption)
                        .monospacedDigit()
                    }
                }

                VStack(alignment: .leading, spacing: 4) {
                    Text("Device Preset")
                        .font(.caption2)
                        .foregroundStyle(theme.textMuted)
                    StudioDropdownPicker(
                        selection: $store.omnibusConfig.devicePreset,
                        options: EReaderDevicePreset.allCases.map {
                            StudioDropdownOption(value: $0, title: $0.displayName)
                        },
                        theme: theme,
                        size: .regular
                    )
                    .onChange(of: store.omnibusConfig.devicePreset) { _, newPreset in
                        store.omnibusConfig.maxDimension = newPreset.maxDimension
                        store.omnibusConfig.jpegQuality = newPreset.jpegQuality
                        store.omnibusConfig.colorsoftTune = newPreset.colorsoftTune && !store.omnibusConfig.exportOriginal
                    }
                }

                HStack {
                    Text("Max Dimension: \(store.omnibusConfig.maxDimension == 0 ? "Native" : "\(store.omnibusConfig.maxDimension)px")")
                        .font(.caption)
                        .monospacedDigit()
                    Spacer()
                    Slider(
                        value: Binding(
                            get: { Double(store.omnibusConfig.maxDimension) },
                            set: { store.omnibusConfig.maxDimension = Int($0.rounded()) }
                        ),
                        in: 0...2560,
                        step: 160
                    )
                    .frame(width: 120)
                }

                HStack {
                    Text("JPEG Quality: \(store.omnibusConfig.jpegQuality)%")
                        .font(.caption)
                        .monospacedDigit()
                    Spacer()
                    Slider(
                        value: Binding(
                            get: { Double(store.omnibusConfig.jpegQuality) },
                            set: { store.omnibusConfig.jpegQuality = Int($0.rounded()) }
                        ),
                        in: 60...100,
                        step: 5
                    )
                    .frame(width: 120)
                }

                StudioToggleRow(
                    title: "16-Level E-Ink Grayscale",
                    isOn: $store.omnibusConfig.grayscale,
                    theme: theme
                )
                StudioToggleRow(
                    title: "Kindle Colorsoft Vivid Tune",
                    isOn: $store.omnibusConfig.colorsoftTune,
                    theme: theme
                )
                StudioToggleRow(
                    title: "Export Original Scans",
                    subtitle: "Skip colorization",
                    isOn: $store.omnibusConfig.exportOriginal,
                    theme: theme
                )

                if store.isExporting && store.combinedExportJob != nil {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text(store.combinedExportStatusText)
                                .font(.caption2)
                                .foregroundStyle(theme.textSecondary)
                            Spacer()
                            Text("\(store.combinedExportPercent)%")
                                .font(.caption.weight(.bold))
                                .monospacedDigit()
                        }
                        ProgressView(value: Double(store.combinedExportPercent), total: 100)
                            .tint(theme.accentPrimary)
                        Button("Cancel Export", role: .destructive) {
                            Task { await store.cancelCombinedOmnibusExport() }
                        }
                        .studioButtonStyle(.destructive, theme: theme, size: .small)
                    }
                }

                Button {
                    Task { await store.startCombinedOmnibusExport() }
                } label: {
                    Label("Build Omnibus", systemImage: "book.closed.fill")
                        .frame(maxWidth: .infinity)
                }
                .studioButtonStyle(.prominent, theme: theme, size: .regular)
                .disabled(store.sessions.isEmpty || store.isExporting)

                if let downloaded = store.lastDownloadedFileURL {
                    HStack(spacing: 6) {
                        Button {
                            store.revealInFinder(downloaded)
                        } label: {
                            Label("Reveal in Finder", systemImage: "folder.fill")
                                .frame(maxWidth: .infinity)
                        }
                        .studioButtonStyle(.prominent, theme: theme, size: .small, tint: theme.accentGreen)

                        Button {
                            if let saveURL = StudioFilePanels.pickSaveDestination(suggestedFilename: downloaded.lastPathComponent) {
                                try? FileManager.default.copyItem(at: downloaded, to: saveURL)
                                store.revealInFinder(saveURL)
                            }
                        } label: {
                            Label("Save As…", systemImage: "square.and.arrow.down")
                        }
                        .studioButtonStyle(.secondary, theme: theme, size: .small)
                    }
                }
            }
        }
    }
}
