from __future__ import annotations

from typing import Any


def compute_string_delta(old: str | None, new: str) -> str:
    """
    Computes the delta for two strings for streaming concatenation.

    If the new string starts with the old string (treating None or non-string old
    values as empty string), returns only the appended part (suffix).
    Otherwise, returns the complete new string.

    Args:
        old: The previous string value (or None/non-string).
        new: The current string value.

    Returns:
        The delta string (suffix or full string).
    """
    # Ensure 'new' is treated as a string, handle potential None input if needed by caller
    if not isinstance(new, str):
        # This shouldn't happen if called correctly by compute_delta, but defensive
        return new

    old_str = old if isinstance(old, str) else ""

    if new.startswith(old_str):
        return new[len(old_str) :]

    return new


def compute_delta(prev: dict[str, Any] | None, curr: dict[str, Any]) -> dict:
    """
    Recursively computes a delta dictionary optimized for streaming updates,
    assuming dictionary inputs for states.

    Compares 'curr' dictionary state against 'prev' dictionary state.
    Designed for minimizing network traffic for streamed updates where strings
    are often appended to.

    Delta Calculation Rules:
    - Only keys present in the 'curr' dictionary are included in the delta.
    - For each key in 'curr':
        - If the value is Number, Boolean, or None: The full value from 'curr'
          is included in the delta.
        - If the value is a String: `compute_string_delta` is used to find
          the appended part (or the full string if new/changed).
        - If the value is a List: Compared element-wise recursively using
          these delta rules. Only elements present in the 'curr' list are considered.
        - If the value is a Dictionary: Compared recursively using these delta rules.
        - Other types: The full value from 'curr' is included.

    Args:
        prev: The previous state dictionary, or None if no previous state exists.
        curr: The current state dictionary.

    Returns:
        A dictionary representing the delta. Keys absent from `curr` are omitted.
        String values may only contain the appended suffix.

    Raises:
        TypeError: If 'curr' is not a dictionary at the top level.
    """
    if not isinstance(curr, dict):
        raise TypeError("Top-level 'curr' input to compute_delta must be a dictionary.")

    prev_dict = prev if isinstance(prev, dict) else {}
    delta_dict = {}

    for key, current_val in curr.items():
        previous_val = prev_dict.get(key)

        delta_value = _compute_delta_recursive(previous_val, current_val)

        # Always include the key/delta_value pair for keys present in `curr`.
        # The recursive call handles whether the delta_value is empty (e.g., "" for strings)
        # or full based on the rules.
        delta_dict[key] = delta_value

    return delta_dict


def _compute_delta_recursive(prev_val: Any, current_val: Any) -> Any:
    """Recursive helper for compute_delta, handles non-dict values."""

    # Base case: Current value is None
    if current_val is None:
        return None

    # Rule: Strings use compute_string_delta
    if isinstance(current_val, str):
        # compute_string_delta handles None or non-string prev_val
        return compute_string_delta(prev_val, current_val)

    # Rule: Lists are processed element-wise recursively
    elif isinstance(current_val, list):
        delta_list = []
        prev_list = prev_val if isinstance(prev_val, list) else []
        for i, new_item in enumerate(current_val):
            # Get previous item if index exists, otherwise None
            prev_item = prev_list[i] if i < len(prev_list) else None
            # Recursively compute delta for the item
            delta_list.append(_compute_delta_recursive(prev_item, new_item))
        return delta_list

    # Rule: Dictionaries are processed recursively via main function
    elif isinstance(current_val, dict):
        # Ensure previous value is dict or None for the recursive call
        prev_dict = prev_val if isinstance(prev_val, dict) else None
        # Call main compute_delta for nested dicts
        return compute_delta(prev_dict, current_val)

    # Rule: Numbers, Booleans (and any other non-list/dict/str type)
    # are returned directly from 'curr'
    else:
        return current_val
