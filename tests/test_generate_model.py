from __future__ import annotations

from typing import Optional
from typing import Union

import pytest

from pydantic import BaseModel
from pydantic import Field

from delta_stream._errors import DeltaStreamModelBuildError
from delta_stream._generate_model import _generate_model_with_defaults


def test_generate_primitives_with_defaults():
    """
    Tests if defaults are correctly applied/prioritized for primitive types.
    """

    class PrimitivesInput(BaseModel):
        a: str = "original"
        b: int = Field(default=10)

        c: float = Field(
            default=2.2, json_schema_extra={"stream_default": 1.1}
        )  # stream overrides

        d: bool = Field(
            default=False, json_schema_extra={"stream_default": True}
        )  # stream overrides

        e: str | None = Field(
            default="keep", json_schema_extra={"stream_default": "stream"}
        )  # stream overrides
        f: str | None = "keep_direct"  # No stream_default
        g: int | None = None  # Explicit None default
        # Only stream default
        h: str = Field(json_schema_extra={"stream_default": "stream_only"})
        # Stream default makes it non-None
        i: bool | None = Field(json_schema_extra={"stream_default": True})

    # Generate the model that should have defaults applied
    generated_model = _generate_model_with_defaults(PrimitivesInput)

    # Instantiate using defaults
    instance = generated_model()

    # Assert defaults
    assert instance.a == "original"
    assert instance.b == 10
    assert instance.c == 2.2
    assert instance.d is False
    assert instance.e == "keep"
    assert instance.f == "keep_direct"
    assert instance.g is None
    assert instance.h == "stream_only"
    assert instance.i is True


def test_generate_error_for_missing_defaults():
    """
    Tests if DeltaStreamModelBuildError is raised for required primitive fields
    that cannot be automatically defaulted.
    """

    class MissingInt(BaseModel):
        a: int  # Required, no default source

    class MissingFloat(BaseModel):
        a: float = Field(...)  # Explicitly required

    class MissingBool(BaseModel):
        b: bool  # Required

    with pytest.raises(DeltaStreamModelBuildError):
        _generate_model_with_defaults(MissingInt)

    with pytest.raises(DeltaStreamModelBuildError):
        _generate_model_with_defaults(MissingFloat)

    with pytest.raises(DeltaStreamModelBuildError):
        _generate_model_with_defaults(MissingBool)


def test_generate_no_error_for_optional_primitives():
    """
    Tests that Optional primitive fields default to None if no other default is given.
    (Based on updated understanding of user's default logic for nullables).
    """

    class OptionalInput(BaseModel):
        a: int | None
        b: float | None = Field()  # Field() implies Optional default None
        c: bool | None
        d: str | None  # Should default to None, not ""

    generated_model = _generate_model_with_defaults(OptionalInput)
    instance = generated_model()

    assert instance.a is None
    assert instance.b is None
    assert instance.c is None
    assert instance.d is None


def test_generate_automatic_defaults():
    """
    Tests if automatic defaults ("" for str, [] for list) are applied correctly
    when no other default is present.
    """

    class AutoDefaultsInput(BaseModel):
        s: str  # Required string -> Should get ""
        # Required list -> Should get [] (via default_factory=list)
        l: list  # noqa: E741
        ls: list[str]  # Required list[str] -> Should get []

    generated_model = _generate_model_with_defaults(AutoDefaultsInput)
    instance = generated_model()

    assert instance.s == ""
    assert instance.l == []
    assert instance.ls == []
    assert instance.l is not instance.ls


class NestedChild(BaseModel):
    x: int = 5
    y: str = "child_orig"
    z: str


def test_generate_nested_model_factory():
    """
    Tests if a default_factory is correctly applied to required nested BaseModel fields.
    """

    class NestedParentInput(BaseModel):
        child_auto: NestedChild
        child_opt: NestedChild | None
        child_list: list[NestedChild]
        child_none: NestedChild | None = None

    generated_model = _generate_model_with_defaults(NestedParentInput)
    instance = generated_model()

    assert instance.child_auto.x == 5  # From child's stream_default
    assert instance.child_auto.y == "child_orig"  # From child's original default
    assert instance.child_auto.z == ""  # Assuming auto "" default applies recursively

    # Check optional child
    assert instance.child_opt is None

    # Check list child
    assert instance.child_list == []

    # Check explicitly None child
    assert instance.child_none is None


class NestedForOptional(BaseModel):
    x: int = Field(default=1, json_schema_extra={"stream_default": 10})
    y: str = "nested_default"


class NestedForUnionA(BaseModel):
    a: str = Field(default="A", json_schema_extra={"stream_default": "StreamA"})


class NestedForUnionB(BaseModel):
    b: int = Field(default=100, json_schema_extra={"stream_default": 200})


def test_generate_optional_syntax_defaults():
    """
    Tests default handling for fields using Optional[T] or T | None syntax,
    with corrected precedence (default/factory > stream_default).
    """

    class OptionalSyntaxModel(BaseModel):
        # Rule 6: Optional types default to None if no other default specified
        opt_int: int | None
        opt_str: Optional[str]  # noqa: UP007
        opt_list: list[int] | None
        opt_nested: NestedForOptional | None

        # Rule 2: Explicit default=None wins
        opt_explicit_none: int | None = None
        opt_explicit_none_field: Optional[float] = Field(default=None)  # noqa: UP007

        # Rule 2: Explicit default value wins
        opt_explicit_val: bool | None = True
        opt_explicit_val_field: str | None = Field(default="hello")

        # Rule 1/2: Explicit default wins over stream_default
        opt_stream_val: int | None = Field(
            # Explicit default=5 wins
            default=5,
            json_schema_extra={"stream_default": 50},
        )
        opt_stream_none: str | None = Field(
            # Explicit default="abc" wins
            default="abc",
            json_schema_extra={"stream_default": None},
        )

        # Rule 3 (now): stream_default applies if no explicit default/factory
        opt_only_stream: float | None = Field(
            json_schema_extra={"stream_default": 123.4}
        )
        opt_only_stream_none: bool | None = Field(
            json_schema_extra={"stream_default": None}
        )

    # Generate the model that should have defaults applied
    generated_model = _generate_model_with_defaults(OptionalSyntaxModel)

    # Instantiate using defaults
    instance = generated_model()

    # Assert Rule 6 (Implicit None)
    assert instance.opt_int is None, "opt_int failed"
    assert instance.opt_str is None, "opt_str failed"
    assert instance.opt_list is None, "opt_list failed"
    assert instance.opt_nested is None, "opt_nested failed"

    # Assert Rule 2 (Explicit None)
    assert instance.opt_explicit_none is None, "opt_explicit_none failed"
    assert instance.opt_explicit_none_field is None, "opt_explicit_none_field failed"

    # Assert Rule 2 (Explicit Value)
    assert instance.opt_explicit_val is True, "opt_explicit_val failed"
    assert instance.opt_explicit_val_field == "hello", "opt_explicit_val_field failed"

    # Assert Rule 1/2 (Explicit Default/Factory Wins Over Stream)
    assert instance.opt_stream_val == 5, "opt_stream_val failed (default=5 should win)"
    assert (
        instance.opt_stream_none == "abc"
    ), "opt_stream_none failed (default='abc' should win)"

    # Assert Rule 3 (stream_default applies when no explicit default/factory)
    assert instance.opt_only_stream == 123.4, "opt_only_stream failed"
    assert instance.opt_only_stream_none is None, "opt_only_stream_none failed"


# Define models inside the test or ensure they are available in the scope


class UnionErrorModel(BaseModel):
    req_int_str: int | str
    req_bool_float: Union[bool, float]  # noqa: UP007
    req_nested_a_b: NestedForUnionA | NestedForUnionB
    req_str_bytes: str | bytes


def test_generate_union_syntax_defaults_and_errors():
    """
    Tests default handling and errors for fields using Union[X, Y] or X | Y syntax
    (where None is NOT one of the options), using corrected precedence.
    """

    with pytest.raises(DeltaStreamModelBuildError):
        _generate_model_with_defaults(UnionErrorModel)

    class UnionSuccessModel(BaseModel):
        def_int_str_int: int | str = 100
        def_int_str_str: Union[int, str] = "一百"  # noqa: UP007
        stream_float_bool: float | bool = Field(
            default=1.2, json_schema_extra={"stream_default": False}
        )
        def_list_str: list[int] | str

    generated_success_model = _generate_model_with_defaults(UnionSuccessModel)
    instance = generated_success_model()

    assert instance.def_int_str_int == 100, "def_int_str_int failed"
    assert instance.def_int_str_str == "一百", "def_int_str_str failed"
    assert (
        instance.stream_float_bool == 1.2
    ), "stream_float_bool failed (default=1.2 should win)"
    assert instance.def_list_str == "", "def_list_str failed (factory should win)"
