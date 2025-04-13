from __future__ import annotations

import pytest

from pydantic import BaseModel

from delta_stream._errors import DeltaStreamValidationError
from delta_stream._parser_state import ParserState
from delta_stream.stream_parser import JsonStreamParser


json_string = '{"s":"abc","n":null,"b":true,"i":123,"a_s":["xyz"],"a_o":[{"k":1},{"l":2}],"o":{"n":{"m":false}}}'

# Define the expected state *after* processing the character at the given index
# Tuple format: (is_inside_string, expecting_key, inside_key_string, parsing_literal_or_number, stack_list, just_saw_colon, last_char)
# Note: Calculating this manually is tedious and error-prone. Double-check carefully!
# Note: last_char in the tuple represents the state *after* processing the char at that index.
expected_states_tuples = [
    # Char 0: {
    (False, True, False, False, ["{"], False, False, "{"),
    # Char 1: "
    (True, False, True, False, ["{"], False, False, '"'),
    # Char 2: s
    (True, False, True, False, ["{"], False, False, "s"),
    # Char 3: " (closing key) → recently_finished_key becomes True.
    (False, False, False, False, ["{"], False, True, '"'),
    # Char 4: : → colon resets recently_finished_key.
    (False, False, False, False, ["{"], True, False, ":"),
    # Char 5: " (starting value string; not a key)
    (True, False, False, False, ["{"], False, False, '"'),
    # Char 6: a
    (True, False, False, False, ["{"], False, False, "a"),
    # Char 7: b
    (True, False, False, False, ["{"], False, False, "b"),
    # Char 8: c
    (True, False, False, False, ["{"], False, False, "c"),
    # Char 9: " (closing value string; no recently_finished_key for value strings)
    (False, False, False, False, ["{"], False, False, '"'),
    # Char 10: , → After comma, expecting_key becomes True.
    (False, True, False, False, ["{"], False, False, ","),
    # Char 11: " (starting key string)
    (True, False, True, False, ["{"], False, False, '"'),
    # Char 12: n
    (True, False, True, False, ["{"], False, False, "n"),
    # Char 13: " (closing key) → recently_finished_key becomes True.
    (False, False, False, False, ["{"], False, True, '"'),
    # Char 14: : → resets recently_finished_key.
    (False, False, False, False, ["{"], True, False, ":"),
    # Char 15: n (starting literal/number)
    (False, False, False, True, ["{"], False, False, "n"),
    # Char 16: u
    (False, False, False, True, ["{"], False, False, "u"),
    # Char 17: l
    (False, False, False, True, ["{"], False, False, "l"),
    # Char 18: l
    (False, False, False, True, ["{"], False, False, "l"),
    # Char 19: , → Literal finished; after comma expecting_key True.
    (False, True, False, False, ["{"], False, False, ","),
    # Char 20: " (starting key string)
    (True, False, True, False, ["{"], False, False, '"'),
    # Char 21: b
    (True, False, True, False, ["{"], False, False, "b"),
    # Char 22: " (closing key) → recently_finished_key becomes True.
    (False, False, False, False, ["{"], False, True, '"'),
    # Char 23: : → resets recently_finished_key.
    (False, False, False, False, ["{"], True, False, ":"),
    # Char 24: t (starting literal/number)
    (False, False, False, True, ["{"], False, False, "t"),
    # Char 25: r
    (False, False, False, True, ["{"], False, False, "r"),
    # Char 26: u
    (False, False, False, True, ["{"], False, False, "u"),
    # Char 27: e
    (False, False, False, True, ["{"], False, False, "e"),
    # Char 28: , → literal finished; comma resets.
    (False, True, False, False, ["{"], False, False, ","),
    # Char 29: " (starting key string)
    (True, False, True, False, ["{"], False, False, '"'),
    # Char 30: i
    (True, False, True, False, ["{"], False, False, "i"),
    # Char 31: " (closing key) → recently_finished_key = True.
    (False, False, False, False, ["{"], False, True, '"'),
    # Char 32: : → resets recently_finished_key.
    (False, False, False, False, ["{"], True, False, ":"),
    # Char 33: 1 (starting literal)
    (False, False, False, True, ["{"], False, False, "1"),
    # Char 34: 2
    (False, False, False, True, ["{"], False, False, "2"),
    # Char 35: 3
    (False, False, False, True, ["{"], False, False, "3"),
    # Char 36: , → comma resets.
    (False, True, False, False, ["{"], False, False, ","),
    # Char 37: " (starting key string)
    (True, False, True, False, ["{"], False, False, '"'),
    # Char 38: a
    (True, False, True, False, ["{"], False, False, "a"),
    # Char 39: _
    (True, False, True, False, ["{"], False, False, "_"),
    # Char 40: s
    (True, False, True, False, ["{"], False, False, "s"),
    # Char 41: " (closing key) → recently_finished_key becomes True.
    (False, False, False, False, ["{"], False, True, '"'),
    # Char 42: : → resets recently_finished_key.
    (False, False, False, False, ["{"], True, False, ":"),
    # Char 43: [ → push "[" onto stack.
    (False, False, False, False, ["{", "["], False, False, "["),
    # Char 44: " (starting value string in array)
    (True, False, False, False, ["{", "["], False, False, '"'),
    # Char 45: x
    (True, False, False, False, ["{", "["], False, False, "x"),
    # Char 46: y
    (True, False, False, False, ["{", "["], False, False, "y"),
    # Char 47: z
    (True, False, False, False, ["{", "["], False, False, "z"),
    # Char 48: " (closing value string)
    (False, False, False, False, ["{", "["], False, False, '"'),
    # Char 49: ] (pop "[" off stack)
    (False, False, False, False, ["{"], False, False, "]"),
    # Char 50: , → after comma expecting_key becomes True.
    (False, True, False, False, ["{"], False, False, ","),
    # Char 51: " (starting key string)
    (True, False, True, False, ["{"], False, False, '"'),
    # Char 52: a
    (True, False, True, False, ["{"], False, False, "a"),
    # Char 53: _
    (True, False, True, False, ["{"], False, False, "_"),
    # Char 54: o
    (True, False, True, False, ["{"], False, False, "o"),
    # Char 55: " (closing key) → recently_finished_key = True.
    (False, False, False, False, ["{"], False, True, '"'),
    # Char 56: : → resets recently_finished_key.
    (False, False, False, False, ["{"], True, False, ":"),
    # Char 57: [ → push "["; stack becomes ["{", "["].
    (False, False, False, False, ["{", "["], False, False, "["),
    # Char 58: { → push "{"; expecting_key True.
    (False, True, False, False, ["{", "[", "{"], False, False, "{"),
    # Char 59: " (starting key string)
    (True, False, True, False, ["{", "[", "{"], False, False, '"'),
    # Char 60: k
    (True, False, True, False, ["{", "[", "{"], False, False, "k"),
    # Char 61: " (closing key) → recently_finished_key = True.
    (False, False, False, False, ["{", "[", "{"], False, True, '"'),
    # Char 62: : → resets recently_finished_key.
    (False, False, False, False, ["{", "[", "{"], True, False, ":"),
    # Char 63: 1 (starting literal)
    (False, False, False, True, ["{", "[", "{"], False, False, "1"),
    # Char 64: } → pop "{" off stack.
    (False, False, False, False, ["{", "["], False, False, "}"),
    # Char 65: ,
    (False, False, False, False, ["{", "["], False, False, ","),
    # Char 66: { → push "{"; expecting_key True.
    (False, True, False, False, ["{", "[", "{"], False, False, "{"),
    # Char 67: " (starting key string)
    (True, False, True, False, ["{", "[", "{"], False, False, '"'),
    # Char 68: l
    (True, False, True, False, ["{", "[", "{"], False, False, "l"),
    # Char 69: " (closing key) → recently_finished_key = True.
    (False, False, False, False, ["{", "[", "{"], False, True, '"'),
    # Char 70: : → resets recently_finished_key.
    (False, False, False, False, ["{", "[", "{"], True, False, ":"),
    # Char 71: 2 (starting literal)
    (False, False, False, True, ["{", "[", "{"], False, False, "2"),
    # Char 72: } → pop "{"; stack becomes ["{", "["].
    (False, False, False, False, ["{", "["], False, False, "}"),
    # Char 73: ] → pop "["; stack becomes ["{"].
    (False, False, False, False, ["{"], False, False, "]"),
    # Char 74: , → after comma, expecting_key True.
    (False, True, False, False, ["{"], False, False, ","),
    # Char 75: " (starting key string)
    (True, False, True, False, ["{"], False, False, '"'),
    # Char 76: o
    (True, False, True, False, ["{"], False, False, "o"),
    # Char 77: " (closing key) → recently_finished_key True.
    (False, False, False, False, ["{"], False, True, '"'),
    # Char 78: : → resets recently_finished_key.
    (False, False, False, False, ["{"], True, False, ":"),
    # Char 79: { → push "{"; expecting_key True.
    (False, True, False, False, ["{", "{"], False, False, "{"),
    # Char 80: " (starting key string)
    (True, False, True, False, ["{", "{"], False, False, '"'),
    # Char 81: n
    (True, False, True, False, ["{", "{"], False, False, "n"),
    # Char 82: " (closing key) → recently_finished_key True.
    (False, False, False, False, ["{", "{"], False, True, '"'),
    # Char 83: : → resets recently_finished_key.
    (False, False, False, False, ["{", "{"], True, False, ":"),
    # Char 84: { → push "{"; expecting_key True.
    (False, True, False, False, ["{", "{", "{"], False, False, "{"),
    # Char 85: " (starting key string)
    (True, False, True, False, ["{", "{", "{"], False, False, '"'),
    # Char 86: m
    (True, False, True, False, ["{", "{", "{"], False, False, "m"),
    # Char 87: " (closing key) → recently_finished_key True.
    (False, False, False, False, ["{", "{", "{"], False, True, '"'),
    # Char 88: : → resets recently_finished_key.
    (False, False, False, False, ["{", "{", "{"], True, False, ":"),
    # Char 89: f (starting literal)
    (False, False, False, True, ["{", "{", "{"], False, False, "f"),
    # Char 90: a
    (False, False, False, True, ["{", "{", "{"], False, False, "a"),
    # Char 91: l
    (False, False, False, True, ["{", "{", "{"], False, False, "l"),
    # Char 92: s
    (False, False, False, True, ["{", "{", "{"], False, False, "s"),
    # Char 93: e
    (False, False, False, True, ["{", "{", "{"], False, False, "e"),
    # Char 94: } → pop "{"; stack becomes ["{", "{"].
    (False, False, False, False, ["{", "{"], False, False, "}"),
    # Char 95: } → pop "{"; stack becomes ["{"].
    (False, False, False, False, ["{"], False, False, "}"),
    # Char 96: } → pop "{"; stack becomes [].
    (False, False, False, False, [], False, False, "}"),
]


def test_parse_delta_char_state_transitions():
    """
    Tests the state transitions of _parse_delta_char by processing a complex
    JSON string character by character and asserting the expected state after each char.
    """

    class DummyModel(BaseModel):
        pass

    parser = JsonStreamParser(DummyModel)  # Use dummy model

    assert len(json_string) == len(
        expected_states_tuples
    ), f"Mismatch between JSON string length ({len(json_string)}) and expected states ({len(expected_states_tuples)})"

    for i, char in enumerate(json_string):
        # Construct the expected state for this step
        expected_tuple = expected_states_tuples[i]
        expected_state = ParserState(
            is_inside_string=expected_tuple[0],
            expecting_key=expected_tuple[1],
            inside_key_string=expected_tuple[2],
            parsing_literal_or_number=expected_tuple[3],
            parenthesis_stack=list(expected_tuple[4]),  # Ensure list copy
            just_saw_colon=expected_tuple[5],
            # NEW: index 6 for recently_finished_key
            recently_finished_key=expected_tuple[6],
            last_char=expected_tuple[7],  # index 7 for last_char
            aggregated_json_string=json_string[: i + 1],
        )
        try:
            parser._parse_chunk_char(char)
            current_state = parser._state

            # Assert the full state matches
            # pytest will give a nice diff if they don't match
            assert (
                current_state == expected_state
            ), f"State mismatch after char {i} ('{char}')"

        except DeltaStreamValidationError as e:
            pytest.fail(
                f"Validation error raised unexpectedly at char {i} ('{char}'): {e}\n"
                f"State before error: {expected_states_tuples[i-1] if i > 0 else 'Initial'}\n"
                f"Expected state: {expected_state}"
            )
        except Exception as e:
            pytest.fail(
                f"Unexpected error at char {i} ('{char}'): {type(e).__name__}: {e}\n"
                f"State before error: {expected_states_tuples[i-1] if i > 0 else 'Initial'}\n"
                f"Expected state: {expected_state}"
            )


whitespace_json_string = (
    '{\n   "key" :   123 ,\n   "another" : [\n      true ,\n      false\n   ]\n}\n'
)
whitespace_expected_states_tuples = [
    # Format:
    # (is_inside_string, expecting_key, inside_key_string, parsing_literal_or_number,
    #  parenthesis_stack, just_saw_colon, recently_finished_key, last_char)
    # Char 0: '{'
    (False, True, False, False, ["{"], False, False, "{"),
    # Char 1: '\n'
    (False, True, False, False, ["{"], False, False, "\n"),
    # Char 2: ' '
    (False, True, False, False, ["{"], False, False, " "),
    # Char 3: ' '
    (False, True, False, False, ["{"], False, False, " "),
    # Char 4: ' '
    (False, True, False, False, ["{"], False, False, " "),
    # Char 5: '"' - start key string
    (True, False, True, False, ["{"], False, False, '"'),
    # Char 6: 'k'
    (True, False, True, False, ["{"], False, False, "k"),
    # Char 7: 'e'
    (True, False, True, False, ["{"], False, False, "e"),
    # Char 8: 'y'
    (True, False, True, False, ["{"], False, False, "y"),
    # Char 9: '"' - closing key; set recently_finished_key True
    (False, False, False, False, ["{"], False, True, '"'),
    # Char 10: ' ' - whitespace after key; key still recently finished
    (False, False, False, False, ["{"], False, True, " "),
    # Char 11: ':' - colon resets recently_finished_key and sets just_saw_colon
    (False, False, False, False, ["{"], True, False, ":"),
    # Char 12: ' '
    (False, False, False, False, ["{"], True, False, " "),
    # Char 13: ' '
    (False, False, False, False, ["{"], True, False, " "),
    # Char 14: ' '
    (False, False, False, False, ["{"], True, False, " "),
    # Char 15: '1' - literal starts
    (False, False, False, True, ["{"], False, False, "1"),
    # Char 16: '2'
    (False, False, False, True, ["{"], False, False, "2"),
    # Char 17: '3'
    (False, False, False, True, ["{"], False, False, "3"),
    # Char 18: ' '
    (False, False, False, False, ["{"], False, False, " "),
    # Char 19: ',' - comma; new key expected
    (False, True, False, False, ["{"], False, False, ","),
    # Char 20: '\n'
    (False, True, False, False, ["{"], False, False, "\n"),
    # Char 21: ' '
    (False, True, False, False, ["{"], False, False, " "),
    # Char 22: ' '
    (False, True, False, False, ["{"], False, False, " "),
    # Char 23: ' '
    (False, True, False, False, ["{"], False, False, " "),
    # Char 24: '"' - start key string
    (True, False, True, False, ["{"], False, False, '"'),
    # Char 25: 'a'
    (True, False, True, False, ["{"], False, False, "a"),
    # Char 26: 'n'
    (True, False, True, False, ["{"], False, False, "n"),
    # Char 27: 'o'
    (True, False, True, False, ["{"], False, False, "o"),
    # Char 28: 't'
    (True, False, True, False, ["{"], False, False, "t"),
    # Char 29: 'h'
    (True, False, True, False, ["{"], False, False, "h"),
    # Char 30: 'e'
    (True, False, True, False, ["{"], False, False, "e"),
    # Char 31: 'r'
    (True, False, True, False, ["{"], False, False, "r"),
    # Char 32: '"' - closing key; set recently_finished_key True
    (False, False, False, False, ["{"], False, True, '"'),
    # Char 33: ' ' - whitespace remains; recently_finished_key stays True
    (False, False, False, False, ["{"], False, True, " "),
    # Char 34: ':' - colon resets recently_finished_key and sets just_saw_colon
    (False, False, False, False, ["{"], True, False, ":"),
    # Char 35: ' '
    (False, False, False, False, ["{"], True, False, " "),
    # Char 36: '[' - push array; stack becomes ["{", "["]
    (False, False, False, False, ["{", "["], False, False, "["),
    # Char 37: '\n'
    (False, False, False, False, ["{", "["], False, False, "\n"),
    # Char 38: ' '
    (False, False, False, False, ["{", "["], False, False, " "),
    # Char 39: ' '
    (False, False, False, False, ["{", "["], False, False, " "),
    # Char 40: ' '
    (False, False, False, False, ["{", "["], False, False, " "),
    # Char 41: ' '
    (False, False, False, False, ["{", "["], False, False, " "),
    # Char 42: ' ' - missing originally, treat as ordinary whitespace
    (False, False, False, False, ["{", "["], False, False, " "),
    # Char 43: ' ' - missing originally
    (False, False, False, False, ["{", "["], False, False, " "),
    # Char 44: 't' - literal starts; in array element
    (False, False, False, True, ["{", "["], False, False, "t"),
    # Char 45: 'r'
    (False, False, False, True, ["{", "["], False, False, "r"),
    # Char 46: 'u'
    (False, False, False, True, ["{", "["], False, False, "u"),
    # Char 47: 'e'
    (False, False, False, True, ["{", "["], False, False, "e"),
    # Char 48: ' ' - terminator for literal; literal mode ends
    (False, False, False, False, ["{", "["], False, False, " "),
    # Char 49: ','
    (False, False, False, False, ["{", "["], False, False, ","),
    # Char 50: '\n'
    (False, False, False, False, ["{", "["], False, False, "\n"),
    # Char 51: ' '
    (False, False, False, False, ["{", "["], False, False, " "),
    # Char 52: ' '
    (False, False, False, False, ["{", "["], False, False, " "),
    # Char 53: ' '
    (False, False, False, False, ["{", "["], False, False, " "),
    # Char 54: ' '
    (False, False, False, False, ["{", "["], False, False, " "),
    # Char 55: ' ' - missing originally
    (False, False, False, False, ["{", "["], False, False, " "),
    # Char 56: ' ' - missing originally
    (False, False, False, False, ["{", "["], False, False, " "),
    # Char 57: 'f' - literal for "false"
    (False, False, False, True, ["{", "["], False, False, "f"),
    # Char 58: 'a'
    (False, False, False, True, ["{", "["], False, False, "a"),
    # Char 59: 'l'
    (False, False, False, True, ["{", "["], False, False, "l"),
    # Char 60: 's'
    (False, False, False, True, ["{", "["], False, False, "s"),
    # Char 61: 'e'
    (False, False, False, True, ["{", "["], False, False, "e"),
    # Char 62: '\n'
    (False, False, False, False, ["{", "["], False, False, "\n"),
    # Char 63: ' '
    (False, False, False, False, ["{", "["], False, False, " "),
    # Char 64: ' '
    (False, False, False, False, ["{", "["], False, False, " "),
    (False, False, False, False, ["{", "["], False, False, " "),
    # Char 66: '\n'
    # Char 65: ']' - pop array; now stack becomes ["{"]
    (False, False, False, False, ["{"], False, False, "]"),
    # Char 67: ' '
    (False, False, False, False, ["{"], False, False, "\n"),
    # Char 68: '}' - pop object; stack becomes []
    (False, False, False, False, [], False, False, "}"),
    # Char 69: '\n'
    (False, False, False, False, [], False, False, "\n"),
]


def test_parse_delta_char_with_whitespace():
    """
    Tests the state transitions of _parse_delta_char when processing JSON
    containing significant whitespace between tokens.
    """

    class DummyModel(BaseModel):
        pass

    parser = JsonStreamParser(DummyModel)  # Use dummy model

    assert len(whitespace_json_string) == len(
        whitespace_expected_states_tuples
    ), f"Mismatch between whitespace JSON string length ({len(whitespace_json_string)}) and expected states ({len(whitespace_expected_states_tuples)})"

    for i, char in enumerate(whitespace_json_string):
        # Construct the expected state for this step
        expected_tuple = whitespace_expected_states_tuples[i]
        expected_state = ParserState(
            is_inside_string=expected_tuple[0],
            expecting_key=expected_tuple[1],
            inside_key_string=expected_tuple[2],
            parsing_literal_or_number=expected_tuple[3],
            parenthesis_stack=list(expected_tuple[4]),
            just_saw_colon=expected_tuple[5],
            recently_finished_key=expected_tuple[6],
            last_char=expected_tuple[7],
            aggregated_json_string=whitespace_json_string[: i + 1],
        )

        try:
            parser._parse_chunk_char(char)
            current_state = parser._state

            assert (
                current_state
                == expected_state
                # Use repr for whitespace chars
            ), f"State mismatch after char {i} ('{char!r}')"

        except DeltaStreamValidationError as e:
            pytest.fail(
                f"Validation error raised unexpectedly at char {i} ('{char!r}'): {e}\n"
                f"State before error: {whitespace_expected_states_tuples[i-1] if i > 0 else 'Initial'}\n"
                f"Expected state for this char: {expected_state}\n"
                f"Aggregated string when error occurred: {parser._state.aggregated_json_string}"
            )
        except Exception as e:
            pytest.fail(
                f"Unexpected error at char {i} ('{char!r}'): {type(e).__name__}: {e}\n"
                f"State before error: {whitespace_expected_states_tuples[i-1] if i > 0 else 'Initial'}\n"
                f"Expected state for this char: {expected_state}\n"
                f"Aggregated string when error occurred: {parser._state.aggregated_json_string}"
            )

    # Optional: Add a final assertion on the total aggregated string if desired
    assert (
        parser._state.aggregated_json_string == whitespace_json_string
    ), "Final aggregated string doesn't match input"
