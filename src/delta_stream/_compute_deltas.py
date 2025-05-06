from __future__ import annotations

from enum import Enum as PythonEnum
from typing import Any

from pydantic import BaseModel


def compute_string_delta(old: str | None, new: str) -> str:
    if not isinstance(new, str):
        return new
    old_str = old if isinstance(old, str) else ""
    if new.startswith(old_str):
        return new[len(old_str) :]
    return new


def _compute_delta_recursive(prev_val: Any, current_val: Any) -> Any:
    if current_val is None:
        return None
    if isinstance(current_val, PythonEnum):  # Use aliased PythonEnum
        return current_val.value
    if isinstance(current_val, str):
        old_for_string_delta: str | None = None
        if isinstance(prev_val, str):
            old_for_string_delta = prev_val
        elif isinstance(prev_val, PythonEnum) and isinstance(prev_val.value, str):
            old_for_string_delta = prev_val.value
        return compute_string_delta(old_for_string_delta, current_val)
    elif isinstance(current_val, list):
        delta_list = []
        prev_list = prev_val if isinstance(prev_val, list) else []
        for i, new_item in enumerate(current_val):
            prev_item = prev_list[i] if i < len(prev_list) else None
            delta_list.append(_compute_delta_recursive(prev_item, new_item))
        return delta_list
    elif isinstance(current_val, BaseModel):
        prev_model = prev_val if isinstance(prev_val, BaseModel) else None
        # Recursive call to the modified compute_delta
        return compute_delta(prev_model, current_val)
    elif isinstance(current_val, dict):
        delta_nested_dict = {}
        prev_dict_val = prev_val if isinstance(prev_val, dict) else {}
        for key, value_in_curr_dict in current_val.items():
            value_in_prev_dict = prev_dict_val.get(key)
            delta_nested_dict[key] = _compute_delta_recursive(
                value_in_prev_dict, value_in_curr_dict
            )
        return delta_nested_dict
    else:
        return current_val


# compute_delta (MODIFIED from the Pydantic-aware version)


def compute_delta(prev: BaseModel | None, curr: BaseModel) -> dict[str, Any]:
    if not isinstance(curr, BaseModel):
        raise TypeError(
            "Top-level 'curr' input to compute_delta must be a Pydantic BaseModel."
        )
    delta_dict = {}

    # MODIFICATION HERE: Iterate over keys from model_dump(exclude_unset=True)
    # This ensures we only process fields that were explicitly set on the 'curr' model,
    # aligning with the original behavior of "only keys present in curr dict".
    # For Pydantic V2, exclude_unset=True is the correct flag.
    # exclude_none=False to keep explicitly set None values
    for field_name in curr.model_dump(exclude_unset=True, exclude_none=False):
        current_field_value = getattr(curr, field_name)
        previous_field_value = None

        if prev and (
            field_name in prev.model_fields
        ):  # Check if field exists in prev model's definition
            previous_field_value = getattr(prev, field_name)

        delta_value = _compute_delta_recursive(
            previous_field_value, current_field_value
        )
        delta_dict[field_name] = delta_value

    return delta_dict
