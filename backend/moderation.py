from __future__ import annotations

import re
from dataclasses import dataclass

OFFENSIVE_TERMS = {
    "idiot",
    "stupid",
    "moron",
    "dumb",
    "trash",
    "hate",
    "loser",
    "screw",
}

AGGRESSIVE_MARKERS = re.compile(r"(!{2,}|\b(shut up|kill|attack|worthless)\b)", re.IGNORECASE)
ALL_CAPS_PATTERN = re.compile(r"\b[A-Z]{4,}\b")


@dataclass(frozen=True)
class ModerationResult:
    display_text: str
    original_text: str
    moderated: bool


TERM_PATTERN = re.compile(r"\b(" + "|".join(re.escape(term) for term in sorted(OFFENSIVE_TERMS)) + r")\b", re.IGNORECASE)


def is_aggressive_context(message: str) -> bool:
    if not message:
        return False
    has_marker = bool(AGGRESSIVE_MARKERS.search(message))
    has_caps = bool(ALL_CAPS_PATTERN.search(message))
    has_offensive = bool(TERM_PATTERN.search(message))
    return has_offensive and (has_marker or has_caps)


def soft_moderate(text: str, aggressive_context: bool) -> ModerationResult:
    if not text or not aggressive_context:
        return ModerationResult(display_text=text, original_text=text, moderated=False)

    def mask_match(match: re.Match[str]) -> str:
        word = match.group(0)
        if len(word) <= 3:
            return "[...]"
        return "[...]"

    masked = TERM_PATTERN.sub(mask_match, text)
    moderated = masked != text
    return ModerationResult(display_text=masked, original_text=text, moderated=moderated)
