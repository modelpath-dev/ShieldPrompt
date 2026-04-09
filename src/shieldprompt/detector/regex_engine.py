"""Deterministic PII detection via regex patterns."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from ..entities import EntityType


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

        for entity_type, pattern, validator in _PATTERNS:
            if self._entities and entity_type not in self._entities:
                continue

            for match in pattern.finditer(text):
                value = match.group()
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
