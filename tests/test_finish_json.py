from __future__ import annotations

import json

import pytest

from pydantic import BaseModel

from delta_stream._errors import DeltaStreamValidationError
from delta_stream._finish_json import _finish_json
from delta_stream.stream_parser import JsonStreamParser


BACK_SLASH = chr(92)  # This is the backslash character in Python

test_cases = [
    # Rule 1: Inside Key String -> None
    ('{"k', None),  # Incomplete key at root
    ('{"outer": {"inner_ke', None),  # Incomplete key nested
    # Incomplete key in object within array
    ('{"data": [{"key": 1, "next_ke', None),
    # Rule 2: Between Tokens -> None ONLY if just saw colon
    ("{", "{}"),  # Just opened object -> Complete
    # After comma in object -> Complete (comma removed)
    ('{"key": "value",', '{"key": "value"}'),
    # After colon -> None (waiting for value)
    ('{"key":', None),
    # After completed object + space -> Complete (space kept)
    ('{"key":123} ', '{"key":123} '),
    # Rule 3: Parsing Incomplete Literal/Number -> None
    ('{"key": tru', None),
    ('{"key": 1.', None),
    ('{"key": -', None),
    ('{"a": [1, 2, fals', None),  # Incomplete literal in array
    ('{"key": 1e', None),
    ('{"key": 1e-', None),
    ('{"a": [ {"b": [ {"c": fals', None),  # Incomplete literal deep nested
    # Rule 4: Inside Value String -> Append Quote and Close Structure
    ('{"key": "val', '{"key": "val"}'),
    # In value string in array
    ('{"arr": ["item1", "ite', '{"arr": ["item1", "ite"]}'),
    # In value string in nested obj
    ('{"obj": {"k": "part', '{"obj": {"k": "part"}}'),
    # In value string deep nested
    ('{"data": [{"config": {"name": "part', '{"data": [{"config": {"name": "part"}}]}'),
    # Rule 5: Closing brackets/braces (Values must be complete)
    # Needs brace, keeps preceding space
    ('{"key": "value" ', '{"key": "value" }'),
    ('{"key": 123', '{"key": 123}'),
    ('{"key": true', '{"key": true}'),
    ('{"key": null', '{"key": null}'),
    ('{"arr": ["abc"', '{"arr": ["abc"]}'),
    ('{"arr": [123', '{"arr": [123]}'),
    ('{"a": {', '{"a": {}}'),
    ('{"a": [1, 2', '{"a": [1, 2]}'),
    ('{"a": {"b": 1', '{"a": {"b": 1}}'),
    ('{"a": {"b": "c"', '{"a": {"b": "c"}}'),
    ('{"a": {"b": false', '{"a": {"b": false}}'),
    # Comma cleanup needed before closing
    ('{"key": 123,', '{"key": 123}'),
    ('{"arr": [true, false,', '{"arr": [true, false]}'),
    ('{"arr": [{"k":1},', '{"arr": [{"k":1}]}'),
    ('{"a": {"b": 1,', '{"a": {"b": 1}}'),
    # Nested comma cleanup
    ('{"data": {"items": [1, 2,', '{"data": {"items": [1, 2]}}'),
    # Nested comma cleanup (array)
    ('{"data": [{"k":1},', '{"data": [{"k":1}]}'),
    # Edge cases / Complete JSON (Object Root)
    ("{}", "{}"),
    ('{"key": 123}', '{"key": 123}'),
    # Ends just after an escaped quote inside value string
    ('{"esc": "abc\\"', '{"esc": "abc\\""}'),
    ('{"key": "val\\\\', '{"key": "val\\\\"}'),
    ('{"mix": "A\\\\\\"B\\\\tC\\\\\\\\D', '{"mix": "A\\\\\\"B\\\\tC\\\\\\\\D"}'),
    ('{"esc_end": "E\\\\nF" ', '{"esc_end": "E\\\\nF" }'),
    ('{"start_esc": "\\\\nHello W', '{"start_esc": "\\\\nHello W"}'),
    ('{"nes": [{"ted": "G\\\\\\"H"', '{"nes": [{"ted": "G\\\\\\"H"}]}'),
    ('{"key"', None),
    # Edge case where string ends with a single backslash
    ('{"key": "value' + BACK_SLASH, '{"key": "value"}'),
]
# Parameterize the test function


@pytest.mark.parametrize("input_snippet, expected_output", test_cases)
def test_finish_json_logic(input_snippet, expected_output):
    """
    Tests the _finish_json function by simulating the state after parsing
    an input snippet and asserting the output matches the expected completion.
    """

    class DummyModel(BaseModel):
        pass

    parser = JsonStreamParser(DummyModel)
    try:
        for char in input_snippet:
            parser._parse_chunk_char(char)
    except DeltaStreamValidationError as e:
        pytest.fail(
            f"Preprocessing snippet '{input_snippet}' failed with validation error: {e}"
        )
    except Exception as e:
        pytest.fail(
            f"Preprocessing snippet '{input_snippet}' failed with unexpected error: {type(e).__name__}: {e}"
        )

    actual_output = _finish_json(parser._state)

    assert (
        actual_output == expected_output
    ), f"Mismatch for input snippet: '{input_snippet}'. Final State was: {parser._state}"

    # Check if the output is valid JSON

    if actual_output:
        try:
            json.loads(actual_output)
        except json.JSONDecodeError:
            pytest.fail(
                f"Output for input snippet '{input_snippet}' is not valid JSON: {actual_output}"
            )
