import Foundation
import Security

public protocol KeychainHelperProtocol: Sendable {
    @discardableResult
    func save(key: String, value: String, service: String) -> Bool
    func read(key: String, service: String) -> String?
    @discardableResult
    func delete(key: String, service: String) -> Bool
}

public extension KeychainHelperProtocol {
    @discardableResult
    func save(key: String, value: String) -> Bool {
        save(key: key, value: value, service: KeychainHelper.defaultService)
    }

    func read(key: String) -> String? {
        read(key: key, service: KeychainHelper.defaultService)
    }

    @discardableResult
    func delete(key: String) -> Bool {
        delete(key: key, service: KeychainHelper.defaultService)
    }
}

/// SecItem-backed secret storage for API keys (T-01 threat mitigation),
/// with an optional in-memory backing store for isolated unit tests.
public final class KeychainHelper: KeychainHelperProtocol, @unchecked Sendable {
    public static let defaultService = "ai.kobean.manga-colorizer"
    public static let geminiAPIKeyAccount = "gemini_api_key"
    public static let shared = KeychainHelper()

    private let inMemory: Bool
    private let lock = NSLock()
    private var memoryStore: [String: String] = [:]

    public init(inMemory: Bool = false) {
        self.inMemory = inMemory
    }

    @discardableResult
    public func save(key: String, value: String, service: String = KeychainHelper.defaultService) -> Bool {
        if inMemory {
            lock.lock()
            memoryStore["\(service)::\(key)"] = value
            lock.unlock()
            return true
        }

        let data = Data(value.utf8)
        let baseQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key
        ]

        var addQuery = baseQuery
        addQuery[kSecValueData as String] = data
        addQuery[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlock

        let status = SecItemAdd(addQuery as CFDictionary, nil)
        if status == errSecSuccess {
            return true
        }

        if status == errSecDuplicateItem {
            let updateAttributes: [String: Any] = [
                kSecValueData as String: data
            ]
            return SecItemUpdate(baseQuery as CFDictionary, updateAttributes as CFDictionary) == errSecSuccess
        }

        return false
    }

    public func read(key: String, service: String = KeychainHelper.defaultService) -> String? {
        if inMemory {
            lock.lock()
            let val = memoryStore["\(service)::\(key)"]
            lock.unlock()
            return val
        }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    @discardableResult
    public func delete(key: String, service: String = KeychainHelper.defaultService) -> Bool {
        if inMemory {
            lock.lock()
            memoryStore.removeValue(forKey: "\(service)::\(key)")
            lock.unlock()
            return true
        }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key
        ]
        let status = SecItemDelete(query as CFDictionary)
        return status == errSecSuccess || status == errSecItemNotFound
    }
}
