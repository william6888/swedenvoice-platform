"""Guardrails for the live voice prompt: it must sound like a cashier, not a form."""

from pathlib import Path


PROMPT = (Path(__file__).resolve().parent.parent / "system_prompt.md").read_text(
    encoding="utf-8"
)


def test_prompt_forbids_wait_filler_and_form_words():
    lowered = PROMPT.casefold()
    assert "serveringsform" not in lowered
    assert "vänta en sekund" not in lowered
    assert "det tar bara" in lowered
    assert "ögonblick" in lowered
    assert "säg aldrig" in lowered
    assert "vänta" in lowered


def test_prompt_requires_human_order_taking():
    assert "Något mer?" in PROMPT
    assert "Äta här eller ta med?" in PROMPT
    assert "Stämmer det?" in PROMPT
    assert "Hallå" in PROMPT
    assert "Tack, välkommen." in PROMPT
    assert "transfer_to_staff" in PROMPT
    assert "bara om kunden ber att prata med personal" in PROMPT


def test_prompt_keeps_kebab_family_and_readback_contract():
    assert "Kebabfamiljepizza" in PROMPT
    assert "readback" in PROMPT
    assert "draft_order" in PROMPT
    assert "place_order" in PROMPT
    assert "Gislegrillen" in PROMPT
