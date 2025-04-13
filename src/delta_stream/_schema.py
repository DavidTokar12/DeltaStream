"""
Schema utilities for Pydantic model processing.

This module provides functions to manipulate and traverse JSON schemas derived from Pydantic models.
"""

from __future__ import annotations

import types

from typing import Any
from typing import Optional
from typing import Union
from typing import get_args
from typing import get_origin
from typing import get_type_hints

from pydantic import BaseModel


def format_schema_path(path: tuple[str, ...]) -> str:
    """Format a schema path tuple into a dot-separated string.

    Args:
        path: Tuple of path segments

    Returns:
        Formatted path string with "$defs" and "properties" keys omitted
    """
    if not path:
        return ""
    filtered_parts = [part for part in path if part not in ["$defs", "properties"]]
    return ".".join(filtered_parts)


def resolve_schema_reference(ref: str, root_schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve a JSON schema $ref pointer within the same document.

    Args:
        ref: Reference string (e.g., "#/$defs/ModelName")
        root_schema: Root schema object to resolve references within

    Returns:
        Resolved schema definition

    Raises:
        ValueError: If reference cannot be resolved
    """
    parts = ref.split("/")
    if parts[0] != "#":
        raise ValueError(f"External/invalid reference format: {ref}")

    current: dict[str, Any] | None = root_schema
    for i, part in enumerate(parts[1:]):
        current_path_str = "/".join(parts[1 : i + 1])
        if isinstance(current, dict):
            if part not in current:
                raise ValueError(
                    f"Reference part '{part}' not found at path '#/{current_path_str}' in schema. Ref: {ref}"
                )
            current = current.get(part)
        else:
            raise ValueError(
                f"Schema traversal failed at non-dictionary element at path '#/{current_path_str}' trying to resolve part '{part}'. Ref: {ref}"
            )

    if not isinstance(current, dict):
        raise ValueError(
            f"Reference resolved successfully, but does not point to a dictionary/object as expected: {ref}"
        )
    return current


def find_nested_schema_definition(
    prop_schema: dict[str, Any], root_schema: dict[str, Any], is_list: bool
) -> dict[str, Any] | None:
    """Find the JSON schema definition for a nested model within a property schema.

    Args:
        prop_schema: Property schema that might contain references
        root_schema: Root schema to resolve references against
        is_list: Whether the property is a list type

    Returns:
        Resolved schema definition or None if not found

    Raises:
        ValueError: If reference resolution fails
    """
    if not prop_schema:
        return None

    ref: str | None = None
    target_schema: Any = prop_schema

    if is_list:
        items_schema = prop_schema.get("items")
        if isinstance(items_schema, dict):
            target_schema = items_schema
        else:
            return None

    # Check for $ref in the target schema
    if isinstance(target_schema, dict) and "$ref" in target_schema:
        ref = target_schema.get("$ref")
    # Check for $ref within anyOf
    elif "anyOf" in prop_schema:
        for sub_schema in prop_schema.get("anyOf", []):
            if isinstance(sub_schema, dict) and "$ref" in sub_schema:
                ref = sub_schema.get("$ref")
                break

    # Resolve $ref if found
    if ref and isinstance(ref, str):
        try:
            return resolve_schema_reference(ref, root_schema)
        except ValueError:
            raise

    # Check for an inline object definition
    if (
        isinstance(target_schema, dict)
        and target_schema.get("type") == "object"
        and "properties" in target_schema
    ):
        return target_schema

    return None


def build_path_mapping(
    model_class: type[BaseModel],
    path_mapping: dict[tuple[str, ...], type[BaseModel]],
) -> None:
    """Build a mapping from schema paths to model classes.

    This function recursively maps schema paths to their corresponding Pydantic model classes,
    including nested models in fields, lists, and unions.

    Args:
        model_class: Root Pydantic model class
        path_mapping: Dictionary to store path -> model mappings
    """

    path_mapping[()] = model_class
    path_mapping[("$defs", model_class.__name__)] = model_class

    def collect_models(cls):
        models = set()
        for _, field_type in get_type_hints(cls).items():
            # Direct BaseModel field
            if isinstance(field_type, type) and issubclass(field_type, BaseModel):
                models.add(field_type)

            # List of BaseModels
            elif get_origin(field_type) in (list, list) and get_args(field_type):
                item_type = get_args(field_type)[0]
                if isinstance(item_type, type) and issubclass(item_type, BaseModel):
                    models.add(item_type)

            # Union type with BaseModels
            elif get_origin(field_type) in (Union, types.UnionType, Optional):
                for arg in get_args(field_type):
                    if isinstance(arg, type) and issubclass(arg, BaseModel):
                        models.add(arg)

        return models

    models_to_process = collect_models(model_class)
    for nested_model in models_to_process:
        path_mapping[("$defs", nested_model.__name__)] = nested_model

        for sub_model in collect_models(nested_model):
            path_mapping[("$defs", sub_model.__name__)] = sub_model
