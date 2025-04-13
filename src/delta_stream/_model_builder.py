"""
Pydantic model builder with stream compatibility.

This module provides functionality to create new Pydantic models with defaults applied
from a processed schema.
"""

from __future__ import annotations

import functools
import operator
import types

from typing import Any
from typing import ForwardRef
from typing import Union
from typing import get_args
from typing import get_origin
from typing import get_type_hints

from pydantic import BaseModel
from pydantic import Field
from pydantic import create_model
from pydantic_core import PydanticUndefined

from delta_stream._schema import find_nested_schema_definition


def process_annotation_recursive(
    annotation: Any,
    cache: dict[type[BaseModel], type[BaseModel] | ForwardRef],
    prop_schema: dict[str, Any],
    root_schema: dict[str, Any],
    field_name: str,
    class_name: str,
) -> Any:
    """Process a type annotation recursively, rebuilding nested models as needed.

    Args:
        annotation: Type annotation to process
        cache: Cache of already processed models
        prop_schema: Property schema for this field
        root_schema: Root schema object
        field_name: Name of the field being processed (for error context)
        class_name: Name of the containing class (for error context)

    Returns:
        Processed annotation with nested models rebuilt

    Raises:
        ValueError: If schema definition for nested model cannot be found
        TypeError: If generic type reconstruction fails
    """
    origin = get_origin(annotation)
    args = get_args(annotation)

    if args and origin:  # Generic types like list[T], T | None, T | U ...
        processed_args = []
        nested_model_found_in_args = False
        is_list_origin = origin is list

        for arg in args:
            if isinstance(arg, type) and issubclass(arg, BaseModel):
                nested_model_found_in_args = True
                # Find schema for nested model
                nested_schema_def = find_nested_schema_definition(
                    prop_schema, root_schema, is_list=is_list_origin
                )
                if nested_schema_def is None:
                    raise ValueError(
                        f"Could not find schema definition for nested model '{arg.__name__}' "
                        f"referenced in field '{class_name}.{field_name}'. "
                        f"Field schema: {prop_schema}"
                    )

                rebuilt_nested_model = build_model_with_defaults_recursive(
                    arg, cache, nested_schema_def, root_schema
                )
                processed_args.append(rebuilt_nested_model)
            else:
                processed_args.append(arg)  # Keep non-model args

        if nested_model_found_in_args:
            # Reconstruct the generic type hint
            # Handle Union (|) using functools.reduce
            if origin is types.UnionType or origin is Union:
                if not processed_args:
                    raise ValueError(
                        f"Cannot create Union type with zero arguments for field '{class_name}.{field_name}'."
                    )
                # Build the union type iteratively using | operator via reduce
                try:
                    return functools.reduce(operator.or_, processed_args)
                except TypeError as e:
                    raise TypeError(
                        f"Failed to create Union type for field '{class_name}.{field_name}' with args {processed_args}: {e}"
                    ) from e
            elif origin is list:
                if len(processed_args) != 1:
                    raise ValueError(
                        f"list[...] annotation expects exactly one type argument for field '{class_name}.{field_name}', got {len(processed_args)}: {processed_args}"
                    )
                return list[processed_args[0]]
            else:
                try:
                    return origin[tuple(processed_args)]
                except TypeError as e:
                    raise TypeError(
                        f"Could not reconstruct generic type {origin} for field '{class_name}.{field_name}' with args {processed_args}: {e}"
                    ) from e

    elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
        # Direct nesting (field: NestedModel)
        nested_schema_def = find_nested_schema_definition(
            prop_schema, root_schema, is_list=False
        )
        if nested_schema_def is None:
            raise ValueError(
                f"Could not find schema definition for nested model '{annotation.__name__}' "
                f"referenced directly in field '{class_name}.{field_name}'. "
                f"Field schema: {prop_schema}"
            )

        return build_model_with_defaults_recursive(
            annotation, cache, nested_schema_def, root_schema
        )

    # Return original annotation if no nested models were involved or processed
    return annotation


def build_model_with_defaults_recursive(
    original_cls: type[BaseModel],
    cache: dict[type[BaseModel], type[BaseModel] | ForwardRef],
    schema_definition: dict[str, Any],
    root_schema: dict[str, Any],
) -> type[BaseModel]:
    """Recursively build a new Pydantic model with defaults from schema.

    Args:
        original_cls: Original Pydantic model class
        cache: Cache of already processed models to avoid circular references
        schema_definition: Schema definition for this model
        root_schema: Root schema object

    Returns:
        New model class with defaults applied

    Raises:
        TypeError: If type hints cannot be resolved
        KeyError: If a field has no corresponding schema property
        RuntimeError: If model creation fails
    """
    # 1. Check cache
    if original_cls in cache:
        cached_val = cache[original_cls]
        if (
            isinstance(cached_val, type)
            and issubclass(cached_val, BaseModel)
            or isinstance(cached_val, ForwardRef)
        ):
            return cached_val
        else:
            raise TypeError(
                f"Unexpected type {type(cached_val)} in model build cache for {original_cls}."
            )

    # 2. Prepare for new model creation
    new_model_name = f"{original_cls.__name__}WithDefaults"
    cache[original_cls] = ForwardRef(new_model_name)

    # 3. Get Type Hints for original model
    try:
        original_type_hints = get_type_hints(original_cls, include_extras=True)
    except Exception as e:
        raise TypeError(
            f"Failed to resolve type hints for {original_cls.__name__}: {e}"
        ) from e

    # 4. Iterate through original fields to build new field definitions
    new_fields: dict[str, tuple[type[Any], Field]] = {}
    properties_schema = schema_definition.get("properties", {})

    for field_name, original_field_info in original_cls.model_fields.items():
        original_annotation = original_type_hints.get(field_name, Any)

        # Find the corresponding property schema in the *mutated* schema
        prop_schema = properties_schema.get(field_name)

        if prop_schema is None:
            raise KeyError(
                f"Field '{field_name}' from Python model '{original_cls.__name__}' "
                f"not found in the 'properties' of the provided schema definition. "
                f"Schema keys: {list(properties_schema.keys())}"
            )

        # Process annotation for nested models
        try:
            processed_annotation = process_annotation_recursive(
                original_annotation,
                cache,
                prop_schema,
                root_schema,
                field_name,
                original_cls.__name__,
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to process annotation for field '{original_cls.__name__}.{field_name}': {e}"
            ) from e

        # Extract the NEW default value from the mutated schema
        new_default = prop_schema.get("default", PydanticUndefined)

        # Create NEW FieldInfo using the new default
        field_kwargs = {}
        description = prop_schema.get("title", original_field_info.description)
        if description:
            field_kwargs["description"] = description

        # Use a default_factory to generate an instance of the nested model with defaults.
        if isinstance(processed_annotation, type) and issubclass(
            processed_annotation, BaseModel
        ):
            new_field_info = Field(
                default_factory=lambda processed_annotation=processed_annotation: processed_annotation(),
                **field_kwargs,
            )

        elif new_default is not PydanticUndefined:
            new_field_info = Field(default=new_default, **field_kwargs)

        elif original_field_info.is_required():

            new_field_info = Field(..., **field_kwargs)

        else:
            new_field_info = Field(
                default=original_field_info.get_default(),
                default_factory=original_field_info.default_factory,
                **field_kwargs,
            )

        new_fields[field_name] = (processed_annotation, new_field_info)

    # 5. Create the new model class
    try:
        new_model_cls = create_model(
            new_model_name,
            __base__=BaseModel,
            __module__=original_cls.__module__,
            **new_fields,
        )
    except Exception as e:
        raise RuntimeError(
            f"Pydantic create_model failed for '{new_model_name}': {e}"
        ) from e

    # 6. Update cache and rebuild
    cache[original_cls] = new_model_cls
    try:
        new_model_cls.model_rebuild(force=True)
    except Exception as e:
        raise RuntimeError(
            f"Pydantic model_rebuild failed for '{new_model_name}' after creation: {e}"
        ) from e

    return new_model_cls


def create_model_with_defaults(
    original_cls: type[BaseModel], mutated_schema: dict[str, Any]
) -> type[BaseModel]:
    """Create a new Pydantic model with defaults from a processed schema.

    This is the main public entry point for model creation with defaults.

    Args:
        original_cls: Original Pydantic model class
        mutated_schema: Schema with defaults already set

    Returns:
        New model class with defaults applied

    Raises:
        TypeError: If schema is not a dictionary
        RuntimeError: If model building fails
    """
    if not isinstance(mutated_schema, dict):
        raise TypeError("mutated_schema must be a dictionary.")

    model_build_cache: dict[type[BaseModel], type[BaseModel] | ForwardRef] = {}

    try:
        new_model_cls = build_model_with_defaults_recursive(
            original_cls=original_cls,
            cache=model_build_cache,
            schema_definition=mutated_schema,
            root_schema=mutated_schema,
        )
    except Exception as e:
        raise RuntimeError(
            f"Failed to build model '{original_cls.__name__}' with new defaults: {e}"
        ) from e

    return new_model_cls
