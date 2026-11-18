#!/usr/bin/env swift
import AppKit
import CoreGraphics
import Foundation

struct IconSpec {
    let filename: String
    let pixelSize: Int
}

let iconSpecs: [IconSpec] = [
    IconSpec(filename: "icon_16x16.png", pixelSize: 16),
    IconSpec(filename: "icon_16x16@2x.png", pixelSize: 32),
    IconSpec(filename: "icon_32x32.png", pixelSize: 32),
    IconSpec(filename: "icon_32x32@2x.png", pixelSize: 64),
    IconSpec(filename: "icon_128x128.png", pixelSize: 128),
    IconSpec(filename: "icon_128x128@2x.png", pixelSize: 256),
    IconSpec(filename: "icon_256x256.png", pixelSize: 256),
    IconSpec(filename: "icon_256x256@2x.png", pixelSize: 512),
    IconSpec(filename: "icon_512x512.png", pixelSize: 512),
    IconSpec(filename: "icon_512x512@2x.png", pixelSize: 1024),
]

let args = CommandLine.arguments
let outputIcnsPath = args.count > 1 ? args[1] : "macos/AppIcon.icns"
let brandPngPath = args.count > 2 ? args[2] : "static/brand-icon.png"

let fm = FileManager.default
let outputURL = URL(fileURLWithPath: outputIcnsPath).standardizedFileURL
let brandURL = URL(fileURLWithPath: brandPngPath).standardizedFileURL
let brandImage = fm.fileExists(atPath: brandURL.path) ? NSImage(contentsOf: brandURL) : nil

let tempIconsetDir = fm.temporaryDirectory
    .appendingPathComponent("AppIcon-\(UUID().uuidString).iconset")

try fm.createDirectory(at: tempIconsetDir, withIntermediateDirectories: true)
defer { try? fm.removeItem(at: tempIconsetDir) }

func srgbColor(_ red: CGFloat, _ green: CGFloat, _ blue: CGFloat, _ alpha: CGFloat = 1.0) -> NSColor {
    NSColor(srgbRed: red / 255.0, green: green / 255.0, blue: blue / 255.0, alpha: alpha)
}

func renderIconPNG(pixelSize: Int, brandImage: NSImage?, to destinationURL: URL) throws {
    guard let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil,
        pixelsWide: pixelSize,
        pixelsHigh: pixelSize,
        bitsPerSample: 8,
        samplesPerPixel: 4,
        hasAlpha: true,
        isPlanar: false,
        colorSpaceName: .deviceRGB,
        bytesPerRow: 0,
        bitsPerPixel: 0
    ) else {
        throw NSError(domain: "IconGenerator", code: 1, userInfo: [NSLocalizedDescriptionKey: "Failed to allocate bitmap"])
    }
    rep.size = NSSize(width: pixelSize, height: pixelSize)

    guard let nsCtx = NSGraphicsContext(bitmapImageRep: rep) else {
        throw NSError(domain: "IconGenerator", code: 2, userInfo: [NSLocalizedDescriptionKey: "Failed to create graphics context"])
    }

    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = nsCtx
    let cg = nsCtx.cgContext
    cg.interpolationQuality = .high

    let size = CGFloat(pixelSize)
    let margin = size * 0.08
    let cardRect = NSRect(x: margin, y: margin, width: size - 2 * margin, height: size - 2 * margin)
    let cornerRadius = cardRect.width * 0.225
    let squirclePath = NSBezierPath(roundedRect: cardRect, xRadius: cornerRadius, yRadius: cornerRadius)

    // Drop shadow behind macOS squircle
    cg.saveGState()
    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.38)
    shadow.shadowOffset = NSSize(width: 0, height: -size * 0.02)
    shadow.shadowBlurRadius = size * 0.045
    shadow.set()
    srgbColor(9, 13, 22).setFill()
    squirclePath.fill()
    cg.restoreGState()

    // Clip to squircle for internal background, glows, and artwork
    cg.saveGState()
    squirclePath.addClip()

    // Base studio dark canvas (#090D16)
    srgbColor(9, 13, 22).setFill()
    NSBezierPath(rect: cardRect).fill()

    // Cyan (#06B6D4) top-left radial glow + Violet (#8B5CF6) bottom-right radial glow
    let colorSpace = CGColorSpaceCreateDeviceRGB()
    if let cyanGrad = CGGradient(
        colorsSpace: colorSpace,
        colors: [
            srgbColor(6, 182, 212, 0.38).cgColor,
            srgbColor(6, 182, 212, 0.0).cgColor,
        ] as CFArray,
        locations: [0.0, 1.0]
    ) {
        let center = CGPoint(x: cardRect.minX + cardRect.width * 0.26, y: cardRect.maxY - cardRect.height * 0.24)
        cg.drawRadialGradient(
            cyanGrad,
            startCenter: center,
            startRadius: 0,
            endCenter: center,
            endRadius: cardRect.width * 0.72,
            options: []
        )
    }

    if let violetGrad = CGGradient(
        colorsSpace: colorSpace,
        colors: [
            srgbColor(139, 92, 246, 0.36).cgColor,
            srgbColor(139, 92, 246, 0.0).cgColor,
        ] as CFArray,
        locations: [0.0, 1.0]
    ) {
        let center = CGPoint(x: cardRect.maxX - cardRect.width * 0.22, y: cardRect.minY + cardRect.height * 0.22)
        cg.drawRadialGradient(
            violetGrad,
            startCenter: center,
            startRadius: 0,
            endCenter: center,
            endRadius: cardRect.width * 0.72,
            options: []
        )
    }

    if let brandImage {
        let artPadding = cardRect.width * 0.14
        let artRect = cardRect.insetBy(dx: artPadding, dy: artPadding)
        brandImage.draw(
            in: artRect,
            from: NSRect(origin: .zero, size: brandImage.size),
            operation: .sourceOver,
            fraction: 1.0
        )
    } else {
        // Vector fallback: crisp manga panel frame + cyan/violet gradient brush stroke
        let panelInset = cardRect.width * 0.22
        let panelRect = cardRect.insetBy(dx: panelInset, dy: panelInset)
        let panelPath = NSBezierPath(roundedRect: panelRect, xRadius: size * 0.04, yRadius: size * 0.04)
        srgbColor(18, 24, 38, 0.92).setFill()
        panelPath.fill()
        srgbColor(6, 182, 212, 0.9).setStroke()
        panelPath.lineWidth = max(1.0, size * 0.03)
        panelPath.stroke()

        let slash = NSBezierPath()
        slash.move(to: NSPoint(x: panelRect.minX + panelRect.width * 0.2, y: panelRect.minY + panelRect.height * 0.22))
        slash.curve(
            to: NSPoint(x: panelRect.maxX - panelRect.width * 0.18, y: panelRect.maxY - panelRect.height * 0.22),
            controlPoint1: NSPoint(x: panelRect.midX, y: panelRect.maxY - panelRect.height * 0.2),
            controlPoint2: NSPoint(x: panelRect.midX, y: panelRect.minY + panelRect.height * 0.2)
        )
        slash.lineWidth = max(1.5, size * 0.065)
        slash.lineCapStyle = .round
        srgbColor(139, 92, 246).setStroke()
        slash.stroke()
    }

    cg.restoreGState()

    // Subtle specular rim highlight
    squirclePath.lineWidth = max(1.0, size * 0.012)
    srgbColor(255, 255, 255, 0.16).setStroke()
    squirclePath.stroke()

    NSGraphicsContext.restoreGraphicsState()

    guard let pngData = rep.representation(using: .png, properties: [:]) else {
        throw NSError(domain: "IconGenerator", code: 3, userInfo: [NSLocalizedDescriptionKey: "Failed to encode PNG"])
    }
    try pngData.write(to: destinationURL)
}

for spec in iconSpecs {
    let dest = tempIconsetDir.appendingPathComponent(spec.filename)
    try renderIconPNG(pixelSize: spec.pixelSize, brandImage: brandImage, to: dest)
}

try fm.createDirectory(at: outputURL.deletingLastPathComponent(), withIntermediateDirectories: true)
if fm.fileExists(atPath: outputURL.path) {
    try fm.removeItem(at: outputURL)
}

let iconutil = Process()
iconutil.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
iconutil.arguments = ["-c", "icns", tempIconsetDir.path, "-o", outputURL.path]
try iconutil.run()
iconutil.waitUntilExit()

guard iconutil.terminationStatus == 0,
      fm.fileExists(atPath: outputURL.path),
      let attrs = try? fm.attributesOfItem(atPath: outputURL.path),
      (attrs[.size] as? NSNumber)?.intValue ?? 0 > 0 else {
    fputs("Error: iconutil failed to generate \(outputURL.path)\n", stderr)
    exit(1)
}

print("Generated macOS icon: \(outputURL.path)")
