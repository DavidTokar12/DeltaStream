"""
Type validators for JSON schema type checking.

This module provides functions to validate Python objects against JSON schema types.
"""

from __future__ import annotations

import numbers

from typing import Any


def is_array(instance: Any) -> bool:
    return isinstance(instance, list)


def is_bool(instance: Any) -> bool:
    return isinstance(instance, bool)


def is_integer(instance: Any) -> bool:
    if isinstance(instance, bool):
        return False
    return isinstance(instance, int)


def is_null(instance: Any) -> bool:
    return instance is None


def is_number(instance: Any) -> bool:
    if isinstance(instance, bool):
        return False
    return isinstance(instance, numbers.Number)


def is_object(instance: Any) -> bool:
    return isinstance(instance, dict)


def is_string(instance: Any) -> bool:
    return isinstance(instance, str)


def is_any(_: Any, instance: Any) -> bool:
    return True


# Mapping of JSON schema types to validator functions
JSON_TYPE_VALIDATORS = {
    "string": is_string,
    "array": is_array,
    "null": is_null,
    "boolean": is_bool,
    "integer": is_integer,
    "number": is_number,
    "object": is_object,
    "any": is_any,
}
