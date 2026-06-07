#pragma once

#include <optional>
#include <string>
#include <vector>

namespace light_config {

/// Machine-readable error codes for config loading failures.
///
/// The numeric values are stable — integrations may depend on them.
/// Always check code != kOk, never check specific integer values.
enum class ErrorCode {
    kOk = 0,                          ///< Success.

    // ---- File I/O errors ----
    kFileReadError = 1,               ///< Cannot access or stat the file.
    kFileEmpty = 2,                   ///< File exists but is empty.

    // ---- Parse errors ----
    kJsonParseError = 10,             ///< JSON syntax or structural error.
    kJsonDeserializeError = 11,       ///< JSON parsed OK but struct population failed.
    kYamlParseError = 20,             ///< YAML syntax or structural error.

    // ---- Validation errors ----
    kValidationError = 30,            ///< Config values out of allowed range.
};

/// Human-readable description for an ErrorCode.
/// Returns empty string for kOk.
constexpr const char* error_code_message(ErrorCode code) noexcept {
    switch (code) {
    case ErrorCode::kOk:                   return "";
    case ErrorCode::kFileReadError:        return "file read error";
    case ErrorCode::kFileEmpty:            return "file is empty";
    case ErrorCode::kJsonParseError:       return "JSON parse error";
    case ErrorCode::kJsonDeserializeError: return "JSON deserialize error";
    case ErrorCode::kYamlParseError:       return "YAML parse error";
    case ErrorCode::kValidationError:      return "validation error";
    }
    return "unknown error";
}

/// Format of the config file.
enum class Format {
    Auto,   ///< Detect from file extension.
    Json,   ///< JSON format (uses iguana::from_json).
    Yaml    ///< YAML format (uses iguana::from_yaml).
};

/// Result of loading a config file.
///
/// On success: code == kOk, absent_optionals and present_fields are populated.
/// On failure: code != kOk, message carries detail suitable for logging.
struct LoadResult {
    ErrorCode code = ErrorCode::kOk;

    /// Human-readable detail. Set when code != kOk; may be empty.
    std::string message;

    /// Shortcut: true when code == kOk.
    bool ok() const noexcept { return code == ErrorCode::kOk; }

    /// std::optional fields that were NOT present in the config file.
    ///
    /// JSON: accurate (DOM-level key check).
    /// YAML: fields that were std::nullopt after loading (conflates
    ///       explicit null with missing key).
    std::vector<std::string> absent_optionals;

    /// Fields found in the config file.
    std::vector<std::string> present_fields;

    /// Factory: success result.
    static LoadResult success() {
        return LoadResult{};
    }

    /// Factory: failure with an error code and optional message.
    static LoadResult failure(ErrorCode c, std::string msg = "") {
        LoadResult r;
        r.code = c;
        r.message = std::move(msg);
        return r;
    }
};

// ---- Shared type traits ----

namespace detail {

template <typename T>
struct is_optional : std::false_type {};

template <typename T>
struct is_optional<std::optional<T>> : std::true_type {};

template <typename T>
inline constexpr bool is_optional_v = is_optional<T>::value;

}  // namespace detail

}  // namespace light_config
