from collections.abc import Callable

import pytest


@pytest.mark.parametrize(
    ("subtotal_cents", "expected_fee"),
    [pytest.param(4_999, 500, id="standard"), pytest.param(5_000, 0, id="free")],
)
def test_shipping_fee(
    quote: Callable[[int], int], subtotal_cents: int, expected_fee: int
) -> None:
    assert quote(subtotal_cents) == expected_fee
