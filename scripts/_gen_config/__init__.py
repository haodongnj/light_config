"""
Re-export all public symbols of the gen_config package.
"""

from .__main__ import _build_provenance, generate, main
from .codegen import CodeGenerator
from .config import GeneratorConfig
from .cpp_gen import (
    _make_header_preamble,
    _make_schema_version_constant,
    _make_source_preamble,
    _make_struct_body,
    _make_validate_decl,
    _make_validate_impl,
)
from .provenance import Provenance, _provenance_block
from .samples import _build_sample_dict, _write_json, _write_yaml
from .schema import SchemaModel
from .types import (
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
