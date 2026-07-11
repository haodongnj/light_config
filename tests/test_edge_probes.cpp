#define DOCTEST_CONFIG_IMPLEMENT_WITH_MAIN
#include <light_config/light_config.hpp>

#include <optional>
#include <string>
#include <vector>

#include <doctest/doctest.h>

// ---- Probe structs (re-hosted from build/edge_probes/runtime_probe.cpp) ----

struct Item {
    std::string name;
    int qty = 0;
    std::optional<std::string> tag;
};
YLT_REFL(Item, name, qty, tag);

struct Box {
    std::vector<Item> items;
    std::optional<std::string> label;
};
YLT_REFL(Box, items, label);
struct ItemList {
    std::optional<std::vector<Item>> items;
};
YLT_REFL(ItemList, items);

struct Versioned {
    std::string name;
    int value = 0;
};
YLT_REFL(Versioned, name, value);
constexpr std::string_view kVer{"1.0.0"};

struct Inner {
    std::string host = "default";
    std::optional<int> port;
};
YLT_REFL(Inner, host, port);

struct Outer {
    std::string app;
    std::optional<Inner> inner;
};
YLT_REFL(Outer, app, inner);

static bool contains(const std::vector<std::string>& v, const std::string& s) {
    for (auto& x : v)
        if (x == s)
            return true;
    return false;
}

// ============================================================================
// YAML $schema inside a # comment must not count as a present $schema.
// ============================================================================

TEST_CASE("$schema in a line-leading comment is ignored") {
    // Comment with a *mismatched* version but no real $schema key -> the
    // loader is permissive ($schema treated as absent) -> ok.
    Versioned v;
    std::string yaml = "# $schema: 2.0.0\nname: x\nvalue: 1\n";
    auto r = light_config::load_from_yaml_string(v, yaml, kVer);
    CHECK(r.ok());
    CHECK(v.name == "x");
    CHECK(v.value == 1);
}

TEST_CASE("real $schema on its own line still matches") {
    Versioned v;
    std::string yaml = "$schema: 1.0.0\nname: x\nvalue: 1\n";
    auto r = light_config::load_from_yaml_string(v, yaml, kVer);
    CHECK(r.ok());
}

TEST_CASE("real $schema mismatch still rejected") {
    Versioned v;
    std::string yaml = "$schema: 2.0.0\nname: x\nvalue: 1\n";
    auto r = light_config::load_from_yaml_string(v, yaml, kVer);
    CHECK(!r.ok());
    CHECK(r.code == light_config::ErrorCode::kSchemaMismatch);
}

// ============================================================================
// quoted $schema value is unquoted before comparison.
// ============================================================================

TEST_CASE("double-quoted $schema matches unquoted expected") {
    Versioned v;
    std::string yaml = "$schema: \"1.0.0\"\nname: x\nvalue: 1\n";
    auto r = light_config::load_from_yaml_string(v, yaml, kVer);
    CHECK(r.ok());
}

TEST_CASE("single-quoted $schema matches unquoted expected") {
    Versioned v;
    std::string yaml = "$schema: '1.0.0'\nname: x\nvalue: 1\n";
    auto r = light_config::load_from_yaml_string(v, yaml, kVer);
    CHECK(r.ok());
}

TEST_CASE("unquoted $schema still matches (unchanged)") {
    Versioned v;
    std::string yaml = "$schema: 1.0.0\nname: x\nvalue: 1\n";
    auto r = light_config::load_from_yaml_string(v, yaml, kVer);
    CHECK(r.ok());
}

// ============================================================================
// detect_format matches extensions case-insensitively.
// ============================================================================

TEST_CASE("detect_format is case-insensitive") {
    using F = light_config::Format;
    CHECK(light_config::detect_format("foo.YAML") == F::Yaml);
    CHECK(light_config::detect_format("foo.JSON") == F::Json);
    CHECK(light_config::detect_format("FOO.Yml") == F::Yaml);
    CHECK(light_config::detect_format("foo.YML") == F::Yaml);
    // Unchanged cases.
    CHECK(light_config::detect_format("foo.yaml") == F::Yaml);
    CHECK(light_config::detect_format("foo.json") == F::Json);
    CHECK(light_config::detect_format("foo") == F::Json);      // no ext
    CHECK(light_config::detect_format("foo.txt") == F::Auto);  // unrecognized
}

// ============================================================================
// audit recurses into optional<Nested> and arrays of structs.
// ============================================================================

TEST_CASE("optional<Nested> present -> inner subfields audited") {
    Outer o;
    auto r = light_config::load_from_json_string(o, R"({
        "app": "x", "inner": { "host": "h", "port": 7 }
    })");
    CHECK(r.ok());
    CHECK(contains(r.present_fields, "inner"));
    CHECK(contains(r.present_fields, "inner.host"));
    CHECK(contains(r.present_fields, "inner.port"));
}

TEST_CASE("optional<Nested> present, inner.port absent -> reported") {
    Outer o;
    auto r = light_config::load_from_json_string(o, R"({
        "app": "x", "inner": { "host": "h" }
    })");
    CHECK(r.ok());
    CHECK(contains(r.present_fields, "inner"));
    CHECK(contains(r.present_fields, "inner.host"));
    CHECK(contains(r.absent_optionals, "inner.port"));
}

TEST_CASE("vector<Item> element optional field reported via items[]") {
    Box b;
    auto r = light_config::load_from_json_string(b, R"({
        "items": [ {"name":"a","qty":1} ], "label": "x"
    })");
    CHECK(r.ok());
    CHECK(contains(r.present_fields, "items"));
    CHECK(contains(r.present_fields, "items[].name"));
    CHECK(contains(r.present_fields, "items[].qty"));
    CHECK(contains(r.absent_optionals, "items[].tag"));
    CHECK(contains(r.present_fields, "label"));
}

// ============================================================================
TEST_CASE("optional<vector<Item>> audit recurses into elements") {
    ItemList il;
    auto r = light_config::load_from_json_string(il, R"({
        "items": [ {"name":"a","qty":1} ]
    })");
    CHECK(r.ok());
    CHECK(contains(r.present_fields, "items"));
    CHECK(contains(r.present_fields, "items[].name"));
    CHECK(contains(r.present_fields, "items[].qty"));
    CHECK(contains(r.absent_optionals, "items[].tag"));
}

TEST_CASE("optional<vector<Item>> mixed absent tag reported") {
    ItemList il;
    auto r = light_config::load_from_json_string(il, R"({
        "items": [
            {"name":"full","qty":1,"tag":"opt"},
            {"name":"bare","qty":2}
        ]
    })");
    CHECK(r.ok());
    CHECK(contains(r.present_fields, "items"));
    CHECK(contains(r.present_fields, "items[].name"));
    CHECK(contains(r.present_fields, "items[].qty"));
    CHECK(contains(r.absent_optionals, "items[].tag"));
}

// Scenario [5]: empty JSON string is a parse error (already-correct behavior).
// ============================================================================

TEST_CASE("empty JSON string -> kJsonParseError") {
    Versioned v;
    auto r = light_config::load_from_json_string(v, "");
    CHECK(!r.ok());
    CHECK(r.code == light_config::ErrorCode::kJsonParseError);
}
