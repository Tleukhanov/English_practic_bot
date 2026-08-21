from core.characters import get_character, list_characters, character_prompt


def test_list_characters_has_six():
    chars = list_characters()
    assert len(chars) == 6
    ids = [c.id for c in chars]
    assert "default" in ids
    assert "chill" in ids
    assert "toxic" in ids
    assert "strict" in ids
    assert "british" in ids
    assert "toxic_friend" in ids


def test_get_character_default():
    c = get_character("default")
    assert c.emoji == "📚"
    assert c.prompt_suffix == ""


def test_get_character_unknown_falls_back():
    c = get_character("nonexistent")
    assert c.id == "default"


def test_character_prompt_returns_suffix():
    assert character_prompt("default") == ""
    assert "chill" in character_prompt("chill").lower() or "friendly" in character_prompt("chill").lower()
    assert "British" in character_prompt("british")
    assert "sarcastic" in character_prompt("toxic").lower() or "roast" in character_prompt("toxic").lower()


def test_characters_have_unique_ids():
    chars = list_characters()
    ids = [c.id for c in chars]
    assert len(ids) == len(set(ids))
