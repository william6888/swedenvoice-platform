"""Tester för Pydantic-validering: quantity, special_requests, status enum."""

import pytest
from pydantic import ValidationError

import main as M
import order_integrity


def test_order_item_rejects_quantity_zero():
    with pytest.raises(ValidationError):
        M.OrderItem(id=1, name="Capri", quantity=0, price=120.0)


def test_order_item_rejects_quantity_too_high():
    with pytest.raises(ValidationError):
        M.OrderItem(id=1, name="Capri", quantity=order_integrity.MAX_QUANTITY_PER_ITEM + 1, price=120.0)


def test_order_item_truncates_special_requests():
    item = M.OrderItem(id=1, name="Capri", quantity=1, price=120.0,
                       special_requests="x" * 5000)
    assert item.special_requests is not None
    assert len(item.special_requests) <= order_integrity.MAX_SPECIAL_REQUEST_LEN


def test_place_order_request_rejects_empty_items():
    with pytest.raises(ValidationError):
        M.PlaceOrderRequest(items=[])


def test_update_status_request_rejects_invalid_value():
    with pytest.raises(ValidationError):
        M.UpdateOrderStatusRequest(order_id="O1", status="annulled")


def test_update_status_request_accepts_normalized_alias():
    req = M.UpdateOrderStatusRequest(order_id="O1", status="redo")
    assert req.status == "ready"
