"""PII detection via Microsoft Presidio + spaCy.

Preferred NER backend. Presidio's AnalyzerEngine combines spaCy NER with
Presidio's built-in recognizers and context-aware scoring — handles PERSON,
LOCATION, DATE, ORG, etc. far more reliably than a raw transformer.

Default model is `en_core_web_sm` (~12 MB). spaCy models aren't on PyPI, so
we auto-download on first use if the model isn't already installed — this
keeps `pip install shieldprompt` self-contained.
"""

from __future__ import annotations

import logging
from typing import Optional

from .regex_engine import Detection
from ..entities import EntityType

logger = logging.getLogger("shieldprompt")


# Presidio entity name -> our EntityType
# spaCy's small model over-flags short capitalized common nouns as
# ORGANIZATION. Drop spans whose (case-folded) text hits this list so the
# vault stays clean and output isn't cluttered with junk tokens. Add to this
# list rather than lowering the threshold, which would hurt real ORG recall.
_ORG_DENYLIST: frozenset[str] = frozenset({
    "ssn", "ip", "id", "card", "cc", "email", "phone", "mobile", "fax",
    "teammate", "teammates", "team", "staff", "manager", "admin", "user",
    "client", "customer", "vendor", "employee", "contractor",
    "dr", "mr", "mrs", "ms", "prof", "sir", "madam",
    "note", "notes", "memo", "re", "fyi", "cc", "bcc", "tba", "tbd",
    "amex", "visa", "mastercard", "discover",
    "iban", "swift", "bic", "pan", "gst",
    "aws", "api", "url", "uri", "http", "https", "tls", "ssl", "vpn",
    "ceo", "cto", "cfo", "coo", "vp", "hr", "it", "qa", "pm", "po",
})


_LABEL_MAP: dict[str, str] = {
    "PERSON": EntityType.PERSON,
    "LOCATION": EntityType.LOCATION,
    "NRP": EntityType.PERSON,  # nationality / religious / political — treat conservatively
    "ORGANIZATION": EntityType.ORGANIZATION,
    "DATE_TIME": EntityType.DATE,
    "US_SSN": EntityType.SSN,
    "CREDIT_CARD": EntityType.CREDIT_CARD,
    "EMAIL_ADDRESS": EntityType.EMAIL_ADDRESS,
    "PHONE_NUMBER": EntityType.PHONE_NUMBER,
    "IP_ADDRESS": EntityType.IP_ADDRESS,
    "IBAN_CODE": EntityType.IBAN,
    "URL": EntityType.URL,
}


class PresidioDetector:
    """Presidio-backed detector. Loads spaCy + analyzer lazily on first use."""

    def __init__(
        self,
        spacy_model: str = "en_core_web_sm",
        score_threshold: float = 0.35,
        entities: Optional[set[str]] = None,
    ) -> None:
        self._spacy_model = spacy_model
        self._score_threshold = score_threshold
        self._entities = entities
        self._analyzer = None

    def _ensure_spacy_model(self) -> None:
        """Make sure the spaCy model is installed; download it if not.

        spaCy models aren't on PyPI, so this is how we keep installation a
        single `pip install` for the end user.
        """
        import spacy

        try:
            spacy.load(self._spacy_model)
            return
        except OSError:
            pass

        logger.info("spaCy model %r not found — downloading…", self._spacy_model)
        from spacy.cli.download import download as spacy_download

        spacy_download(self._spacy_model)

    def _load(self) -> None:
        if self._analyzer is not None:
            return
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import NlpEngineProvider
        except ImportError:
            raise ImportError(
                "presidio-analyzer is required but not installed. "
                "Run: pip install presidio-analyzer"
            )

        self._ensure_spacy_model()

        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": self._spacy_model}],
            }
        )
        self._analyzer = AnalyzerEngine(
            nlp_engine=provider.create_engine(),
            default_score_threshold=self._score_threshold,
        )
        logger.info("Presidio analyzer loaded (spacy=%s)", self._spacy_model)

    def detect(self, text: str) -> list[Detection]:
        self._load()
        assert self._analyzer is not None

        # Let Presidio scan for all entities it supports; filter afterwards.
        results = self._analyzer.analyze(text=text, language="en")
        out: list[Detection] = []
        for r in results:
            mapped = _LABEL_MAP.get(r.entity_type)
            if mapped is None:
                continue
            if self._entities and mapped not in self._entities:
                continue
            value = text[r.start:r.end]
            if len(value.strip()) < 2:
                continue
            if mapped == EntityType.ORGANIZATION and value.strip().lower() in _ORG_DENYLIST:
                continue
            out.append(
                Detection(
                    entity_type=mapped,
                    value=value,
                    start=r.start,
                    end=r.end,
                    score=float(r.score),
                )
            )
        return out
