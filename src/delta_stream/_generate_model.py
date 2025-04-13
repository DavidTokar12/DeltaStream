"""
Main module for preparing Pydantic models for streaming.

This module provides the public API for processing Pydantic models to make them
compatible with streaming requirements.
"""

from __future__ import annotations

from pydantic import BaseModel

from delta_stream._defaults import process_schema_with_defaults
from delta_stream._errors import DeltaStreamModelBuildError
from delta_stream._model_builder import create_model_with_defaults
from delta_stream._schema import build_path_mapping


def _generate_model_with_defaults(model_class: type[BaseModel]) -> type[BaseModel]:
    """
    Generate a Pydantic model for streaming by setting appropriate defaults.

    Takes an input Pydantic BaseModel and returns a *new* BaseModel class
    where fields have default values assigned based on the following priority:
    1. Keep existing explicit defaults (`field: type = value` or `Field(default=...)`).
    2. Use `stream_default` found in `Field(json_schema_extra={'stream_default': ...})`.
    3. Apply automatic defaults: `""` for `str`, `[]` for `list`.
    4. Apply `default_factory` to create default instances for nested *required* BaseModel fields (fields typed as `NestedModel`, not `NestedModel | None`).
       The nested model instance created will also have *its* defaults applied according
       to these rules.
    6. Default to `None` for optional fields (`Type | None` or `Optional[Type]`) if
       no other default is specified.
    7. Raise `DeltaStreamModelBuildError` for any other required field without a
       default specified via the above rules (e.g., required `int`, `float`, `bool`).

    Args:
        model_class: The Pydantic BaseModel class to process.

    Returns:
        A new Pydantic BaseModel class (`type[T]`) derived from the input class,
        with defaults applied according to the streaming rules.

    Raises:
        DeltaStreamModelBuildError: If processing fails, typically because a required
                                   field cannot be assigned a default value.
        TypeError: If input is not a Pydantic BaseModel class.
    """
    try:
        schema = model_class.model_json_schema()

        path_mapping = {}
        build_path_mapping(model_class, path_mapping)

        schema_with_defaults = process_schema_with_defaults(
            schema,
            def_path=(),
            root_schema=schema,
            path_mapping=path_mapping,
        )

        model_with_defaults = create_model_with_defaults(
            model_class, schema_with_defaults
        )

        return model_with_defaults

    except Exception as e:
        raise DeltaStreamModelBuildError(
            f"Failed to prepare model {model_class.__name__} for streaming: {e}"
        ) from e
