from __future__ import annotations


class DeltaStreamValidationError(Exception):
    """
    Raised when validation fails in Delta Stream operations.

    This includes schema validation issues, type mismatches, and invalid default values.
    """


class DeltaStreamModelBuildError(Exception):
    """Raised when building a model with defaults fails."""
