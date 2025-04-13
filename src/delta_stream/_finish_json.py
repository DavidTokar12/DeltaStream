from __future__ import annotations

import json

from delta_stream._parser_state import ParserState


def _finish_json(state: ParserState) -> str | None:
    """
    Attempts to construct a syntactically complete JSON string based on the parser state.

    This function takes the current state of the parser (including the aggregated
    JSON string seen so far and the parenthesis stack) and tries to append the
    necessary closing characters ('"', '}', ']') to form a potentially valid JSON
    document that can be subsequently parsed.

    It applies specific rules based on the state:
    - Returns None if the state indicates parsing stopped inside an incomplete
      key string (`inside_key_string` is True).
    - Returns None if the state indicates the parser is between distinct JSON tokens
      (i.e., not inside a string, not inside a key, and not actively parsing a
      literal or number). This prevents attempts to parse when the stream is
      waiting for the next key or value start.
    - Returns None if the state indicates parsing stopped while processing an
      incomplete or invalid literal or number (`parsing_literal_or_number`
      is True and the extracted partial value fails a `json.loads` check).
    - If the state indicates parsing stopped inside a value string
      (`is_inside_string` is True), a closing quote ('"') is appended to the candidate string.
    - Closing brackets (']') and braces ('}') are appended according to the
      `parenthesis_stack` (in reverse order).
    - Trailing commas are automatically cleaned up before appending closing
      brackets/braces if necessary.

    Args:
        state: The current state (`ParserState` object) of the JSON stream parser,
               reflecting the point reached after processing the last delta.

    Returns:
        The potentially completed JSON string if the completion attempt was possible
        under the rules and resulted in a non-empty string. Returns None if the state
        prevents a completion attempt (e.g., inside key, between tokens, incomplete literal).
        Note: The returned string is not guaranteed to be fully valid JSON in all edge cases,
        but represents the best attempt at structural completion. Final parsing and
        validation should be done by the caller.
    """

    # Rule 1: If still inside an incomplete key, cannot parse yet.
    if state.inside_key_string:
        return None

    # Rule 2: If the stream stopped immediately after a colon, waiting for a value.
    if state.just_saw_colon:
        return None

    if state.recently_finished_key:
        return None

    # Rule 3 (Revised): Check if parsing an incomplete literal/number
    if state.parsing_literal_or_number:

        start_index = -1
        temp_agg_string = state.aggregated_json_string

        for i in range(len(temp_agg_string) - 1, -1, -1):
            char = temp_agg_string[i]
            if char in ":[,{":  # Delimiters that precede a value
                start_index = i + 1
                break

        partial_value_str = temp_agg_string[start_index:].strip()

        # Attempt to parse *just* the potential literal/number substring
        try:
            json.loads(partial_value_str)
            # If it loads successfully, it means the literal/number *was* complete.
            # Proceed to close brackets below.
        except json.JSONDecodeError:
            # It's an incomplete or invalid literal/number. Cannot parse yet.
            return None

    # If we are here, we are not inside a key and not inside an *incomplete* literal/number.

    # Prepare candidate string for parsing
    candidate_string = state.aggregated_json_string
    suffix = ""

    # Rule 4: If inside a (value) string, close it for the candidate.
    if state.is_inside_string:
        candidate_string += '"'

    # Rule 5: Close open parentheses/brackets based on the stack
    for bracket_type in reversed(state.parenthesis_stack):
        if bracket_type == "{":
            suffix += "}"
        elif bracket_type == "[":
            suffix += "]"

    # Clean potential trailing comma *before* adding suffix
    cleaned_candidate = candidate_string.rstrip()

    # Only remove comma if we are adding a suffix (closing bracket/brace)
    if cleaned_candidate.endswith(",") and suffix:
        candidate_string = cleaned_candidate[:-1].rstrip()

    # Append the closing suffix
    candidate_string += suffix

    return candidate_string
