"""GeneratorError and other exceptions for the gen_config package."""


class GeneratorError(Exception):
    """Raised when the CSV schema or generator input is invalid.

    Replaces unstructured sys.exit(1) calls so the package is usable as a
    library without killing the host process.
    """
