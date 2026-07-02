#include <light_config/light_config.hpp>

#include <cassert>
#include <iostream>
#include <optional>
#include <string>
#include <vector>

#include <fstream>

/// Config struct exercising various types.
struct TestConfig {
    std::string name;
    int value = 0;
    bool flag = false;
    double ratio = 1.0;
    std::optional<std::string> opt_str;
    std::optional<int> opt_int;
    std::optional<double> opt_double;
    std::vector<int> numbers;
    std::vector<std::string> tags;
};
YLT_REFL(TestConfig, name, value, flag, ratio, opt_str, opt_int, opt_double, numbers, tags);

// A struct with all optional fields.
struct AllOptionalConfig {
    std::optional<std::string> opt_a;
    std::optional<int> opt_b;
};
YLT_REFL(AllOptionalConfig, opt_a, opt_b);

// A struct with no optional fields.
struct NoOptionalConfig {
    std::string a;
    int b = 0;
};
YLT_REFL(NoOptionalConfig, a, b);

// ---- Nested struct for recursive audit testing ----

struct InnerCfg {
    std::string host = "default";
    std::optional<int> port;
};
YLT_REFL(InnerCfg, host, port);

struct OuterCfg {
    std::string app_name;
    int version = 1;
    InnerCfg inner;
};
YLT_REFL(OuterCfg, app_name, version, inner);

// ---- Struct for schema version testing ----

struct VersionedConfig {
    std::string name;
    int value = 0;
};
YLT_REFL(VersionedConfig, name, value);
// Simulates what gen_config.py emits:
constexpr std::string_view kVersionedConfigSchemaVersion{"2.0.0"};

// ---- JSON Tests ----

void test_json_all_fields_present() {
    TestConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "name": "test",
        "value": 42,
        "flag": true,
        "ratio": 2.5,
        "opt_str": "hello",
        "opt_int": 99,
        "opt_double": 1.5,
        "numbers": [1, 2, 3],
        "tags": ["a", "b"]
    })");
    assert(r.ok());
    assert(r.code == light_config::ErrorCode::kOk);
    assert(cfg.name == "test");
    assert(cfg.value == 42);
    assert(cfg.flag);
    assert(cfg.ratio == 2.5);
    assert(cfg.opt_str.has_value() && cfg.opt_str.value() == "hello");
    assert(cfg.opt_int.has_value() && cfg.opt_int.value() == 99);
    assert(cfg.opt_double.has_value() && cfg.opt_double.value() == 1.5);
    assert(cfg.numbers.size() == 3);
    assert(cfg.tags.size() == 2);
    assert(r.absent_optionals.empty());
    assert(r.present_fields.size() == 9);
    std::cout << "[PASS] JSON all fields present.\n";
}

void test_json_some_optionals_absent() {
    TestConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "name": "minimal",
        "value": 1,
        "flag": false
    })");
    assert(r.ok());
    assert(cfg.name == "minimal");
    assert(cfg.value == 1);
    assert(cfg.flag == false);
    assert(!cfg.opt_str.has_value());
    assert(!cfg.opt_int.has_value());
    assert(!cfg.opt_double.has_value());
    assert(r.absent_optionals.size() == 3);
    assert(r.present_fields.size() == 3);
    std::cout << "[PASS] JSON optional fields absent.\n";
}

void test_json_optional_explicit_null() {
    AllOptionalConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "opt_a": null,
        "opt_b": 5
    })");
    assert(r.ok());
    assert(!cfg.opt_a.has_value());
    assert(cfg.opt_b.has_value() && cfg.opt_b.value() == 5);
    assert(r.present_fields.size() == 2);
    assert(r.absent_optionals.empty());
    std::cout << "[PASS] JSON optional explicit null = present.\n";
}

void test_json_all_optional() {
    AllOptionalConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({})");
    assert(r.ok());
    assert(!cfg.opt_a.has_value());
    assert(!cfg.opt_b.has_value());
    assert(r.absent_optionals.size() == 2);
    assert(r.present_fields.empty());
    std::cout << "[PASS] JSON empty object.\n";
}

void test_json_no_optionals() {
    NoOptionalConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({"a": "x", "b": 10})");
    assert(r.ok());
    assert(cfg.a == "x");
    assert(cfg.b == 10);
    assert(r.absent_optionals.empty());
    assert(r.present_fields.size() == 2);
    std::cout << "[PASS] JSON no optional fields.\n";
}

void test_json_parse_error() {
    TestConfig cfg;
    auto r = light_config::load_from_json_string(cfg, "{invalid");
    assert(!r.ok());
    assert(r.code == light_config::ErrorCode::kJsonParseError);
    assert(!r.message.empty());
    std::cout << "[PASS] JSON parse error reported: " << r.message << "\n";
}

void test_json_missing_file() {
    TestConfig cfg;
    auto r = light_config::load_from_json_file(cfg, "/nonexistent/path.json");
    assert(!r.ok());
    assert(r.code == light_config::ErrorCode::kFileReadError);
    assert(!r.message.empty());
    std::cout << "[PASS] JSON missing file error reported.\n";
}

// ---- Nested struct tests ----

void test_json_nested_all_present() {
    OuterCfg cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "app_name": "myapp",
        "version": 2,
        "inner": {
            "host": "10.0.0.1",
            "port": 9999
        }
    })");
    assert(r.ok());
    assert(cfg.app_name == "myapp");
    assert(cfg.version == 2);
    assert(cfg.inner.host == "10.0.0.1");
    assert(cfg.inner.port.has_value() && cfg.inner.port.value() == 9999);
    // Check dot-separated field paths for nested fields
    assert(r.present_fields.size() == 5);  // app_name, version, inner, inner.host, inner.port
    assert(r.absent_optionals.empty());
    std::cout << "[PASS] JSON nested struct all present.\n";
}

void test_json_nested_some_absent() {
    OuterCfg cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "app_name": "myapp",
        "inner": {
            "host": "10.0.0.1"
        }
    })");
    assert(r.ok());
    assert(cfg.app_name == "myapp");
    assert(cfg.inner.host == "10.0.0.1");
    assert(!cfg.inner.port.has_value());
    // inner.port is absent from JSON
    auto has_port_absent = false;
    for (auto& name : r.absent_optionals) {
        if (name == "inner.port") {
            has_port_absent = true;
        }
    }
    assert(has_port_absent);
    std::cout << "[PASS] JSON nested struct: inner.port absent.\n";
}

// ---- Round-Trip Tests ----

void test_json_roundtrip_basic() {
    // Populate a config struct with known values.
    TestConfig original;
    original.name = "roundtrip";
    original.value = 42;
    original.flag = true;
    original.ratio = 3.14;
    original.opt_str = "hello";
    original.opt_int = 99;
    original.opt_double = 1.5;
    original.numbers = {1, 2, 3};
    original.tags = {"x", "y"};

    // Serialize to JSON.
    auto json_opt = light_config::to_json(original);
    assert(json_opt.has_value());

    // Re-parse into a fresh struct.
    TestConfig parsed;
    auto r = light_config::load_from_json_string(parsed, json_opt.value());
    assert(r.ok());

    // Compare every field.
    assert(parsed.name == original.name);
    assert(parsed.value == original.value);
    assert(parsed.flag == original.flag);
    assert(parsed.ratio == original.ratio);
    assert(parsed.opt_str.has_value() && parsed.opt_str.value() == "hello");
    assert(parsed.opt_int.has_value() && parsed.opt_int.value() == 99);
    assert(parsed.opt_double.has_value() && parsed.opt_double.value() == 1.5);
    assert(parsed.numbers.size() == 3);
    assert(parsed.numbers[0] == 1 && parsed.numbers[1] == 2 && parsed.numbers[2] == 3);
    assert(parsed.tags.size() == 2);
    assert(parsed.tags[0] == "x" && parsed.tags[1] == "y");
    std::cout << "[PASS] Round-trip: JSON basic serialization + re-parse.\n";
}

void test_json_roundtrip_pretty() {
    TestConfig original;
    original.name = "pretty_test";
    original.value = 7;
    original.flag = false;
    original.ratio = 2.0;
    original.opt_str = "present";
    original.opt_int = 10;
    original.opt_double = 3.5;
    original.numbers = {1, 2};
    original.tags = {"x"};

    // Serialize with pretty-printing.
    auto json_opt = light_config::to_json(original, true);
    assert(json_opt.has_value());

    // Pretty JSON should contain newlines.
    assert(json_opt.value().find('\n') != std::string::npos);

    // Re-parse and verify data survives the round-trip.
    TestConfig parsed;
    auto r = light_config::load_from_json_string(parsed, json_opt.value());
    assert(r.ok());
    assert(parsed.name == original.name);
    assert(parsed.value == original.value);
    assert(parsed.flag == original.flag);
    assert(parsed.ratio == original.ratio);
    assert(parsed.opt_str.has_value() && parsed.opt_str.value() == "present");
    assert(parsed.opt_int.has_value() && parsed.opt_int.value() == 10);
    assert(parsed.opt_double.has_value() && parsed.opt_double.value() == 3.5);
    assert(parsed.numbers.size() == 2);
    assert(parsed.tags.size() == 1);
    std::cout << "[PASS] Round-trip: JSON pretty-print survives re-parse.\n";
}

void test_json_roundtrip_all_optionals() {
    // All optional fields populated.
    AllOptionalConfig original;
    original.opt_a = "alpha";
    original.opt_b = 100;

    auto json_opt = light_config::to_json(original);
    assert(json_opt.has_value());

    AllOptionalConfig parsed;
    auto r = light_config::load_from_json_string(parsed, json_opt.value());
    assert(r.ok());
    assert(parsed.opt_a.has_value() && parsed.opt_a.value() == "alpha");
    assert(parsed.opt_b.has_value() && parsed.opt_b.value() == 100);

    // All optional fields empty.
    AllOptionalConfig empty;
    json_opt = light_config::to_json(empty);
    assert(json_opt.has_value());

    AllOptionalConfig parsed_empty;
    r = light_config::load_from_json_string(parsed_empty, json_opt.value());
    assert(r.ok());
    assert(!parsed_empty.opt_a.has_value());
    assert(!parsed_empty.opt_b.has_value());
    std::cout << "[PASS] Round-trip: JSON all-optional struct (filled + empty).\n";
}

void test_json_roundtrip_nested() {
    OuterCfg original;
    original.app_name = "nested_app";
    original.version = 3;
    original.inner.host = "192.168.1.1";
    original.inner.port = 8080;

    auto json_opt = light_config::to_json(original);
    assert(json_opt.has_value());

    OuterCfg parsed;
    auto r = light_config::load_from_json_string(parsed, json_opt.value());
    assert(r.ok());
    assert(parsed.app_name == original.app_name);
    assert(parsed.version == original.version);
    assert(parsed.inner.host == original.inner.host);
    assert(parsed.inner.port.has_value() && parsed.inner.port.value() == 8080);
    std::cout << "[PASS] Round-trip: JSON nested struct survives re-parse.\n";
}

void test_yaml_roundtrip_basic() {
    TestConfig original;
    original.name = "yaml_rt";
    original.value = 99;
    original.flag = true;
    original.ratio = 1.0;
    original.opt_str = "yamltest";
    original.numbers = {10, 20};
    original.tags = {"a", "b", "c"};

    auto yaml_opt = light_config::to_yaml(original);
    assert(yaml_opt.has_value());

    TestConfig parsed;
    auto r = light_config::load_from_yaml_string(parsed, yaml_opt.value());
    assert(r.ok());
    assert(parsed.name == original.name);
    assert(parsed.value == original.value);
    assert(parsed.flag == original.flag);
    assert(parsed.ratio == original.ratio);
    assert(parsed.opt_str.has_value() && parsed.opt_str.value() == "yamltest");
    assert(parsed.numbers.size() == 2);
    assert(parsed.tags.size() == 3);
    std::cout << "[PASS] Round-trip: YAML serialization + re-parse.\n";
}

void test_json_file_roundtrip() {
    const std::string path = "/tmp/light_config_test_rt.json";

    TestConfig original;
    original.name = "file_rt";
    original.value = 55;
    original.flag = true;

    // Save to file (compact JSON for reliable round-trip).
    bool ok = light_config::save_to_json_file(original, path, false);
    assert(ok);

    // Load from file.
    TestConfig parsed;
    auto r = light_config::load_from_json_file(parsed, path);
    assert(r.ok());
    assert(parsed.name == original.name);
    assert(parsed.value == original.value);
    assert(parsed.flag == original.flag);
    std::cout << "[PASS] Round-trip: JSON file save + load.\n";
}

void test_yaml_file_roundtrip() {
    const std::string path = "/tmp/light_config_test_rt.yaml";

    TestConfig original;
    original.name = "yaml_file_rt";
    original.value = 123;
    original.flag = false;

    // Save to YAML file.
    bool ok = light_config::save_to_yaml_file(original, path);
    assert(ok);

    // Load from YAML file.
    TestConfig parsed;
    auto r = light_config::load_from_yaml_file(parsed, path);
    assert(r.ok());
    assert(parsed.name == original.name);
    assert(parsed.value == original.value);
    assert(parsed.flag == original.flag);
    std::cout << "[PASS] Round-trip: YAML file save + load.\n";
}

// ---- YAML Tests ----

void test_yaml_basic() {
    TestConfig cfg;
    auto r = light_config::load_from_yaml_string(cfg, R"(
name: yaml_test
value: 100
flag: true
ratio: 3.14
opt_str: "present"
numbers:
  - 1
  - 2
tags:
  - "tag1"
  - "tag2"
)");
    assert(r.ok());
    assert(cfg.name == "yaml_test");
    assert(cfg.value == 100);
    assert(cfg.opt_str.has_value() && cfg.opt_str.value() == "present");
    assert(cfg.numbers.size() == 2);
    assert(r.present_fields.size() == 7);
    assert(r.absent_optionals.size() == 2);
    std::cout << "[PASS] YAML basic load.\n";
}

void test_yaml_empty() {
    AllOptionalConfig cfg;
    auto r = light_config::load_from_yaml_string(cfg, "");
    assert(r.ok());
    assert(r.absent_optionals.size() == 2);
    std::cout << "[PASS] YAML empty document.\n";
}

// ---- Format Auto-Detection ----

void test_auto_detect_json() {
    const std::string path = "/tmp/light_config_test_auto.json";
    {
        std::ofstream f(path);
        f << R"({"name": "auto", "value": 1, "flag": false})";
    }
    TestConfig cfg;
    auto r = light_config::load(cfg, path);
    assert(r.ok());
    assert(cfg.name == "auto");
    std::cout << "[PASS] Auto-detect JSON (.json).\n";
}

void test_auto_detect_yaml() {
    const std::string path = "/tmp/light_config_test_auto.yaml";
    {
        std::ofstream f(path);
        f << "name: auto_yaml\nvalue: 2\nflag: true\n";
    }
    TestConfig cfg;
    auto r = light_config::load(cfg, path);
    assert(r.ok());
    assert(cfg.name == "auto_yaml");
    std::cout << "[PASS] Auto-detect YAML (.yaml).\n";
}

void test_auto_detect_yml() {
    const std::string path = "/tmp/light_config_test_auto.yml";
    {
        std::ofstream f(path);
        f << "name: auto_yml\nvalue: 3\nflag: false\n";
    }
    TestConfig cfg;
    auto r = light_config::load(cfg, path);
    assert(r.ok());
    assert(cfg.name == "auto_yml");
    std::cout << "[PASS] Auto-detect YAML (.yml).\n";
}

void test_auto_detect_no_extension() {
    const std::string path = "/tmp/light_config_test_auto_noext";
    {
        std::ofstream f(path);
        f << R"({"name": "noext", "value": 4, "flag": true})";
    }
    TestConfig cfg;
    auto r = light_config::load(cfg, path);
    assert(r.ok());
    assert(cfg.name == "noext");
    std::cout << "[PASS] Auto-detect no extension -> JSON.\n";
}

// ---- Schema Version Tests ----

void test_schema_version_json_match() {
    VersionedConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "$schema": "2.0.0",
        "name": "test",
        "value": 42
    })",
                                                 kVersionedConfigSchemaVersion);
    assert(r.ok());
    assert(r.code == light_config::ErrorCode::kOk);
    assert(cfg.name == "test");
    assert(cfg.value == 42);
    std::cout << "[PASS] Schema version: JSON match succeeds.\n";
}

void test_schema_version_json_mismatch() {
    VersionedConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "$schema": "1.0.0",
        "name": "test",
        "value": 42
    })",
                                                 kVersionedConfigSchemaVersion);
    assert(!r.ok());
    assert(r.code == light_config::ErrorCode::kSchemaMismatch);
    assert(!r.message.empty());
    // Message should mention both versions.
    assert(r.message.find("2.0.0") != std::string::npos);
    assert(r.message.find("1.0.0") != std::string::npos);
    std::cout << "[PASS] Schema version: JSON mismatch rejected: " << r.message << "\n";
}

void test_schema_version_json_missing_key() {
    VersionedConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "name": "no_schema",
        "value": 99
    })",
                                                 kVersionedConfigSchemaVersion);
    assert(r.ok());
    assert(cfg.name == "no_schema");
    assert(cfg.value == 99);
    std::cout << "[PASS] Schema version: missing $schema key proceeds (permissive).\n";
}

void test_schema_version_empty_expected_skips_check() {
    VersionedConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "$schema": "anything",
        "name": "test",
        "value": 1
    })");  // default: expected_schema_version = ""
    assert(r.ok());
    std::cout << "[PASS] Schema version: empty expected skips check.\n";
}

void test_schema_version_non_string_value_ignored() {
    VersionedConfig cfg;
    auto r = light_config::load_from_json_string(cfg, R"({
        "$schema": 42,
        "name": "test",
        "value": 1
    })",
                                                 kVersionedConfigSchemaVersion);
    // $schema is a number, not a string → is_string() check skips it.
    assert(r.ok());
    std::cout << "[PASS] Schema version: non-string $schema ignored.\n";
}

void test_schema_version_yaml_match() {
    VersionedConfig cfg;
    auto r = light_config::load_from_yaml_string(cfg, R"(
$schema: 2.0.0
name: yaml_test
value: 7
)",
                                                 kVersionedConfigSchemaVersion);
    assert(r.ok());
    assert(cfg.name == "yaml_test");
    assert(cfg.value == 7);
    std::cout << "[PASS] Schema version: YAML match succeeds.\n";
}

void test_schema_version_yaml_mismatch() {
    VersionedConfig cfg;
    auto r = light_config::load_from_yaml_string(cfg, R"(
$schema: 9.9.9
name: yaml_test
value: 7
)",
                                                 kVersionedConfigSchemaVersion);
    assert(!r.ok());
    assert(r.code == light_config::ErrorCode::kSchemaMismatch);
    std::cout << "[PASS] Schema version: YAML mismatch rejected.\n";
}

void test_schema_version_load_versioned_json() {
    const std::string path = "/tmp/light_config_test_schema.json";
    {
        std::ofstream f(path);
        f << R"({"$schema": "2.0.0", "name": "file_test", "value": 5})";
    }
    VersionedConfig cfg;
    auto r = light_config::load_versioned(cfg, path, kVersionedConfigSchemaVersion);
    assert(r.ok());
    assert(cfg.value == 5);
    std::cout << "[PASS] Schema version: load_versioned JSON match.\n";
}

// NOLINTNEXTLINE(bugprone-exception-escape)
int main() {
    // JSON
    test_json_all_fields_present();
    test_json_some_optionals_absent();
    test_json_optional_explicit_null();
    test_json_all_optional();
    test_json_no_optionals();
    test_json_parse_error();
    test_json_missing_file();

    // Nested struct
    test_json_nested_all_present();
    test_json_nested_some_absent();

    // YAML
    test_yaml_basic();
    test_yaml_empty();

    // Auto-detect
    test_auto_detect_json();
    test_auto_detect_yaml();
    test_auto_detect_yml();
    test_auto_detect_no_extension();

    // Schema version
    test_schema_version_json_match();
    test_schema_version_json_mismatch();
    test_schema_version_json_missing_key();
    test_schema_version_empty_expected_skips_check();
    test_schema_version_non_string_value_ignored();
    test_schema_version_yaml_match();
    test_schema_version_yaml_mismatch();
    test_schema_version_load_versioned_json();

    // Round-trip
    test_json_roundtrip_basic();
    test_json_roundtrip_pretty();
    test_json_roundtrip_all_optionals();
    test_json_roundtrip_nested();
    test_yaml_roundtrip_basic();
    test_json_file_roundtrip();
    test_yaml_file_roundtrip();

    std::cout << "\nAll " << 30 << " tests passed.\n";
    return 0;
}
