"""
Provenance stamp recorded in every generated .hpp/.cpp file.
"""

from dataclasses import dataclass


@dataclass
class Provenance:
    """Metadata recorded in every generated .hpp/.cpp file.

    Fields:
        schema_version: Human-readable version (from CSV __metadata__ or --schema-version).
        source_csv:     Bare basename of the input CSV.
        csv_md5:        32-char hex MD5 of the CSV's raw bytes.
        generated_at:   ISO-8601 UTC timestamp of the generation run.
        generator:      Name of the generator (CSV generator key or default).
    """

    schema_version: str
    source_csv: str
    csv_md5: str
    generated_at: str
    generator: str


def _provenance_block(prov: Provenance, indent: str = "") -> str:
    """Return a /// comment block recording schema provenance.

    Each line is prefixed with `indent` (used when the block is emitted
    inside an already-indented context; the common case is indent="").
    """
    lines = [
        f"{indent}///",
        f"{indent}/// --- Schema provenance ---",
        f"{indent}///   schema_version : {prov.schema_version}",
        f"{indent}///   source_csv     : {prov.source_csv}",
        f"{indent}///   csv_md5        : {prov.csv_md5}",
        f"{indent}///   generated_at   : {prov.generated_at}",
        f"{indent}///   generator      : {prov.generator}",
        f"{indent}/// -----------------------",
    ]
    return "\n".join(lines)
