"""Texts the integration writes into feeds, such as "Line 4" and popup row labels.

One JSON file per language in texts/, with English as the reference. To add a
language, copy texts/en.json to texts/<code>.json, translate the values (keep
the {placeholders}), and add the code to LANGUAGES in const.py. The tests check
that every file has the same keys and placeholders as English.

These are not Home Assistant UI translations (those are in translations/):
feeds are plain data, written in the language chosen for the integration.
"""

from __future__ import annotations

import json
import re
from functools import cache
from pathlib import Path

from homeassistant.core import HomeAssistant

TEXTS_DIR = Path(__file__).parent / "texts"
FALLBACK_LANGUAGE = "en"
PLACEHOLDER = re.compile(r"\{(\w+)\}")


class Texts:
    """Looks up a text and fills in placeholders: texts("line", line="4") → "Line 4"."""

    def __init__(self, language: str, texts: dict[str, str], fallback: dict[str, str]) -> None:
        self.language = language
        self._texts = texts
        self._fallback = fallback

    def __call__(self, key: str, **values: object) -> str:
        text = self._texts.get(key) or self._fallback.get(key) or key
        return PLACEHOLDER.sub(lambda match: str(values.get(match.group(1), "")), text)


@cache
def read_texts_file(language: str) -> dict[str, str]:
    path = TEXTS_DIR / f"{language}.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def load_texts(language: str) -> Texts:
    """Reads the files; blocking, so call it from an executor (see async_load_texts)."""
    return Texts(language, read_texts_file(language), read_texts_file(FALLBACK_LANGUAGE))


async def async_load_texts(hass: HomeAssistant, language: str) -> Texts:
    return await hass.async_add_executor_job(load_texts, language)
