import XCTest
@testable import KobeanMangaCore

final class SSEParserTests: XCTestCase {
    func testParseAllColorizeSSEEvents() {
        let initLine = #"data: {"type":"init","is_active":true,"uncolorized_count":4,"session":{"session_id":"s1","filename":"Vol1.cbz","total_pages":10,"processed_count":6,"status":"processing","pages":[]}}"#
        guard case let .initial(session, isActive, uncolorizedCount)? = SSEParser.parseColorizeLine(initLine) else {
            return XCTFail("Expected .initial event")
        }
        XCTAssertEqual(session?.sessionId, "s1")
        XCTAssertTrue(isActive)
        XCTAssertEqual(uncolorizedCount, 4)

        let startLine = #"data: {"type":"start","total":10,"model_provider":"resnext_generator","model_name":"resnext-v2-manga"}"#
        guard case let .start(total, provider, modelName)? = SSEParser.parseColorizeLine(startLine) else {
            return XCTFail("Expected .start event")
        }
        XCTAssertEqual(total, 10)
        XCTAssertEqual(provider, "resnext_generator")
        XCTAssertEqual(modelName, "resnext-v2-manga")

        let pageUpdateLine = #"data: {"type":"page_update","page_index":2,"status":"colorized","skipped_colored":false,"colorized_url":"/api/session/s1/image/colorized/page_0003.jpg","engine":"ResNeXt","adapter_used":true,"auto_harvested":true,"processed_count":7,"total":10,"translated":true,"quality_score":{"overall_score":0.91,"grade":"high","auto_learn_eligible":true,"metrics":{"linework_integrity":0.95,"white_purity":0.90,"color_richness":0.88}}}"#
        guard case let .pageUpdate(payload)? = SSEParser.parseColorizeLine(pageUpdateLine) else {
            return XCTFail("Expected .pageUpdate event")
        }
        XCTAssertEqual(payload.pageIndex, 2)
        XCTAssertEqual(payload.status, "colorized")
        XCTAssertTrue(payload.adapterUsed)
        XCTAssertTrue(payload.autoHarvested)
        XCTAssertEqual(payload.processedCount, 7)
        XCTAssertEqual(payload.qualityScore?.overall ?? 0, 0.91, accuracy: 0.001)

        let adapterLine = #"data: {"type":"adapter_training_progress","series_key":"dr_slump","step":30,"total_steps":100,"progress":30.0,"loss":0.0412,"status":"training","auto_refine":true}"#
        guard case let .adapterTrainingProgress(adapterPayload)? = SSEParser.parseColorizeLine(adapterLine) else {
            return XCTFail("Expected .adapterTrainingProgress event")
        }
        XCTAssertEqual(adapterPayload.seriesKey, "dr_slump")
        XCTAssertEqual(adapterPayload.step, 30)
        XCTAssertEqual(adapterPayload.totalSteps, 100)
        XCTAssertTrue(adapterPayload.autoRefine)

        guard case let .completed(totalProcessed, _)? = SSEParser.parseColorizeLine(#"data: {"type":"completed","total_processed":10}"#) else {
            return XCTFail("Expected .completed event")
        }
        XCTAssertEqual(totalProcessed, 10)

        guard case let .idle(idleProcessed, idleTotal)? = SSEParser.parseColorizeLine(#"data: {"type":"idle","total_processed":6,"total":10}"#) else {
            return XCTFail("Expected .idle event")
        }
        XCTAssertEqual(idleProcessed, 6)
        XCTAssertEqual(idleTotal, 10)

        guard case let .cancelled(cancelledProcessed, cancelledTotal)? = SSEParser.parseColorizeLine(#"data: {"type":"cancelled","processed_count":4,"total":10}"#) else {
            return XCTFail("Expected .cancelled event")
        }
        XCTAssertEqual(cancelledProcessed, 4)
        XCTAssertEqual(cancelledTotal, 10)

        guard case let .error(message)? = SSEParser.parseColorizeLine(#"data: {"type":"error","error":"MPS out of memory"}"#) else {
            return XCTFail("Expected .error event")
        }
        XCTAssertEqual(message, "MPS out of memory")
    }

    func testParseCombinedExportSSEEvents() {
        let initLine = #"data: {"type":"init","job_id":"job-1","status":"processing","progress":{"percent":0,"processed_pages":0,"total_pages":120,"status":"Starting..."}}"#
        guard case let .initial(jobId, status, progress)? = SSEParser.parseCombinedExportLine(initLine) else {
            return XCTFail("Expected combined .initial event")
        }
        XCTAssertEqual(jobId, "job-1")
        XCTAssertEqual(status, "processing")
        XCTAssertEqual(progress.totalPages, 120)

        let progressLine = #"data: {"type":"progress","job_id":"job-1","percent":45,"processed_pages":54,"total_pages":120,"status":"Volume 2/4: Page 12"}"#
        guard case let .progress(progPayload)? = SSEParser.parseCombinedExportLine(progressLine) else {
            return XCTFail("Expected combined .progress event")
        }
        XCTAssertEqual(progPayload.percent, 45)
        XCTAssertEqual(progPayload.processedPages, 54)

        let completedLine = #"data: {"type":"completed","job_id":"job-1","download_url":"/api/download/combined/SlamDunk.epub","filename":"SlamDunk.epub","total_volumes":4,"title":"Slam Dunk"}"#
        guard case let .completed(cJobId, dlUrl, filename, vols, title)? = SSEParser.parseCombinedExportLine(completedLine) else {
            return XCTFail("Expected combined .completed event")
        }
        XCTAssertEqual(cJobId, "job-1")
        XCTAssertEqual(dlUrl, "/api/download/combined/SlamDunk.epub")
        XCTAssertEqual(filename, "SlamDunk.epub")
        XCTAssertEqual(vols, 4)
        XCTAssertEqual(title, "Slam Dunk")

        guard case .cancelled("job-1", _)? = SSEParser.parseCombinedExportLine(#"data: {"type":"cancelled","job_id":"job-1"}"#) else {
            return XCTFail("Expected combined .cancelled event")
        }

        guard case let .error("job-1", msg)? = SSEParser.parseCombinedExportLine(#"data: {"type":"error","job_id":"job-1","error":"Disk full"}"#) else {
            return XCTFail("Expected combined .error event")
        }
        XCTAssertEqual(msg, "Disk full")
    }

    func testIgnoreNonDataAndMalformedLines() {
        XCTAssertNil(SSEParser.parseColorizeLine(""))
        XCTAssertNil(SSEParser.parseColorizeLine(": ping"))
        XCTAssertNil(SSEParser.parseColorizeLine("event: message"))
        XCTAssertNil(SSEParser.parseColorizeLine("data: not-valid-json"))
        XCTAssertNil(SSEParser.parseCombinedExportLine("data: {\"type\":\"unknown_type\"}"))
    }
}
