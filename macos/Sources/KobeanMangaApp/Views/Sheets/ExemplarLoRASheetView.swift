import KobeanMangaCore
import SwiftUI

struct ExemplarLoRASheetView: View {
    @Bindable var store: StudioStore
    @Environment(\.dismiss) private var dismiss

    @State private var trainingSteps: Int = 100
    @State private var learningRate: Double = 2e-4
    @State private var refineSettingsDraft = AutoRefineSettingsDTO()

    private let columns = [
        GridItem(.adaptive(minimum: 150, maximum: 200), spacing: 12)
    ]

    var body: some View {
        let theme = store.currentTheme

        VStack(spacing: 0) {
            HStack(spacing: 10) {
                StudioBrandLogoView(size: 30, style: .appIcon, theme: theme)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Exemplar Gallery & LoRA Adapter Studio")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(theme.textPrimary)
                    Text(store.seriesMemoryResponse?.title ?? "Series Memory")
                        .font(.caption)
                        .foregroundStyle(theme.textSecondary)
                }
                Spacer()
                Button("Done") { dismiss() }
                    .studioButtonStyle(.secondary, theme: theme, size: .small)
                    .keyboardShortcut(.cancelAction)
            }
            .padding(16)
            .background(theme.bgHeader)

            StudioHairline(theme: theme)

            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    adapterTrainingCard(theme: theme)
                    autoRefineCard(theme: theme)
                    exemplarsGridCard(theme: theme)
                }
                .padding(16)
            }
        }
        .frame(minWidth: 740, minHeight: 580)
        .background(theme.bgDark)
        .onAppear {
            if let current = store.autoRefineSettings {
                refineSettingsDraft = current
            }
        }
    }

    private func adapterTrainingCard(theme: StudioTheme) -> some View {
        StudioCardSurface(theme: theme) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Label("SeriesResidualAdapter LoRA Fine-Tuning", systemImage: "cpu.fill")
                        .font(.headline)
                        .foregroundStyle(theme.textPrimary)
                    Spacer()
                    if let status = store.adapterStatus {
                        StudioBadgePill(
                            text: status.status.replacingOccurrences(of: "_", with: " ").capitalized,
                            foreground: status.isReady ? theme.accentGreen : (status.isTraining ? theme.accentYellow : theme.textSecondary),
                            background: theme.bgInput,
                            border: theme.bgCardBorder
                        )
                    }
                }

                if let status = store.adapterStatus, status.isTraining {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack {
                            Text("Step \(status.step ?? 0) / \(status.totalSteps ?? trainingSteps)")
                                .font(.caption.weight(.semibold))
                                .monospacedDigit()
                            Spacer()
                            if let loss = status.loss {
                                Text(String(format: "Loss: %.4f", loss))
                                    .font(.caption)
                                    .monospacedDigit()
                            }
                            Text("\(Int((status.progress ?? 0).rounded()))%")
                                .font(.caption.weight(.bold))
                                .monospacedDigit()
                        }
                        ProgressView(value: status.progress ?? 0, total: 100)
                            .tint(theme.accentSecondary)
                    }
                }

                HStack(spacing: 14) {
                    Stepper("Steps: \(trainingSteps)", value: $trainingSteps, in: 20...500, step: 20)
                        .font(.callout)
                        .monospacedDigit()

                    HStack(spacing: 6) {
                        Text("Learning Rate")
                            .font(.caption.weight(.medium))
                            .foregroundStyle(theme.textSecondary)
                        StudioDropdownPicker(
                            selection: $learningRate,
                            options: [
                                StudioDropdownOption(value: 1e-4, title: "1e-4"),
                                StudioDropdownOption(value: 2e-4, title: "2e-4"),
                                StudioDropdownOption(value: 5e-4, title: "5e-4"),
                            ],
                            theme: theme,
                            size: .small
                        )
                        .frame(width: 96)
                    }
                }

                HStack(spacing: 8) {
                    Button {
                        Task { await store.trainSeriesAdapter(steps: trainingSteps, lr: learningRate) }
                    } label: {
                        Label("Train LoRA Adapter", systemImage: "play.fill")
                    }
                    .studioButtonStyle(.prominent, theme: theme, size: .regular)
                    .disabled(store.seriesExemplars.isEmpty || (store.adapterStatus?.isTraining ?? false))

                    if store.adapterStatus?.isTraining == true {
                        Button("Cancel Training", role: .destructive) {
                            Task { await store.cancelAdapterTraining() }
                        }
                        .studioButtonStyle(.destructive, theme: theme, size: .regular)
                    }

                    Spacer()

                    Button("Reset Adapter", role: .destructive) {
                        Task { await store.deleteSeriesAdapter() }
                    }
                    .studioButtonStyle(.destructive, theme: theme, size: .regular)
                    .disabled(store.adapterStatus?.isReady != true)
                }
            }
        }
    }

    private func autoRefineCard(theme: StudioTheme) -> some View {
        StudioCardSurface(theme: theme) {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Label("Confidence-Gated Active Learning", systemImage: "sparkles")
                        .font(.headline)
                        .foregroundStyle(theme.textPrimary)
                    Spacer()
                    Button("Save Auto-Refine") {
                        Task { await store.updateAutoRefineSettings(refineSettingsDraft) }
                    }
                    .studioButtonStyle(.secondary, theme: theme, size: .small)
                }

                Toggle("Enable Automatic High-Confidence Harvesting", isOn: $refineSettingsDraft.autoRefineEnabled)

                HStack(spacing: 16) {
                    HStack {
                        Text("Quality Threshold: \(Int((refineSettingsDraft.autoHarvestThreshold * 100).rounded()))%")
                            .font(.caption)
                            .monospacedDigit()
                        Slider(value: $refineSettingsDraft.autoHarvestThreshold, in: 0.65...0.98, step: 0.01)
                            .frame(width: 150)
                    }

                    Stepper("Refine Every \(refineSettingsDraft.autoRefineInterval) Pages", value: $refineSettingsDraft.autoRefineInterval, in: 1...30)
                        .font(.caption)
                        .monospacedDigit()
                }
            }
        }
    }

    private func exemplarsGridCard(theme: StudioTheme) -> some View {
        StudioCardSurface(theme: theme) {
            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("Harvested Visual Exemplars (\(store.seriesExemplars.count))")
                        .font(.headline)
                        .monospacedDigit()
                        .foregroundStyle(theme.textPrimary)
                    Spacer()
                }

                if store.seriesExemplars.isEmpty {
                    Text("No exemplars harvested yet. Colorize pages or click Learn Page in the comparator.")
                        .font(.callout)
                        .foregroundStyle(theme.textMuted)
                        .padding(.vertical, 20)
                } else {
                    LazyVGrid(columns: columns, spacing: 12) {
                        ForEach(store.seriesExemplars) { ex in
                            VStack(alignment: .leading, spacing: 6) {
                                StudioRemoteImageView(
                                    url: ex.imageUrl.flatMap { store.apiClient.imageURL(relativePath: $0, cacheBuster: nil) },
                                    placeholderText: "Page \(ex.pageIndex + 1)",
                                    theme: theme,
                                    contentMode: .fill,
                                    maxPixelDimension: 280
                                )
                                .frame(height: 160)
                                .clipped()
                                .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))

                                HStack {
                                    Text("Page \(ex.pageIndex + 1)")
                                        .font(.caption.weight(.semibold))
                                        .monospacedDigit()
                                        .foregroundStyle(theme.textPrimary)
                                    Spacer()
                                    Button {
                                        Task { await store.togglePinExemplar(pageIndex: ex.pageIndex, pinned: !ex.pinned) }
                                    } label: {
                                        Image(systemName: ex.pinned ? "pin.fill" : "pin")
                                            .font(.caption)
                                    }
                                    .buttonStyle(
                                        StudioInlineIconButtonStyle(
                                            theme: theme,
                                            tint: ex.pinned ? theme.accentYellow : theme.textMuted
                                        )
                                    )

                                    Button(role: .destructive) {
                                        Task { await store.deleteExemplar(pageIndex: ex.pageIndex) }
                                    } label: {
                                        Image(systemName: "trash")
                                            .font(.caption)
                                    }
                                    .buttonStyle(StudioInlineIconButtonStyle(theme: theme, isDestructive: true))
                                }
                            }
                            .padding(8)
                            .background(theme.bgCardSubtle, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                            .studioHoverRow(
                                theme: theme,
                                cornerRadius: 10,
                                isSelected: ex.pinned,
                                showIdleBorder: true,
                                scaleOnHover: true
                            )
                        }
                    }
                }
            }
        }
    }
}
