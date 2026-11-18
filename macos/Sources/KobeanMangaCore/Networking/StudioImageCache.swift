import AppKit
import Foundation
import ImageIO

/// Thread-safe decoded image cache with off-main-thread ImageIO thumbnail downsampling
/// and HTTP pipelined prefetching.
public final class StudioImageCache: @unchecked Sendable {
    public static let shared = StudioImageCache()

    private let cache = NSCache<NSString, NSImage>()
    private let session: URLSession

    public init(session: URLSession? = nil) {
        self.cache.countLimit = 200
        self.cache.totalCostLimit = 256 * 1024 * 1024

        if let session {
            self.session = session
        } else {
            let cfg = URLSessionConfiguration.default
            cfg.urlCache = URLCache(
                memoryCapacity: 64 * 1024 * 1024,
                diskCapacity: 256 * 1024 * 1024
            )
            cfg.httpMaximumConnectionsPerHost = 8
            cfg.timeoutIntervalForRequest = 60
            self.session = URLSession(configuration: cfg)
        }
    }

    public static func cacheKey(for url: URL, maxPixelDimension: CGFloat?) -> String {
        if let dim = maxPixelDimension, dim > 0 {
            return "\(url.absoluteString)#\(Int(dim.rounded()))"
        }
        return url.absoluteString
    }

    public static func decodeImage(data: Data, maxPixelDimension: CGFloat?) -> NSImage? {
        guard !data.isEmpty else { return nil }

        if let dim = maxPixelDimension, dim > 0 {
            let maxPx = max(1, Int(dim.rounded()))
            if let source = CGImageSourceCreateWithData(data as CFData, nil) {
                let options: [CFString: Any] = [
                    kCGImageSourceCreateThumbnailFromImageAlways: true,
                    kCGImageSourceCreateThumbnailWithTransform: true,
                    kCGImageSourceShouldCacheImmediately: true,
                    kCGImageSourceThumbnailMaxPixelSize: maxPx,
                ]
                if let cgImage = CGImageSourceCreateThumbnailAtIndex(source, 0, options as CFDictionary) {
                    return NSImage(
                        cgImage: cgImage,
                        size: NSSize(width: cgImage.width, height: cgImage.height)
                    )
                }
            }
        }

        if let source = CGImageSourceCreateWithData(data as CFData, nil) {
            let options: [CFString: Any] = [
                kCGImageSourceShouldCacheImmediately: true,
            ]
            if let cgImage = CGImageSourceCreateImageAtIndex(source, 0, options as CFDictionary) {
                return NSImage(
                    cgImage: cgImage,
                    size: NSSize(width: cgImage.width, height: cgImage.height)
                )
            }
        }

        return NSImage(data: data)
    }

    public func image(for url: URL, maxPixelDimension: CGFloat? = nil) -> NSImage? {
        let key = Self.cacheKey(for: url, maxPixelDimension: maxPixelDimension) as NSString
        return cache.object(forKey: key)
    }

    public func store(_ image: NSImage, for url: URL, maxPixelDimension: CGFloat? = nil) {
        let key = Self.cacheKey(for: url, maxPixelDimension: maxPixelDimension) as NSString
        let cost = Int(max(1, image.size.width * image.size.height * 4))
        cache.setObject(image, forKey: key, cost: cost)
    }

    public func loadImage(from url: URL, maxPixelDimension: CGFloat? = nil) async throws -> NSImage {
        if let cached = image(for: url, maxPixelDimension: maxPixelDimension) {
            return cached
        }

        let (data, response) = try await session.data(from: url)
        if let http = response as? HTTPURLResponse, !(200...299).contains(http.statusCode) {
            throw StudioAPIError.httpError(statusCode: http.statusCode, detail: "Image request failed")
        }

        let decoded: NSImage? = await Task.detached(priority: .userInitiated) {
            Self.decodeImage(data: data, maxPixelDimension: maxPixelDimension)
        }.value

        guard let decoded else {
            throw StudioAPIError.decodingError("Could not decode image data")
        }
        store(decoded, for: url, maxPixelDimension: maxPixelDimension)
        return decoded
    }

    public func prefetch(urls: [URL], maxPixelDimension: CGFloat? = nil) async {
        let pending = urls.filter { image(for: $0, maxPixelDimension: maxPixelDimension) == nil }
        guard !pending.isEmpty else { return }

        await withTaskGroup(of: Void.self) { group in
            for url in pending {
                group.addTask { [self] in
                    _ = try? await self.loadImage(from: url, maxPixelDimension: maxPixelDimension)
                }
            }
        }
    }
}
