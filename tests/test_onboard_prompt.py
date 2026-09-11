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
    assert "den som svarar i telefonen på Pizzeria Roma" in prompt
    assert "Pizzor: Roma Special." in prompt
    assert "Capricciosa, Vesuvio" not in prompt
    assert "# Exempel" in prompt
    assert "artikel-id" in prompt


def test_current_menu_can_generate_prompt():
    menu_path = Path(__file__).resolve().parent.parent / "menu.json"
    menu = json.loads(menu_path.read_text(encoding="utf-8"))
    prompt = build_system_prompt("Gislegrillen", menu)
    assert "Kebabpizza" in prompt
    assert "Kebabtallrik med mos" in prompt
    assert "Polisen=52" not in prompt
