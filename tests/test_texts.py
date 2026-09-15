"""Feed texts and UI translations."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from custom_components.digitransit_live.const import LANGUAGES
from custom_components.digitransit_live.texts import TEXTS_DIR, load_texts

TRANSLATIONS_DIR = Path(TEXTS_DIR).parent / "translations"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def placeholders(text: str) -> list[str]:
    return sorted(re.findall(r"\{(\w+)\}", text))


def flatten(tree: dict, prefix: str = "") -> dict[str, str]:
    result = {}
    for key, value in tree.items():
        if isinstance(value, dict):
            result |= flatten(value, f"{prefix}{key}.")
        else:
            result[f"{prefix}{key}"] = value
    return result


@pytest.mark.parametrize("language", LANGUAGES)
def test_feed_texts_match_english(language: str) -> None:
    english = read(TEXTS_DIR / "en.json")
    texts = read(TEXTS_DIR / f"{language}.json")
    assert texts.keys() == english.keys()
    for key, text in english.items():
        assert placeholders(texts[key]) == placeholders(text), key


@pytest.mark.parametrize("language", LANGUAGES)
def test_ui_translations_match_english(language: str) -> None:
    english = flatten(read(TRANSLATIONS_DIR / "en.json"))
    translation = flatten(read(TRANSLATIONS_DIR / f"{language}.json"))
    assert translation.keys() == english.keys()


def test_texts_fill_placeholders_and_fall_back_to_english() -> None:
    assert load_texts("fi")("line", line="4") == "Linja 4"
    assert load_texts("de")("line", line="4") == "Line 4"
