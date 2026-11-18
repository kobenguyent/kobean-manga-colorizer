// swift-tools-version: 5.10
import PackageDescription

let package = Package(
    name: "KobeanMangaColorizer",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .library(
            name: "KobeanMangaCore",
            targets: ["KobeanMangaCore"]
        ),
        .executable(
            name: "KobeanMangaApp",
            targets: ["KobeanMangaApp"]
        )
    ],
    targets: [
        .target(
            name: "KobeanMangaCore",
            path: "Sources/KobeanMangaCore"
        ),
        .executableTarget(
            name: "KobeanMangaApp",
            dependencies: ["KobeanMangaCore"],
            path: "Sources/KobeanMangaApp"
        ),
        .testTarget(
            name: "KobeanMangaTests",
            dependencies: ["KobeanMangaCore"],
            path: "Tests/KobeanMangaTests"
        )
    ]
)
