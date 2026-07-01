from __future__ import annotations

import json
import urllib.parse

from .paths import LANG_DIR

SUPPORTED_LANGUAGES = {"en": "English", "ko": "한국어"}


def load_language(code: str) -> dict[str, str]:
    if code not in SUPPORTED_LANGUAGES:
        code = "en"
    path = LANG_DIR / f"{code}.json"
    fallback = LANG_DIR / "en.json"
    data: dict[str, str] = {}
    if fallback.exists():
        data.update(json.loads(fallback.read_text(encoding="utf-8")))
    if path.exists() and path != fallback:
        data.update(json.loads(path.read_text(encoding="utf-8")))
    return data


def tr(lang: str, key: str) -> str:
    return load_language(lang).get(key, key)


def parse_cookies(header: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in header.split(";"):
        if "=" not in part:
            continue
        name, value = part.split("=", 1)
        cookies[name.strip()] = urllib.parse.unquote(value.strip())
    return cookies


def normalize_language(code: str) -> str:
    return code if code in SUPPORTED_LANGUAGES else "en"

