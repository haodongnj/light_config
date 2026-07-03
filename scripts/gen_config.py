#!/usr/bin/env python3
"""
CSV-driven config-header generator for light_config.

Takes a CSV with columns:
    field_name, group, type, default, min, max, description, hpp_file

Every row belongs to a struct via the 'group' column (the exact C++ struct
type name).  Containment is expressed in the CSV itself: when a row's 'type'
matches another group name, that struct becomes a nested member of the current
group.  The member field name comes from 'field_name'.

The root struct is auto-detected: the group that no other group references as
a member type.

File grouping (three modes, in order of precedence):

  1. CSV-driven  — when any row carries a non-empty 'hpp_file', every group
     is placed into the .hpp/.cpp pair named by its hpp_file column.  Groups
     sharing the same hpp_file are bundled into one file pair.  Cross-file
     #includes are emitted automatically.

  2. --per-struct — one .hpp/.cpp pair per struct group.

  3. Monolithic   — all structs in a single .hpp/.cpp pair (default).

Generated files:
    <hpp_dir>/<hpp_file>.hpp         — struct definitions + validation decls
    <src_dir>/<hpp_stem>.cpp         — validation implementations
    <output_dir>/valid_config.json   — (optional) sample valid config
    <output_dir>/valid_config.yaml   — (optional) sample valid config

Usage:
    python3 scripts/gen_config.py --input examples/sample_config.csv
    python3 scripts/gen_config.py --input examples/sample_config.csv \\
        --output-dir build/ --hpp-dir include/config/ --src-dir src/config/ \\
        --per-struct --generate-samples

The implementation lives in the _gen_config/ package; this file is a thin
shim that re-exports the public API so existing importers keep working.
"""
# flake8: noqa: F401, E402

from _gen_config.__main__ import _build_provenance, generate, main

# Re-export all public symbols for backward-compatible imports.
from _gen_config.codegen import CodeGenerator
from _gen_config.config import GeneratorConfig
from _gen_config.cpp_gen import (  # noqa: F401 — re-exported for tests
    _make_header_preamble,
    _make_schema_version_constant,
    _make_source_preamble,
    _make_struct_body,
    _make_validate_decl,
    _make_validate_impl,
)
from _gen_config.provenance import Provenance, _provenance_block
from _gen_config.samples import _build_sample_dict, _write_json, _write_yaml
from _gen_config.schema import SchemaModel
from _gen_config.types import (
    INT_TYPES,
    _csv_trace_block,
    _derive_filenames,
    _example_value,
    _field_value,
    _hpp_to_cpp_name,
    _int_range,
    _is_optional,
    _parse_default,
    _row_location,
    _struct_to_cpp_name,
    _struct_to_hpp_name,
    _to_snake_case,
    _violating_value,
    map_type,
)

if __name__ == "__main__":
    main()
