"""Deterministic PII detection via regex patterns."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from ..entities import EntityType


_ZERO_WIDTH = {"\u200b", "\u200c", "\u200d", "\ufeff", "\u2060"}
_DASH_CHARS = {"\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212"}
_SPACE_CHARS = {"\u00a0", "\u2007", "\u202f", "\u2009", "\u200a", "\u2002", "\u2003"}


def _normalize_for_match(text: str) -> str:
    """NFKC + strip zero-width + fold exotic dashes/spaces to ASCII.

    Preserves string length so detection offsets still index into the
    original text. Zero-width chars are replaced with a space rather than
    removed to keep positions aligned.
    """
    out_chars: list[str] = []
    for ch in unicodedata.normalize("NFKC", text):
        if ch in _ZERO_WIDTH:
            out_chars.append(" ")
        elif ch in _DASH_CHARS:
            out_chars.append("-")
        elif ch in _SPACE_CHARS:
            out_chars.append(" ")
        else:
            out_chars.append(ch)
    result = "".join(out_chars)
    # NFKC can change length (e.g. ligatures). If so, fall back to original
    # to keep offsets valid — we lose normalization but don't corrupt spans.
    if len(result) != len(text):
        return text
    return result


@dataclass
class Detection:
    """A detected PII span."""
    entity_type: str
    value: str
    start: int
    end: int
    score: float = 1.0


def _luhn_check(number: str) -> bool:
    """Validate a credit card number using the Luhn algorithm."""
    digits = [int(d) for d in number if d.isdigit()]
    if len(digits) < 13:
        return False
    odd_digits = digits[-1::-2]
    even_digits = digits[-2::-2]
    total = sum(odd_digits)
    for d in even_digits:
        total += sum(divmod(d * 2, 10))
    return total % 10 == 0


# Patterns: (entity_type, compiled_regex, validator_func_or_None)
_PATTERNS: list[tuple[str, re.Pattern, Optional[callable]]] = [
    (
        EntityType.EMAIL_ADDRESS,
        re.compile(
            r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
        ),
        None,
    ),
    (
        EntityType.PHONE_NUMBER,
        re.compile(
            r"(?<!\d)"
            r"(?:\+?1[\s\-.]?)?"
            r"(?:\(?\d{3}\)?[\s\-.]?)"
            r"\d{3}[\s\-.]?\d{4}"
            r"(?!\d)"
        ),
        None,
    ),
    (
        EntityType.CREDIT_CARD,
        re.compile(
            r"\b(?:\d[ \-]*?){13,19}\b"
        ),
        _luhn_check,
    ),
    (
        EntityType.SSN,
        re.compile(
            r"\b(?!000|666|9\d{2})\d{3}[\s\-]?(?!00)\d{2}[\s\-]?(?!0000)\d{4}\b"
        ),
        None,
    ),
    (
        EntityType.IP_ADDRESS,
        re.compile(
            r"\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b"
        ),
        None,
    ),
    (
        EntityType.IBAN,
        re.compile(
            r"\b[A-Z]{2}\d{2}[\s]?[\dA-Z]{4}[\s]?(?:[\dA-Z]{4}[\s]?){2,7}[\dA-Z]{1,4}\b"
        ),
        None,
    ),
    (
        EntityType.URL,
        re.compile(
            r"https?://[^\s<>\"']{3,}"
        ),
        None,
    ),
    (
        EntityType.AWS_KEY,
        re.compile(
            r"\b(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}\b"
        ),
        None,
    ),
    (
        EntityType.API_KEY,
        re.compile(
            r"\b(?:sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{36,}|gho_[A-Za-z0-9]{36,})\b"
        ),
        None,
    ),
]


class RegexDetector:
    """Fast, deterministic PII detector using compiled regex patterns."""

    def __init__(self, entities: Optional[set[str]] = None) -> None:
        self._entities = entities

    def detect(self, text: str) -> list[Detection]:
        """Scan text and return all detected PII spans."""
        detections: list[Detection] = []
        # Run regex over normalized text so Unicode dashes / zero-width chars
        # don't let attackers slip past the patterns. Offsets stay aligned
        # because _normalize_for_match preserves length.
        search_text = _normalize_for_match(text)

        for entity_type, pattern, validator in _PATTERNS:
            if self._entities and entity_type not in self._entities:
                continue

            for match in pattern.finditer(search_text):
                # Store the original (un-normalized) substring so the vault
                # round-trips what the user actually wrote.
                value = text[match.start():match.end()]
                if validator and not validator(value):
                    continue
                detections.append(
                    Detection(
                        entity_type=entity_type,
                        value=value,
                        start=match.start(),
                        end=match.end(),
                    )
                )

        return detections
