"""Explicit language preferences, separate from a person's language proficiency."""

import re


def language_tag(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", value.strip()):
        raise ValueError("Use a language tag such as ru, en or pt-BR")
    return value.strip().lower()


def search_languages(value):
    if not isinstance(value, list):
        raise ValueError("search_languages must be a list of language tags, for example ['ru', 'en']")
    return list(dict.fromkeys(language_tag(item) for item in value))


def language_coverage(scope, sources):
    requested = search_languages(scope.get("search_languages", []))
    collected = list(
        dict.fromkeys(
            source["language"]
            for source in sources
            if isinstance(source, dict) and source.get("status") == "collected" and source.get("language")
        )
    )
    return {
        "requested": requested,
        "collected": collected,
        "missing": [language for language in requested if language not in collected],
    }
