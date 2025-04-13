"""
Default value handling for stream-compatible Pydantic models.

This module provides functions to validate and set default values for Pydantic model schemas.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from delta_stream._errors import DeltaStreamModelBuildError
from delta_stream._schema import format_schema_path
from delta_stream._types import JSON_TYPE_VALIDATORS


def validate_default_value(
    default_value: Any, prop_schema: dict, path: tuple[str, ...]
) -> bool:
    """Validate that a default value matches the expected schema types.

    Args:
        default_value: Value to validate
        prop_schema: Property schema containing type information
        path: Path to the property for error reporting

    Returns:
        True if validation passed

    Raises:
        TypeError: If validation fails
    """
    if "type" in prop_schema:
        prop_type = prop_schema["type"]
        validator = JSON_TYPE_VALIDATORS.get(prop_type)

        if validator and not validator(default_value):
            raise DeltaStreamModelBuildError(
                f"Default value for '{format_schema_path(path)}' "
                f"must be of type {prop_type}, but got {type(default_value).__name__}."
            )
        return True

    # Handle union type validation (anyOf/oneOf)
    elif "anyOf" in prop_schema or "oneOf" in prop_schema:
        any_of = prop_schema.get("anyOf", prop_schema.get("oneOf", []))
        valid_for_any = False

        for entry in any_of:
            if isinstance(entry, dict) and "type" in entry:
                entry_type = entry["type"]
                validator = JSON_TYPE_VALIDATORS.get(entry_type)

                if validator and validator(default_value):
                    valid_for_any = True
                    break

        if not valid_for_any:
            any_of_types = [
                entry.get("type")
                for entry in any_of
                if isinstance(entry, dict) and "type" in entry
            ]
            any_of_types_str = " or ".join(any_of_types)
            raise DeltaStreamModelBuildError(
                f"Default value for '{format_schema_path(path)}' "
                f"must be {any_of_types_str}, but got {type(default_value).__name__}."
            )
        return True

    return False


def process_schema_with_defaults(
    schema: Any,
    def_path: tuple[str, ...],
    root_schema: dict[str, Any],
    path_mapping: dict[tuple[str, ...], type[BaseModel]],
) -> dict[str, Any]:
    """Process a model schema and set appropriate defaults for all properties.

    This function recursively traverses a schema and sets defaults according to the following rules:
    1. Keep existing defaults if present
    2. Apply stream_default from field metadata if available
    3. Apply automatic defaults based on schema type (empty string for strings, empty list for arrays)
    4. Raise errors for types that require explicit defaults (numbers, booleans, objects)

    Args:
        schema: The schema to process
        def_path: Current path in the schema
        root_schema: Root schema object
        path_mapping: Map of paths to model classes

    Returns:
        Processed schema with defaults set

    Raises:
        TypeError: If schema is not a dictionary
        ValueError: If a required property has no default and no automatic default can be applied
    """
    if not isinstance(schema, dict):
        raise DeltaStreamModelBuildError(
            f"Expected {schema} to be a dictionary; path={def_path}"
        )

    model_class = path_mapping.get(def_path)

    # Process $defs recursively
    defs = schema.get("$defs")
    if isinstance(defs, dict):
        for def_name, def_schema in defs.items():
            process_schema_with_defaults(
                def_schema,
                def_path=(*def_path, "$defs", def_name),
                root_schema=root_schema,
                path_mapping=path_mapping,
            )

    # Process properties and set defaults
    properties = schema.get("properties")
    if isinstance(properties, dict):
        for prop_name, prop_schema in properties.items():
            prop_path = (*def_path, prop_name)

            default_value = None

            # 1. Check if property already has a default
            existing_default = "default" in prop_schema
            if existing_default:
                default_value = prop_schema["default"]
                # Validate existing default
                validate_default_value(default_value, prop_schema, prop_path)
                continue  # Skip to next property, this one already has a valid default

            # 2. Check if stream_default is available from model field
            if model_class and prop_name in model_class.model_fields:
                field = model_class.model_fields[prop_name]
                if hasattr(field, "json_schema_extra"):
                    extra = field.json_schema_extra
                    if isinstance(extra, dict) and "stream_default" in extra:
                        default_value = extra["stream_default"]
                        # Validate stream_default
                        validate_default_value(default_value, prop_schema, prop_path)
                        prop_schema["default"] = default_value
                        continue  # Skip to next property, we've set the stream_default

            # 3. Apply automatic defaults based on schema type
            if "type" in prop_schema:
                # Single type
                prop_type = prop_schema["type"]

                if prop_type == "string":
                    default_value = ""
                elif prop_type == "array":
                    default_value = []
                elif prop_type == "null":
                    default_value = None
                else:
                    # For number, integer, boolean, and object - no automatic default
                    raise ValueError(
                        f"Property '{format_schema_path(prop_path)}' "
                        f"of type {prop_type} must have a default value."
                    )

            # 4. Handle union types (anyOf/oneOf)
            elif "anyOf" in prop_schema or "oneOf" in prop_schema:
                type_options = prop_schema.get("anyOf", prop_schema.get("oneOf", []))

                # Check for null type first (highest priority)
                has_null = any(
                    isinstance(option, dict) and option.get("type") == "null"
                    for option in type_options
                )

                if has_null:
                    default_value = None

                # Then check for string
                elif any(
                    isinstance(option, dict) and option.get("type") == "string"
                    for option in type_options
                ):
                    default_value = ""

                # Then check for array
                elif any(
                    isinstance(option, dict) and option.get("type") == "array"
                    for option in type_options
                ):
                    default_value = []

                else:
                    # No automatic default for this union
                    raise DeltaStreamModelBuildError(
                        f"Property '{format_schema_path(prop_path)}' "
                        f"must have a default value because it's a union type with no automatic default."
                    )

            # 5. Validate the automatically assigned default value
            validate_default_value(default_value, prop_schema, prop_path)

            # 6. Set the validated default in the schema
            prop_schema["default"] = default_value

    return schema
