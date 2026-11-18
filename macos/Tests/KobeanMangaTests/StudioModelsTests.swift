import XCTest
@testable import KobeanMangaCore

final class StudioModelsTests: XCTestCase {
    private let decoder = JSONDecoder()

    func testDecodeHealthStatusAndActiveTasksFallback() throws {
        let primaryJSON = """
        {
          "status": "ok",
          "service": "kobean-manga-colorizer",
          "version": "1.0.0",
          "active_colorization_tasks": 2,
          "batch_running": true,
          "total_sessions": 7
        }
        """.data(using: .utf8)!

        let health = try decoder.decode(HealthStatus.self, from: primaryJSON)
        XCTAssertEqual(health.status, "ok")
        XCTAssertEqual(health.service, "kobean-manga-colorizer")
        XCTAssertEqual(health.version, "1.0.0")
        XCTAssertEqual(health.activeColorizationTasks, 2)
        XCTAssertTrue(health.batchRunning)
        XCTAssertEqual(health.totalSessions, 7)
        XCTAssertTrue(health.isHealthy)

        let fallbackJSON = """
        {
          "status": "ok",
          "active_tasks": 1
        }
        """.data(using: .utf8)!
        let fallback = try decoder.decode(HealthStatus.self, from: fallbackJSON)
        XCTAssertEqual(fallback.activeColorizationTasks, 1)
        XCTAssertFalse(fallback.batchRunning)
        XCTAssertEqual(fallback.totalSessions, 0)
    }

    func testDecodeHardwareProfile() throws {
        let json = """
        {
          "device": "mps",
          "chip_name": "Apple M4 Pro",
          "ram_gb": 24,
          "use_fp16": true,
          "empty_cache_interval": 15,
          "preferred_size": 768,
          "max_concurrency": 2,
          "generator_weights_ready": true,
          "storage": {
            "sessions_dir": "/tmp/sessions",
            "uploads_dir": "/tmp/uploads",
            "output_dir": "/tmp/output"
          }
        }
        """.data(using: .utf8)!

        let hardware = try decoder.decode(HardwareProfile.self, from: json)
        XCTAssertEqual(hardware.device, "mps")
        XCTAssertEqual(hardware.chipName, "Apple M4 Pro")
        XCTAssertEqual(hardware.ramGB, 24)
        XCTAssertTrue(hardware.useFP16)
        XCTAssertEqual(hardware.emptyCacheInterval, 15)
        XCTAssertEqual(hardware.preferredSize, 768)
        XCTAssertEqual(hardware.maxConcurrency, 2)
        XCTAssertTrue(hardware.generatorWeightsReady)
        XCTAssertEqual(hardware.storage.sessionsDir, "/tmp/sessions")
        XCTAssertEqual(hardware.storage.uploadsDir, "/tmp/uploads")
        XCTAssertEqual(hardware.storage.outputDir, "/tmp/output")
    }

    func testDecodeSessionsAndDetailWithNestedQualityScore() throws {
        let json = """
        {
          "session_id": "sess-001",
          "batch_id": "batch-42",
          "filename": "Dr_Slump_v01.cbz",
          "ext": ".cbz",
          "total_pages": 2,
          "processed_count": 1,
          "status": "pending",
          "detected_preset": "dr_slump",
          "preset_title": "Dr. Slump",
          "recommended_style": "shonen_vivid",
          "pages": [
            {
              "page_index": 0,
              "display_name": "Page 1",
              "filename": "page_0001.jpg",
              "original_path": "/sessions/sess-001/original/page_0001.jpg",
              "colorized_url": "/api/session/sess-001/image/colorized/page_0001.jpg",
              "status": "colorized",
              "skipped_colored": false,
              "translated": true,
              "exemplar_used": "page_0002.jpg",
              "adapter_used": true,
              "quality_score": {
                "overall_score": 0.912,
                "grade": "high",
                "auto_learn_eligible": true,
                "metrics": {
                  "linework_integrity": 0.95,
                  "white_purity": 0.92,
                  "color_richness": 0.86
                },
                "threshold": 0.82
              },
              "recognized_characters": [
                {
                  "name": "Arale Norimaki",
                  "confidence": 0.94,
                  "bounding_box": [0.1, 0.2, 0.8, 0.6],
                  "detection_method": "offline_ai",
                  "matched_features": ["winged_cap", "glasses"]
                }
              ],
              "translations": [
                {
                  "box": [10, 20, 110, 140],
                  "japanese": "んちゃ！",
                  "english": "N'cha!",
                  "confidence": 0.91
                }
              ]
            },
            {
              "page_index": 1,
              "filename": "page_0002.jpg",
              "status": "pending"
            }
          ]
        }
        """.data(using: .utf8)!

        let detail = try decoder.decode(MangaSessionDetail.self, from: json)
        XCTAssertEqual(detail.sessionId, "sess-001")
        XCTAssertEqual(detail.batchId, "batch-42")
        XCTAssertEqual(detail.filename, "Dr_Slump_v01.cbz")
        XCTAssertEqual(detail.totalPages, 2)
        XCTAssertEqual(detail.processedCount, 1)
        XCTAssertEqual(detail.detectedPreset, "dr_slump")
        XCTAssertEqual(detail.pages.count, 2)

        let p0 = detail.pages[0]
        XCTAssertEqual(p0.index, 0)
        XCTAssertEqual(p0.filename, "page_0001.jpg")
        XCTAssertEqual(p0.colorizedUrl, "/api/session/sess-001/image/colorized/page_0001.jpg")
        XCTAssertTrue(p0.translated)
        XCTAssertEqual(p0.exemplarUsed, "page_0002.jpg")
        XCTAssertTrue(p0.adapterUsed)
        XCTAssertEqual(p0.qualityScore?.overall ?? 0, 0.912, accuracy: 0.001)
        XCTAssertEqual(p0.qualityScore?.lineworkIntegrity ?? 0, 0.95, accuracy: 0.001)
        XCTAssertEqual(p0.qualityScore?.whitePurity ?? 0, 0.92, accuracy: 0.001)
        XCTAssertEqual(p0.qualityScore?.colorRichness ?? 0, 0.86, accuracy: 0.001)
        XCTAssertEqual(p0.qualityScore?.autoLearnEligible, true)
        XCTAssertEqual(p0.recognizedCharacters.first?.name, "Arale Norimaki")
        XCTAssertEqual(p0.translations.first?.english, "N'cha!")

        let p1 = detail.pages[1]
        XCTAssertEqual(p1.index, 1)
        XCTAssertEqual(p1.status, "pending")
        XCTAssertFalse(p1.translated)
        XCTAssertTrue(p1.translations.isEmpty)
    }

    func testDecodePreviewAndPaletteAndSeriesMemory() throws {
        let previewJSON = """
        {
          "status": "success",
          "page_index": 0,
          "colorized_url": "/api/session/s1/image/colorized/page_0001.jpg",
          "engine": "ResNeXt-50/101 Generator (MPS)",
          "translated": false,
          "adapter_used": true,
          "series_key": "one_piece",
          "processed_count": 1,
          "total_pages": 12
        }
        """.data(using: .utf8)!
        let preview = try decoder.decode(PreviewResultDTO.self, from: previewJSON)
        XCTAssertEqual(preview.status, "success")
        XCTAssertEqual(preview.pageIndex, 0)
        XCTAssertTrue(preview.adapterUsed)
        XCTAssertEqual(preview.seriesKey, "one_piece")

        let paletteJSON = """
        {
          "preset_id": "one_piece",
          "preset_title": "One Piece",
          "characters": [
            {
              "name": "Monkey D. Luffy",
              "hair_hex": "#1A1A1A",
              "skin_hex": "#F2C6A0",
              "costume_hex": "#D92525",
              "extra_hex": "#E8B931",
              "eye_hex": "#2B2118",
              "notes": "Straw hat with red band"
            }
          ]
        }
        """.data(using: .utf8)!
        let palette = try decoder.decode(CharacterPaletteDTO.self, from: paletteJSON)
        XCTAssertEqual(palette.presetId, "one_piece")
        XCTAssertEqual(palette.characters.count, 1)
        XCTAssertEqual(palette.characters[0].hairHex, "#1A1A1A")

        let memoryJSON = """
        {
          "status": "ok",
          "session_id": "s1",
          "series_key": "one_piece",
          "title": "One Piece",
          "memory": {
            "series_key": "one_piece",
            "title": "One Piece",
            "approved_pages_count": 5,
            "auto_learned_count": 3,
            "auto_refine_enabled": true,
            "auto_harvest_threshold": 0.85,
            "auto_refine_interval": 5,
            "unrefined_pages_count": 2,
            "exemplar_pages": [
              {
                "page_index": 3,
                "session_id": "s1",
                "character_names": ["Monkey D. Luffy"],
                "pinned": true,
                "style": "shonen_vivid"
              }
            ]
          }
        }
        """.data(using: .utf8)!
        let memResp = try decoder.decode(SeriesMemoryResponseDTO.self, from: memoryJSON)
        XCTAssertEqual(memResp.seriesKey, "one_piece")
        XCTAssertEqual(memResp.memory?.approvedPagesCount, 5)
        XCTAssertEqual(memResp.memory?.exemplarPages.first?.pinned, true)
    }

    func testAIProvidersAndVariantsMatchWebStudio() {
        XCTAssertEqual(AIProvider.allCases.count, 4)
        XCTAssertEqual(AIProvider.resnextGenerator.variants.count, 3)
        XCTAssertEqual(AIProvider.googleNano.variants.count, 6)
        XCTAssertEqual(AIProvider.appleFoundation.variants.count, 3)
        XCTAssertEqual(AIProvider.localSmart.variants.count, 3)
        XCTAssertTrue(AIProvider.googleNano.requiresAPIKey)
        XCTAssertFalse(AIProvider.resnextGenerator.requiresAPIKey)
        XCTAssertEqual(AIProvider.resnextGenerator.defaultModelName, "resnext-v2-manga")
    }

    func testKeychainInMemoryLifecycle() {
        let keychain = KeychainHelper(inMemory: true)
        XCTAssertNil(keychain.read(key: KeychainHelper.geminiAPIKeyAccount))
        XCTAssertTrue(keychain.save(key: KeychainHelper.geminiAPIKeyAccount, value: "secret-test-key-1"))
        XCTAssertEqual(keychain.read(key: KeychainHelper.geminiAPIKeyAccount), "secret-test-key-1")
        XCTAssertTrue(keychain.save(key: KeychainHelper.geminiAPIKeyAccount, value: "secret-test-key-2"))
        XCTAssertEqual(keychain.read(key: KeychainHelper.geminiAPIKeyAccount), "secret-test-key-2")
        XCTAssertTrue(keychain.delete(key: KeychainHelper.geminiAPIKeyAccount))
        XCTAssertNil(keychain.read(key: KeychainHelper.geminiAPIKeyAccount))
    }
}
