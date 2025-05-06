from __future__ import annotations

from typing import Any

import pytest

from pydantic import BaseModel

from delta_stream._compute_deltas import compute_delta


class NestedModelForD(BaseModel):

    a: int | None = None
    s: str | None = None
    l: list[Any] | None = None  # noqa: E741
    b: Any | None = None


class FlexibleModel(BaseModel):

    a: int | None = None
    b: Any | None = None
    c: Any | None = None
    s: str | None = None
    n: int | None = None
    k: Any | None = None
    k2: Any | None = None
    l: list[Any] | None = None  # noqa: E741
    d: NestedModelForD | None = None


# --- Test Cases with Pydantic Models Specified ---
# Each tuple is: (ID, prev_data_dict_or_None, curr_data_dict, ModelToUse, expected_delta_dict)
delta_test_cases_with_models = [
    # ID                     Prev_Data             Curr_Data                 Model_Class     Expected_Delta
    (
        "Dict_New_Simple",
        None,
        {"a": 1, "b": "xyz"},
        FlexibleModel,
        {"a": 1, "b": "xyz"},
    ),
    ("Dict_New_Empty", {}, {"a": 1, "b": "xyz"}, FlexibleModel, {"a": 1, "b": "xyz"}),
    ("Dict_Num_Same", {"a": 1}, {"a": 1}, FlexibleModel, {"a": 1}),
    ("Dict_Num_Change", {"a": 1}, {"a": 2}, FlexibleModel, {"a": 2}),
    ("Dict_Bool_Same", {"b": True}, {"b": True}, FlexibleModel, {"b": True}),
    ("Dict_Bool_Change", {"b": True}, {"b": False}, FlexibleModel, {"b": False}),
    ("Dict_None_Same", {"c": None}, {"c": None}, FlexibleModel, {"c": None}),
    ("Dict_None_Set", {"c": 1}, {"c": None}, FlexibleModel, {"c": None}),
    ("Dict_Str_Same", {"s": "abc"}, {"s": "abc"}, FlexibleModel, {"s": ""}),
    ("Dict_Str_Append", {"s": "abc"}, {"s": "abcdef"}, FlexibleModel, {"s": "def"}),
    ("Dict_Str_Diff", {"s": "xyz"}, {"s": "abc"}, FlexibleModel, {"s": "abc"}),
    ("Dict_Str_New", {}, {"s": "abc"}, FlexibleModel, {"s": "abc"}),
    ("Dict_Str_FromNone", {"s": None}, {"s": "abc"}, FlexibleModel, {"s": "abc"}),
    # This test's expectation relies on iterating over curr's explicitly set fields.
    ("Dict_KeyRemoved", {"n": 1, "k": "v"}, {"k": "v"}, FlexibleModel, {"k": ""}),
    (
        "Dict_KeyAddedStr",
        {"k": "v"},
        {"k": "v", "k2": "v2"},
        FlexibleModel,
        {"k": "", "k2": "v2"},
    ),
    (
        "Dict_KeyAddedNum",
        {"k": "v"},
        {"k": "v", "k2": 123},
        FlexibleModel,
        {"k": "", "k2": 123},
    ),
    ("Dict_List_New", {}, {"l": ["a"]}, FlexibleModel, {"l": ["a"]}),
    (
        "Dict_List_AddElemStr",
        {"l": ["a"]},
        {"l": ["a", "b"]},
        FlexibleModel,
        {"l": ["", "b"]},
    ),
    ("Dict_List_AddElemNum", {"l": [1]}, {"l": [1, 2]}, FlexibleModel, {"l": [1, 2]}),
    (
        "Dict_List_StrAppend",
        {"l": ["abc"]},
        {"l": ["abcdef"]},
        FlexibleModel,
        {"l": ["def"]},
    ),
    (
        "Dict_List_MixedChange",
        {"l": ["abc", 1]},
        {"l": ["abcdef", 2]},
        FlexibleModel,
        {"l": ["def", 2]},
    ),
    ("Dict_Nest_New", {}, {"d": {"a": 1}}, FlexibleModel, {"d": {"a": 1}}),
    (
        "Dict_Nest_ChangeNum",
        {"d": {"a": 1}},
        {"d": {"a": 2}},
        FlexibleModel,
        {"d": {"a": 2}},
    ),
    (
        "Dict_Nest_ChangeStr",
        {"d": {"s": "a"}},
        {"d": {"s": "ab"}},
        FlexibleModel,
        {"d": {"s": "b"}},
    ),
    (
        "Dict_Nest_AddKey",
        {"d": {"a": 1}},
        {"d": {"a": 1, "b": "x"}},
        FlexibleModel,
        {"d": {"a": 1, "b": "x"}},
    ),
    (
        "Dict_Nest_ListChange",
        {"d": {"l": ["a"]}},
        {"d": {"l": ["a", "b"]}},
        FlexibleModel,
        {"d": {"l": ["", "b"]}},
    ),
    ("Dict_TypeChange", {"k": 1}, {"k": "abc"}, FlexibleModel, {"k": "abc"}),
    ("Dict_TypeChangeList", {"k": "abc"}, {"k": [1]}, FlexibleModel, {"k": [1]}),
]
# fmt: on

delta_test_ids = [case[0] for case in delta_test_cases_with_models]


@pytest.mark.parametrize(
    "test_id, prev_data, curr_data, model_cls, expected_delta",
    [
        (c[0], c[1], c[2], c[3], c[4]) for c in delta_test_cases_with_models
    ],  # Ensure correct indexing
    ids=delta_test_ids,
)
def test_compute_delta_with_models(
    test_id: str,
    prev_data: dict | None,
    curr_data: dict,
    model_cls: type[BaseModel],
    expected_delta: dict,
):
    """
    Tests the compute_delta function using Pydantic models instantiated from dictionary data.
    """
    prev_model: BaseModel | None = None
    if prev_data is not None:
        # If prev_data is an empty dict {}, this creates a model with default values.
        prev_model = model_cls(**prev_data)

    # curr_data is never None in the test cases
    curr_model: BaseModel = model_cls(**curr_data)

    actual_delta = compute_delta(prev_model, curr_model)
    assert actual_delta == expected_delta
