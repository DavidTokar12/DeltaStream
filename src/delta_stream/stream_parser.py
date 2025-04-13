from __future__ import annotations

import inspect
import json

from typing import Generic
from typing import TypeVar

from pydantic import BaseModel
from pydantic import ValidationError

from delta_stream._compute_deltas import compute_delta
from delta_stream._errors import DeltaStreamModelBuildError
from delta_stream._errors import DeltaStreamValidationError
from delta_stream._finish_json import _finish_json
from delta_stream._generate_model import _generate_model_with_defaults
from delta_stream._parser_state import ParserState


T = TypeVar("T")


class JsonStreamParser(Generic[T]):
    """
    Parses a JSON data stream incrementally, attempting to validate and reconstruct
    a Pydantic model instance.

    This parser handles potentially incomplete JSON chunks and uses a Pydantic model
    (with stream-specific defaults applied internally) to guide parsing attempts.
    It can return the complete object upon successful parsing of a chunk or
    optionally compute the difference (delta) from the previously returned object.

    Attributes:
        data_model (Type[T]): The original target Pydantic model class.
        stream_data_model (Type[T]): An internally generated Pydantic model class
                                     with streaming defaults applied. Used for validation
                                     and default filling during stream parsing attempts.
        delta_mode (bool): If True, `parse` returns the delta from the previous object.
    """

    def __init__(self, data_model: type[T], delta_mode: bool = False) -> None:
        """
        Initializes the JsonStreamParser.

        Args:
            data_model: The target Pydantic BaseModel class definition to parse into.
            delta_mode: If True, the `parse` method will return only the computed
                           difference (delta) between the newly parsed object and the
                           previous one. Defaults to False, returning the full object.

        Raises:
            TypeError: If data_model is not a supported Pydantic class.
            RuntimeError: If the internal streaming model generation fails.
        """
        if not inspect.isclass(data_model):
            raise TypeError("data_model must be a class.")

        if issubclass(data_model, BaseModel):
            self.data_model: type[T] = data_model
        # TODO: handle pydantic dataclasses, and dataclasses
        # elif is_pydantic_dataclass(data_model):
        #     self.data_model = TypeAdapter(data_model)
        #     self.json_schema = self.data_model.json_schema()
        # elif is_dataclass(data_model):
        #     self.data_model = TypeAdapter(pydantic_dataclass(data_model))
        #     self.json_schema = self.data_model.json_schema()
        else:
            raise TypeError(
                "data_model must be a Pydantic BaseModel, Pydantic dataclass or a dataclass."
            )

        try:
            self.stream_data_model = _generate_model_with_defaults(
                self.data_model,
            )
        except DeltaStreamModelBuildError as e:
            raise DeltaStreamModelBuildError(
                f"Failed to generate streaming model for {self.data_model.__name__}"
            ) from e
        except Exception as e:
            raise DeltaStreamModelBuildError(
                f"Unexpected error while generating streaming model: {e}"
            ) from e

        self._delta_mode: bool = delta_mode
        self._previous_result: dict | None = None
        self._state: ParserState = ParserState(parenthesis_stack=[])

    def parse_chunk(self, chunk: str) -> T | None:
        """
        Processes an incoming chunk of the JSON string stream and updates the internal state.

        Attempts to parse the aggregated data after processing the chunk. If the data
        forms a complete and valid JSON structure according to the model, a result is
        returned. Otherwise, None is returned, indicating the stream is still incomplete
        or the current state prevents a valid parse attempt (e.g., inside an incomplete key).

        Args:
            chunk: The next chunk of the JSON string stream.

        Returns:
            An instance of the model `T` if the chunk completed a valid JSON object
            that passes validation. If `compute_diffs` is True, this instance
            represents only the changes since the last returned object.
            Returns `None` if the stream is still incomplete or a parsable/valid
            object could not be formed after processing the chunk.

        Raises:
            DeltaStreamValidationError: If the incoming chunk contains invalid JSON syntax
                                       based on the current parsing context.
            TypeError: If the input chunk is not a string.
        """

        if not isinstance(chunk, str):
            raise TypeError("delta must be a string.")

        if not self._state.aggregated_json_string and not self._state.parenthesis_stack:
            chunk = chunk.lstrip()
            if not chunk:  # Ignore pure whitespace if nothing has been aggregated
                return None

        #  Process characters one by one, updating state
        for char in chunk:
            self._parse_chunk_char(char)

        candidate_string = _finish_json(state=self._state)

        if candidate_string is None:
            return None

        full_obj = None

        try:
            full_obj = self.parse_json(candidate_string)
        except ValidationError as e:
            raise DeltaStreamValidationError(
                f"Validation error during final parsing: {e}"
            ) from e
        except json.JSONDecodeError as e:
            raise DeltaStreamValidationError(
                f"JSON parsing error during final parsing: {candidate_string}"
            ) from e
        except Exception as e:
            raise DeltaStreamValidationError(
                f"Unexpected error during final parsing: {e}"
            ) from e

        if not self._delta_mode:
            return full_obj

        result_dict = full_obj.model_dump()
        delta_result = compute_delta(self._previous_result, result_dict) or {}

        self._previous_result = result_dict

        return self.parse_json(delta_result)

    def _parse_chunk_char(self, char: str) -> None:
        """
        Processes a single character from the input stream, updating the parser state accordingly.

        The function supports:
        - Literal/number parsing with a mechanism to “replay” terminator characters.
        - String parsing with proper handling of escape sequences.
        - Structural characters (whitespace, quotes, colons, commas, braces, and brackets)
            updating the parenthesis stack and key expectation flag.

        Raises:
        DeltaStreamValidationError: On invalid character sequences or state.
        """
        # Cache the last character (for use in determining escapes)
        saw_colon = self._state.just_saw_colon

        # --- 1. Handle literal/number parsing mode ---
        if self._state.parsing_literal_or_number:
            if char in ",}]" or char.isspace():
                # Terminator encountered; finish literal parsing and fall through to re-process this char.
                self._state.parsing_literal_or_number = False
                # (Don't immediately return—drop through to structural processing.)
            else:
                # Still within the literal/number: consume the char and update state.
                self._state.aggregated_json_string += char
                self._state.last_char = char
                return  # Nothing else to do

        # --- 2. Handle string parsing mode ---
        if self._state.is_inside_string:
            if char == '"' and not self._is_escaped_quote():
                self._state.is_inside_string = False
                if self._state.inside_key_string:
                    self._state.recently_finished_key = True
                self._state.inside_key_string = False
                self._state.just_saw_colon = False

            self._state.aggregated_json_string += char
            self._state.last_char = char
            return

        # --- 3. Structural processing (outside string and literal) ---
        # If the current char is not whitespace, reset colon flag.
        if not char.isspace():
            self._state.just_saw_colon = False

        # Process whitespace: simply accumulate and do nothing else.
        if char.isspace():
            self._state.aggregated_json_string += char
            self._state.last_char = char
            return

        # Process structural punctuation and delimiters.
        if char == '"':
            # Entering a string
            self._state.is_inside_string = True
            if self._state.expecting_key:
                self._state.inside_key_string = True
                self._state.expecting_key = False
            else:
                self._state.inside_key_string = False

        elif char == "{":
            self._state.parenthesis_stack.append("{")
            self._state.expecting_key = True

        elif char == "[":
            self._state.parenthesis_stack.append("[")
            self._state.expecting_key = False

        elif char == "}":
            if (
                not self._state.parenthesis_stack
                or self._state.parenthesis_stack.pop() != "{"
            ):
                raise DeltaStreamValidationError("Unexpected '}' or mismatched braces.")
            self._state.expecting_key = False

        elif char == "]":
            if (
                not self._state.parenthesis_stack
                or self._state.parenthesis_stack.pop() != "["
            ):
                raise DeltaStreamValidationError(
                    "Unexpected ']' or mismatched brackets."
                )
            self._state.expecting_key = False

        elif char == ":":
            self._state.expecting_key = False
            self._state.just_saw_colon = True
            self._state.recently_finished_key = False
        elif char == ",":
            if not self._state.parenthesis_stack:
                raise DeltaStreamValidationError(
                    "Unexpected ',' outside of array or object."
                )
            # In objects, a comma signals that a new key is expected;
            # in arrays, it simply separates values.
            if self._state.parenthesis_stack[-1] == "{":
                self._state.expecting_key = True
            elif self._state.parenthesis_stack[-1] == "[":
                self._state.expecting_key = False

        # If a colon was seen, the next non-structural character starts a literal/number.
        elif saw_colon:
            if char in '"{[,:]}' or char.isspace():
                raise DeltaStreamValidationError(
                    f"Unexpected character '{char}' after colon."
                )
            # Start literal/number mode and reconsume this char.
            self._state.parsing_literal_or_number = True
            self._state.aggregated_json_string += char
            self._state.last_char = char
            return

        # Check for literal/number start in array or at the root level.
        elif not self._state.expecting_key and (
            not self._state.parenthesis_stack
            or self._state.parenthesis_stack[-1] == "["
        ):
            if char in "tfn" or char.isdigit() or char == "-":
                self._state.parsing_literal_or_number = True
                self._state.aggregated_json_string += char
                self._state.last_char = char
                return
            else:
                raise DeltaStreamValidationError(
                    f"Unexpected character '{char}' as start of value."
                )

        else:
            raise DeltaStreamValidationError(
                f"Unexpected character '{char}' in JSON structure. State: {self._state}"
            )

        # --- Final step: Update aggregated output and last_char ---
        self._state.aggregated_json_string += char
        self._state.last_char = char

    def _is_escaped_quote(self) -> bool:
        """
        Determines if the most recent quote character is escaped.
        It counts consecutive backslashes in the aggregated JSON string.

        Returns:
        True if the quote is escaped (an odd number of backslashes precede it),
        False otherwise.
        """
        count = 0
        # Examine the aggregated string from the end backward.
        idx = len(self._state.aggregated_json_string) - 1
        while idx >= 0 and self._state.aggregated_json_string[idx] == "\\":
            count += 1
            idx -= 1

        # If an odd number of backslashes were found, the quote is escaped.
        return count % 2 == 1

    def parse_json(self, input_json: str | dict | bytes) -> T:
        """
        Parses and validates a complete JSON document or Python object into the target model.

        This method is for parsing known complete data, applies streaming defaults,
        and validates against both the streaming model and the original model.

        Args:
            document: The complete JSON data as a string, bytes, or dictionary.

        Returns:
            A validated instance of the target model `T`.

        Raises:
            DeltaStreamValidationError: If JSON parsing or Pydantic validation fails.
            TypeError: If the input document type is invalid.
        """

        parsed_json = None

        if isinstance(input_json, str):
            parsed_json = json.loads(input_json)
        elif isinstance(input_json, bytes):
            parsed_json = json.loads(input_json.decode())
        elif isinstance(input_json, dict):
            parsed_json = json.loads(json.dumps(input_json))
        else:
            raise TypeError("input_json must be a string, bytes or dict.")

        # Step 1: Validate against the model WITH defaults applied
        # This fills in missing fields using the defaults from mutated_schema
        stream_data = self.stream_data_model.model_validate(parsed_json)

        # Step 2: Dump the data (with defaults applied) back to a Python DICT
        # Use mode='python' for raw Python types
        stream_data_dict = stream_data.model_dump()

        # Step 3: Validate the dictionary against the ORIGINAL model
        # This ensures the final structure (even with defaults filled in)
        # conforms to the original model's rules (e.g., stricter constraints)
        final_data = self.data_model.model_validate(stream_data_dict)

        return final_data
