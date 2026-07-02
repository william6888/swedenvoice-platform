"""SMS-formatering: special_requests måste komma med oavsett om det är per rad eller toppnivå."""

import main as M


def _order(items, special_requests=""):
    return M.Order(
        order_id="ORD-TEST",
        items=items,
        special_requests=special_requests,
        total_price=100.0,
        status="pending",
        timestamp="2026-05-17 14:00:00",
    )


def test_top_level_special_requests_in_sms():
    """AI skickar special_requests som toppnivå-sträng – ska synas i SMS."""
    order = _order(
        [M.OrderItem(id=1, name="Vesuvio", quantity=1, price=120.0)],
        special_requests="Vesuvio: extra sas",
    )
    text = M._format_order_sms(order)
    assert "Vesuvio: extra sas" in text
    assert "1x Vesuvio" in text


def test_per_item_special_requests_in_sms():
    """AI skickar special_requests per rad – ska synas i SMS."""
    item = M.OrderItem(id=1, name="Vesuvio", quantity=1, price=120.0, special_requests="utan lok")
    order = _order([item])
    text = M._format_order_sms(order)
    assert "utan lok" in text
    assert "Vesuvio" in text


def test_both_levels_no_duplicate():
    """Om samma text finns både per rad och toppnivå – visa bara per rad, inte dubbelt."""
    item = M.OrderItem(id=1, name="Vesuvio", quantity=1, price=120.0, special_requests="extra sas")
    order = _order([item], special_requests="extra sas")
    text = M._format_order_sms(order)
    assert text.count("extra sas") == 1


def test_no_special_requests_clean_sms():
    """Inga special requests – inget extra brus i SMS."""
    order = _order([M.OrderItem(id=1, name="Margherita", quantity=1, price=100.0)])
    text = M._format_order_sms(order)
    assert "Önskemål" not in text
    assert "(" not in text
    assert "1x Margherita" in text


def test_multiple_items_with_mixed_specials():
    """Två rätter, en med per-rad request, en utan, plus toppnivå."""
    items = [
        M.OrderItem(id=1, name="Vesuvio", quantity=1, price=120.0, special_requests="extra ost"),
        M.OrderItem(id=2, name="Hawaii", quantity=2, price=130.0),
    ]
    order = _order(items, special_requests="Hawaii: utan ananas")
    text = M._format_order_sms(order)
    assert "extra ost" in text
    assert "Hawaii: utan ananas" in text
    assert "2x Hawaii" in text


def test_default_branding_is_gislegrillen():
    """Utan branding: default = Gislegrillen + standardnummer (bakåtkompatibelt)."""
    order = _order([M.OrderItem(id=1, name="Margherita", quantity=1, price=100.0)])
    text = M._format_order_sms(order)
    assert "från Gislegrillen." in text
    assert "+46760445700" in text


def test_per_tenant_branding_in_sms():
    """Med branding för annan pizzeria: rätt namn och kontaktnummer, inte Gislegrillen."""
    order = _order([M.OrderItem(id=1, name="Margherita", quantity=1, price=100.0)])
    text = M._format_order_sms(order, {"name": "Pizzeria Roma", "contact_phone": "+46701112233"})
    assert "från Pizzeria Roma." in text
    assert "+46701112233" in text
    assert "Gislegrillen" not in text
    assert "+46760445700" not in text
