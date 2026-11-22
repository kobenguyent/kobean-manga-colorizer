import Foundation

public struct SemanticVersion: Equatable, Hashable, Comparable, Codable, CustomStringConvertible, Sendable {
    public let major: Int
    public let minor: Int
    public let patch: Int
    public let prerelease: [String]

    public init(major: Int, minor: Int, patch: Int, prerelease: [String] = []) {
        self.major = major
        self.minor = minor
        self.patch = patch
        self.prerelease = prerelease
    }

    public init?(parsing raw: String) {
        var cleaned = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if cleaned.hasPrefix("v") || cleaned.hasPrefix("V") {
            cleaned.removeFirst()
        }
        if let plusIdx = cleaned.firstIndex(of: "+") {
            cleaned = String(cleaned[..<plusIdx])
        }

        let dashParts = cleaned.split(separator: "-", maxSplits: 1).map(String.init)
        let coreParts = dashParts[0].split(separator: ".").map(String.init)
        guard !coreParts.isEmpty, coreParts.count <= 3 else { return nil }
        guard let major = Int(coreParts[0]), major >= 0 else { return nil }
        let minor = coreParts.count >= 2 ? Int(coreParts[1]) : 0
        let patch = coreParts.count == 3 ? Int(coreParts[2]) : 0
        guard let minor, minor >= 0, let patch, patch >= 0 else { return nil }

        let prerelease: [String] = dashParts.count > 1
            ? dashParts[1].split(separator: ".").map(String.init).filter { !$0.isEmpty }
            : []

        self.init(major: major, minor: minor, patch: patch, prerelease: prerelease)
    }

    public var isPrerelease: Bool {
        !prerelease.isEmpty
    }

    public var description: String {
        let core = "\(major).\(minor).\(patch)"
        return prerelease.isEmpty ? core : "\(core)-\(prerelease.joined(separator: "."))"
    }

    public static func < (lhs: SemanticVersion, rhs: SemanticVersion) -> Bool {
        if lhs.major != rhs.major { return lhs.major < rhs.major }
        if lhs.minor != rhs.minor { return lhs.minor < rhs.minor }
        if lhs.patch != rhs.patch { return lhs.patch < rhs.patch }

        if lhs.prerelease.isEmpty && rhs.prerelease.isEmpty { return false }
        if lhs.prerelease.isEmpty { return false }
        if rhs.prerelease.isEmpty { return true }

        let count = max(lhs.prerelease.count, rhs.prerelease.count)
        for i in 0..<count {
            if i >= lhs.prerelease.count { return true }
            if i >= rhs.prerelease.count { return false }
            let l = lhs.prerelease[i]
            let r = rhs.prerelease[i]
            if l == r { continue }
            switch (Int(l), Int(r)) {
            case let (li?, ri?): return li < ri
            case (_?, nil): return true
            case (nil, _?): return false
            default: return l < r
            }
        }
        return false
    }
}
