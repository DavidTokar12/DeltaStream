from __future__ import annotations

import pytest

from delta_stream._compute_deltas import compute_delta


# fmt: off
delta_test_cases = [
    # ID                      Prev                         Curr                             Expected Delta
    ("Dict_New_Simple",       None,                        {"a":1, "b":"xyz"},               {"a":1, "b":"xyz"}),
    ("Dict_New_Empty",        {},                          {"a":1, "b":"xyz"},               {"a":1, "b":"xyz"}),
    ("Dict_Num_Same",         {"a":1},                     {"a":1},                         {"a":1}), # Number always included
    ("Dict_Num_Change",       {"a":1},                     {"a":2},                         {"a":2}), # Number always included
    ("Dict_Bool_Same",        {"b":True},                  {"b":True},                      {"b":True}), # Boolean always included
    ("Dict_Bool_Change",      {"b":True},                  {"b":False},                     {"b":False}), # Boolean always included
    ("Dict_None_Same",        {"c":None},                  {"c":None},                      {"c":None}), # None always included
    ("Dict_None_Set",         {"c":1},                     {"c":None},                      {"c":None}), # None always included
    ("Dict_Str_Same",         {"s":"abc"},                 {"s":"abc"},                     {"s":""}), # String delta is empty
    ("Dict_Str_Append",       {"s":"abc"},                 {"s":"abcdef"},                  {"s":"def"}), # String delta is suffix
    ("Dict_Str_Diff",         {"s":"xyz"},                 {"s":"abc"},                     {"s":"abc"}), # String delta is full new string
    ("Dict_Str_New",          {},                          {"s":"abc"},                     {"s":"abc"}), # New key with string
    ("Dict_Str_FromNone",     {"s":None},                  {"s":"abc"},                     {"s":"abc"}), # Prev None treated as ""
    ("Dict_KeyRemoved",       {"n":1, "k":"v"},            {"k":"v"},                       {"k":""}), # Key 'n' removed, 'k' delta is ""
    ("Dict_KeyAddedStr",      {"k":"v"},                   {"k":"v", "k2":"v2"},            {"k":"", "k2":"v2"}), # Added key 'k2'
    ("Dict_KeyAddedNum",      {"k":"v"},                   {"k":"v", "k2":123},             {"k":"", "k2":123}), # Added key 'k2' with num
    ("Dict_List_New",         {},                          {"l":["a"]},                     {"l":["a"]}), # New key with list
    ("Dict_List_AddElemStr",  {"l":["a"]},                 {"l":["a", "b"]},                {"l":["", "b"]}), # List append string
    ("Dict_List_AddElemNum",  {"l":[1]},                   {"l":[1, 2]},                    {"l":[1, 2]}), # List append num
    ("Dict_List_StrAppend",   {"l":["abc"]},               {"l":["abcdef"]},                {"l":["def"]}), # List string append
    ("Dict_List_MixedChange", {"l":["abc", 1]},            {"l":["abcdef", 2]},             {"l":["def", 2]}), # Mixed list changes
    ("Dict_Nest_New",         {},                          {"d":{"a":1}},                   {"d":{"a":1}}), # New nested dict
    ("Dict_Nest_ChangeNum",   {"d":{"a":1}},               {"d":{"a":2}},                   {"d":{"a":2}}), # Nested dict num change
    ("Dict_Nest_ChangeStr",   {"d":{"s":"a"}},             {"d":{"s":"ab"}},                {"d":{"s":"b"}}), # Nested dict str append
    ("Dict_Nest_AddKey",      {"d":{"a":1}},               {"d":{"a":1, "b":"x"}},          {"d":{"a":1, "b":"x"}}), # Nested dict add key
    ("Dict_Nest_ListChange",  {"d":{"l":["a"]}},           {"d":{"l":["a","b"]}},           {"d":{"l":["", "b"]}}), # Nested list change
    ("Dict_TypeChange",       {"k": 1},                    {"k": "abc"},                    {"k": "abc"}), # Value type changes str->int
    ("Dict_TypeChangeList",   {"k": "abc"},                {"k": [1]},                      {"k": [1]}), # Value type changes str->list
]
# fmt: on

delta_test_ids = [case[0] for case in delta_test_cases]


@pytest.mark.parametrize(
    "test_id, prev_val, curr_val, expected_delta",
    [(c[0], c[1], c[2], c[3]) for c in delta_test_cases],
    ids=delta_test_ids,
)
def test_compute_delta_dict_focused(test_id, prev_val, curr_val, expected_delta):
    """
    Tests the compute_delta function assuming dictionary inputs, focusing
    on the specified delta logic for strings, lists, dicts, and primitives.
    """
    actual_delta = compute_delta(prev_val, curr_val)
    assert actual_delta == expected_delta
