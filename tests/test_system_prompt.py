"""Guardrails for the live voice prompt: natural Swedish cashier, not a phrase list."""

from pathlib import Path


PROMPT = (Path(__file__).resolve().parent.parent / "system_prompt.md").read_text(
    encoding="utf-8"
)


def test_prompt_forbids_wait_filler_and_form_words():
    lowered = PROMPT.casefold()
    assert "serveringsform" not in lowered
    assert "vänta en sekund" not in lowered
    assert "då läser jag upp" not in lowered
    assert "då slår jag in den" not in lowered
    assert "beställningen är lagd" not in lowered
    assert "varsågod" in lowered
    assert "säg inte varsågod" in lowered


def test_prompt_follows_reusable_restaurant_flow():
    assert "# Flöde" in PROMPT
    assert "Gissa aldrig" in PROMPT
    assert "En fråga i taget" in PROMPT
    assert "gemensamma för alla restauranger" in PROMPT
    assert "# Menynamn" in PROMPT
    assert "Säg inget extra medan" in PROMPT
    assert "Inte lova att något är sparat" in PROMPT


def test_prompt_requires_human_order_taking():
    assert "vill du ha något mer?" in PROMPT
    assert "Fråga aldrig om" in PROMPT or "Fråga aldrig" in PROMPT
    assert "ta_med" in PROMPT
    assert "Hallå" in PROMPT
    assert "transfer_to_staff" in PROMPT
    assert "personal" in PROMPT
    assert "namnfrågor" in PROMPT
    assert "Ciao-Ciao" in PROMPT
    assert "kommatecken" in PROMPT
    assert "okej, en vesuvio, vill du ha något mer?" in PROMPT
    assert "är det bra så?" in PROMPT
    assert "Inte kaxig" in PROMPT
    assert 'Du: "vad vill du ha mer?"' not in PROMPT
    assert 'Du: "vad tar du mer?"' not in PROMPT
    assert 'Du: "blir det bra så?"' not in PROMPT
    assert "önskemål/allergier" in PROMPT.casefold()


def test_prompt_keeps_kebab_family_and_readback_contract():
    assert "Kebabfamiljepizza" in PROMPT
    assert "readback" in PROMPT
    assert "draft_order" in PROMPT
    assert "place_order" in PROMPT
    assert "Gislegrillen" in PROMPT
    assert "Dryck" in PROMPT
    assert "Säg aldrig att dryck tas på plats" in PROMPT
    assert "1.5 liter" in PROMPT
    assert "en och en halv liter" in PROMPT
    assert "Säg inte maträtt" in PROMPT
    assert "Draftar inte" in PROMPT
    assert "tvåhundra gram" in PROMPT
    assert "då ändrar jag till" in PROMPT
    assert "sås till båda eller bara en?" in PROMPT
    assert "Anropa inte draft_order förrän" in PROMPT
    assert "Aldrig cl" in PROMPT
    assert "Avbryts uppläsningen" in PROMPT
    assert "nekade" in PROMPT or "Inte koppla" in PROMPT
