import json
from pathlib import Path

from scripts.onboard_pizzeria import build_menu_names, build_system_prompt


def test_menu_names_contain_no_llm_controlled_ids():
    menu = {
        "pizzas": [
            {"id": 1, "name": "Testpizza"},
            {"id": 2, "name": "Andra pizzan"},
        ]
    }
    text = build_menu_names(menu)
    assert text == "Pizzor: Testpizza, Andra pizzan."
    assert "=1" not in text
    assert "=2" not in text


def test_tenant_prompt_replaces_brand_and_menu_section():
    menu = {"pizzas": [{"id": 501, "name": "Roma Special"}]}
    prompt = build_system_prompt("Pizzeria Roma", menu)
    assert "Du svarar i telefonen på Pizzeria Roma" in prompt
    assert "Pizzor: Roma Special." in prompt
    assert "Capricciosa, Vesuvio" not in prompt
    assert "# Exempel" in prompt
    assert "# Flöde" in prompt
    assert "{{RESTAURANT_NAME}}" not in prompt
    assert "artikel-id" in prompt


def test_current_menu_can_generate_prompt():
    menu_path = Path(__file__).resolve().parent.parent / "menu.json"
    menu = json.loads(menu_path.read_text(encoding="utf-8"))
    prompt = build_system_prompt("Gislegrillen", menu)
    assert "Kebabpizza" in prompt
    assert "Kebabtallrik med mos" in prompt
    assert "Polisen=52" not in prompt
    assert "Dryck: 33cl, 50cl, 2 liter, 1.5 liter." in prompt


def test_gislegrillen_prompt_file_matches_composer():
    menu_path = Path(__file__).resolve().parent.parent / "menu.json"
    prompt_path = Path(__file__).resolve().parent.parent / "system_prompt.md"
    menu = json.loads(menu_path.read_text(encoding="utf-8"))
    assert build_system_prompt("Gislegrillen", menu) == prompt_path.read_text(
        encoding="utf-8"
    )


def test_order_tool_messages_follow_vapi_reliability_guidance():
    from scripts.onboard_pizzeria import DRAFT_ORDER_MESSAGES, PLACE_ORDER_MESSAGES

    draft_complete = [m for m in DRAFT_ORDER_MESSAGES if m["type"] == "request-complete"]
    place_complete = [m for m in PLACE_ORDER_MESSAGES if m["type"] == "request-complete"]
    assert len(draft_complete) == 1
    assert draft_complete[0]["role"] == "system"
    assert len(place_complete) == 1
    assert place_complete[0].get("endCallAfterSpokenEnabled") is True
    for messages in (DRAFT_ORDER_MESSAGES, PLACE_ORDER_MESSAGES):
        start = next(m for m in messages if m["type"] == "request-start")
        delayed = next(m for m in messages if m["type"] == "request-response-delayed")
        assert start["content"] == "okej,"
        assert delayed["content"] == "det tar en sekund till,"
        assert delayed["timingMilliseconds"] == 5000
