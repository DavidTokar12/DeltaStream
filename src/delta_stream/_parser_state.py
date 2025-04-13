from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ParserState:
    parenthesis_stack: list[str]

    is_inside_string: bool = False
    expecting_key: bool = False
    inside_key_string: bool = False
    parsing_literal_or_number: bool = False
    just_saw_colon: bool = False
    recently_finished_key: bool = False
    last_char: str = ""
    aggregated_json_string: str = ""
