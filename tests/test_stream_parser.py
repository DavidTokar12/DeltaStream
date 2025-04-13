from __future__ import annotations

from typing import Any

import pytest

from pydantic import BaseModel
from pydantic import Field

from delta_stream._errors import DeltaStreamValidationError
from delta_stream.stream_parser import JsonStreamParser


class Address(BaseModel):
    street: str
    city: str | None
    zip: int = Field(stream_default=12345)


class User(BaseModel):
    id: int = Field(stream_default=0)
    username: str

    aliases: list[str]
    address: Address
    roles: list[str] | None


class InventoryItem(BaseModel):
    sku: str
    name: str
    count: int = Field(default=0)
    tags: list[str]


class Warehouse(BaseModel):
    warehouse_id: str
    location: Address | None = None
    inventory: list[InventoryItem]


def chunk_string(data: str, size: int):
    for i in range(0, len(data), size):
        yield data[i : i + size]


class TestJsonStreamParserEndToEnd:

    @pytest.mark.parametrize("chunk_size", [1, 2, 3, 5, 8, 10, 20])
    def test_user_stream_no_delta(self, chunk_size):
        """
        Tests streaming User model with delta_mode=False.
        Verifies the last non-None result matches the original complete object.
        """

        original_user = User(
            id=101,
            username="dave",
            aliases=["david", "d"],
            address=Address(street="123 Main St", city="Anytown", zip=12345),
            roles=["ADMIN", "USER"],
        )

        json_input = original_user.model_dump_json()

        parser = JsonStreamParser(User, delta_mode=False)
        results = []

        for chunk in chunk_string(json_input, chunk_size):
            try:
                result = parser.parse_chunk(chunk)
                if result is not None:
                    assert isinstance(result, User)
                    results.append(result)
            except DeltaStreamValidationError as e:
                pytest.fail(
                    f"Validation error (size={chunk_size}): {e}\nInput: '{json_input}'\nChunk: '{chunk}'\nState: {parser._state}"
                )
            except Exception as e:
                pytest.fail(
                    f"Unexpected error (size={chunk_size}): {type(e).__name__}: {e}\nInput: '{json_input}'\nChunk: '{chunk}'\nState: {parser._state}"
                )

        assert (
            results
        ), f"Parser did not return any valid results for chunk size {chunk_size}"
        assert (
            results[-1] == original_user
        ), f"Final result mismatch for chunk size {chunk_size}"

    @pytest.mark.parametrize("chunk_size", [1, 2, 3, 5, 8, 10, 25])
    def test_warehouse_stream_no_delta(self, chunk_size):
        """
        Tests streaming Warehouse model (list of objects) with delta_mode=False.
        Verifies the last non-None result matches the original complete object.
        """

        original_warehouse = Warehouse(
            warehouse_id="WH-NORTH",
            location=Address(street="456 Side St", zip=54321, city=None),
            inventory=[
                InventoryItem(
                    sku="SKU001", name="Thingamajig", count=10, tags=["red", "new"]
                ),
                InventoryItem(sku="SKU002", name="Widget", count=5, tags=[]),
                InventoryItem(sku="SKU003", name="XD", count=0, tags=[]),
            ],
        )
        json_input = original_warehouse.model_dump_json()

        parser = JsonStreamParser(Warehouse, delta_mode=False)
        results = []

        for chunk in chunk_string(json_input, chunk_size):
            try:
                result = parser.parse_chunk(chunk)
                if result is not None:
                    assert isinstance(result, Warehouse)
                    results.append(result)
            except DeltaStreamValidationError as e:
                pytest.fail(
                    f"Validation error (size={chunk_size}): {e}\nInput: '{json_input}'\nChunk: '{chunk}'\nState: {parser._state}"
                )
            except Exception as e:
                pytest.fail(
                    f"Unexpected error (size={chunk_size}): {type(e).__name__}: {e}\nInput: '{json_input}'\nChunk: '{chunk}'\nState: {parser._state}"
                )

        assert (
            results
        ), f"Parser did not return any valid results for chunk size {chunk_size}"
        assert (
            results[-1] == original_warehouse
        ), f"Final result mismatch for chunk size {chunk_size}"
        assert results[-1].inventory[1].tags == []
        assert results[-1].location.city is None  # Verify None default

    def apply_delta(self, base: dict | None, delta: dict) -> dict:
        """
        Applies a delta dictionary to a base dictionary to reconstruct the full state.

        Args:
            base: The previous state dictionary, or None if starting from scratch.
            delta: The delta dictionary representing changes or new additions.

        Returns:
            A new dictionary representing the reconstructed full state.
        """
        base_dict = base.copy() if isinstance(base, dict) else {}
        result = {}

        for key, delta_value in delta.items():
            base_value = base_dict.get(key)

            result[key] = self._apply_delta_recursive(base_value, delta_value)

        # Preserve keys from base that were not affected by delta
        for key, value in base_dict.items():
            if key not in result:
                result[key] = value

        return result

    def _apply_delta_recursive(self, base_value: Any, delta_value: Any) -> Any:
        """
        Recursive helper to apply delta values to base values.
        """
        # Delta is None, result is None
        if delta_value is None:
            return None

        # If delta is a string and base is a string -> append
        if isinstance(delta_value, str) and isinstance(base_value, str):
            return base_value + delta_value

        # If delta is a string and base is not a string or None -> replace
        if isinstance(delta_value, str):
            return delta_value

        # If delta is a list, apply recursively element-wise
        if isinstance(delta_value, list):
            base_list = base_value if isinstance(base_value, list) else []
            result_list = []
            for i, delta_item in enumerate(delta_value):
                base_item = base_list[i] if i < len(base_list) else None
                result_list.append(self._apply_delta_recursive(base_item, delta_item))
            return result_list

        if isinstance(delta_value, dict):
            base_dict = base_value if isinstance(base_value, dict) else {}
            return self.apply_delta(base_dict, delta_value)

        return delta_value

    @pytest.mark.parametrize("chunk_size", [1, 2, 3, 5, 8, 10, 20])
    def test_user_stream_delta_mode(self, chunk_size):
        """
        Tests streaming User model with delta_mode=True.
        Verifies that applying the sequence of deltas reconstructs the original object.
        """
        original_user = User(
            id=101,
            username="dave",
            aliases=["david", "d"],
            address=Address(street="123 Main St", city="Anytown", zip=12345),
            roles=["ADMIN", "2USER"],
        )
        json_input = original_user.model_dump_json()

        parser = JsonStreamParser(User, delta_mode=True)

        reconstructed_dict: dict | None = None
        processed_len = 0
        result_delta_objects = []
        for chunk in chunk_string(json_input, chunk_size):
            processed_len += len(chunk)
            try:
                # This is a User instance representing delta
                result_delta_obj = parser.parse_chunk(chunk)

                result_delta_objects.append(result_delta_obj)

                if result_delta_obj is not None:
                    # Apply the delta to the reconstructed dictionary

                    assert isinstance(result_delta_obj, User)
                    delta_dict = result_delta_obj.model_dump()
                    reconstructed_dict = self.apply_delta(
                        reconstructed_dict, delta_dict
                    )

            except DeltaStreamValidationError as e:
                pytest.fail(
                    f"Validation error (size={chunk_size}) at ~char {processed_len}: {e}\nInput: '{json_input}'\nChunk: '{chunk}'\nState: {parser._state}"
                )
            except Exception as e:
                pytest.fail(
                    f"Unexpected error (size={chunk_size}) at ~char {processed_len}: {type(e).__name__}: {e}\nInput: '{json_input}'\nChunk: '{chunk}'\nState: {parser._state}"
                )

        assert (
            reconstructed_dict is not None
        ), f"Parser did not produce any usable delta results for chunk size {chunk_size}"

        # Validate the fully reconstructed dictionary by parsing it with the original model
        # This ensures the sequence of deltas correctly rebuilt the object
        final_reconstructed_object = parser.data_model.model_validate(
            reconstructed_dict
        )

        assert (
            final_reconstructed_object == original_user
        ), f"Reconstructed object mismatch for chunk size {chunk_size}"

    @pytest.mark.parametrize("chunk_size", [1, 2, 3, 5, 8, 10, 25])
    def test_warehouse_stream_delta_mode(self, chunk_size):
        """
        Tests streaming Warehouse model with delta_mode=True.
        Verifies that applying the sequence of deltas reconstructs the original object.
        """
        original_warehouse = Warehouse(
            warehouse_id="WH-NORTH",
            location=Address(street="456 Side St", zip=54321, city=None),
            inventory=[
                InventoryItem(
                    sku="SKU001", name="Thingamajig", count=10, tags=["red", "new"]
                ),
                InventoryItem(sku="SKU002", name="Widget", count=5, tags=[]),
                InventoryItem(sku="SKU003", name="XD", count=0, tags=[]),
            ],
        )
        json_input = original_warehouse.model_dump_json()

        parser = JsonStreamParser(Warehouse, delta_mode=True)

        reconstructed_dict: dict | None = None
        processed_len = 0
        for chunk in chunk_string(json_input, chunk_size):
            processed_len += len(chunk)
            try:
                result_delta_obj = parser.parse_chunk(chunk)
                if result_delta_obj is not None:
                    assert isinstance(result_delta_obj, Warehouse)
                    delta_dict = result_delta_obj.model_dump()
                    reconstructed_dict = self.apply_delta(
                        reconstructed_dict, delta_dict
                    )
                    # print(f"DEBUG @ {processed_len}: Delta: {delta_dict}") # Debug
                    # print(f"DEBUG @ {processed_len}: Reconstructed: {reconstructed_dict}") # Debug
            except DeltaStreamValidationError as e:
                pytest.fail(
                    f"Validation error (size={chunk_size}) at ~char {processed_len}: {e}\nInput: '{json_input}'\nChunk: '{chunk}'\nState: {parser._state}"
                )
            except Exception as e:
                pytest.fail(
                    f"Unexpected error (size={chunk_size}) at ~char {processed_len}: {type(e).__name__}: {e}\nInput: '{json_input}'\nChunk: '{chunk}'\nState: {parser._state}"
                )

        assert (
            reconstructed_dict is not None
        ), f"Parser did not produce any usable delta results for chunk size {chunk_size}"

        final_reconstructed_object = parser.data_model.model_validate(
            reconstructed_dict
        )

        assert (
            final_reconstructed_object == original_warehouse
        ), f"Reconstructed object mismatch for chunk size {chunk_size}"
