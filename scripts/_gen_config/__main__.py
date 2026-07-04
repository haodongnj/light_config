"""
CSV-driven config-header generator for light_config.

Takes a CSV with columns:
    field_name, group, type, default, min, max, description, hpp_file

See gen_config.py at the scripts/ root for the CLI wrapper, or run as:
    python3 -m _gen_config --input examples/sample_config.csv
"""

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

from .codegen import CodeGenerator
from .config import GeneratorConfig
from .exceptions import GeneratorError
from .provenance import Provenance
from .schema import SchemaModel


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def _build_provenance(
    config: GeneratorConfig,
    model: SchemaModel,
    input_path: str,
) -> Provenance:
    """Resolve schema version, CSV MD5 and timestamp for the stamp."""
    version = (
        config.schema_version_override
        or model.metadata.get("schema_version")
        or "unknown"
    )
    csv_md5 = hashlib.md5(Path(input_path).read_bytes()).hexdigest()
    generated_at = datetime.now(timezone.utc).isoformat()
    generator = model.metadata.get("generator") or "light_config / scripts/gen_config.py"
    return Provenance(
        schema_version=version,
        source_csv=Path(input_path).name,
        csv_md5=csv_md5,
        generated_at=generated_at,
        generator=generator,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def generate(config: GeneratorConfig) -> None:
    model = SchemaModel.from_csv(config.input_csv)
    prov = _build_provenance(config, model, config.input_csv)
    gen = CodeGenerator(model, config, prov)
    gen.generate_all()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate light_config struct + validation code from a CSV schema."
    )
    parser.add_argument(
        "--input", "-i", required=True, help="Path to CSV schema file."
    )
    parser.add_argument(
        "--output-dir",
        "-d",
        default="examples/",
        help="Base directory for generated files, used as fallback for "
        "--hpp-dir, --src-dir, and sample files (default: examples/).",
    )
    parser.add_argument(
        "--hpp-dir",
        default=None,
        help="Directory for the generated .hpp file(s). Falls back to --output-dir "
        "when not set.",
    )
    parser.add_argument(
        "--src-dir",
        default=None,
        help="Directory for the generated .cpp file(s). Falls back to --output-dir "
        "when not set.",
    )
    parser.add_argument(
        "--struct-name",
        default="",
        help="Override root struct name for file naming "
        "(default: auto-detected from CSV root group).",
    )
    parser.add_argument(
        "--hpp-name",
        default=None,
        help="Explicit .hpp filename (e.g. 'app_config.hpp').  Only used in "
        "monolithic or --per-struct mode; ignored when CSV hpp_file column "
        "is present.  When set, this name is used for the generated header, "
        "the corresponding .cpp stem, and the #include directive in the source "
        "file.",
    )
    parser.add_argument(
        "--per-struct",
        action="store_true",
        help="Generate one .hpp/.cpp pair per struct group instead of a single "
        "monolithic pair.  Ignored when the CSV carries an hpp_file column.",
    )
    parser.add_argument(
        "--namespace",
        default="",
        help="C++ namespace to wrap all generated structs and validation "
        "functions in (e.g. 'myapp' or 'myapp::net').  Overrides any "
        "__metadata__ namespace= value in the CSV.  Empty or absent = "
        "global scope (back-compat).",
    )
    parser.add_argument(
        "--generate-samples",
        action="store_true",
        help="Emit valid_config.json and valid_config.yaml into --output-dir.",
    )
    parser.add_argument(
        "--schema-version",
        default=None,
        help="Override the schema version recorded in the generated provenance "
        "stamp (default: read from CSV __metadata__ 'schema_version' key, or "
        "'unknown' when absent).",
    )
    args = parser.parse_args()

    config = GeneratorConfig(
        input_csv=args.input,
        output_dir=args.output_dir,
        hpp_dir=args.hpp_dir,
        src_dir=args.src_dir,
        struct_name=args.struct_name,
        hpp_name=args.hpp_name,
        namespace=args.namespace,
        per_struct=args.per_struct,
        generate_samples=args.generate_samples,
        schema_version_override=args.schema_version,
    )
    try:
        generate(config)
    except GeneratorError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
