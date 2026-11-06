"""PII detection via Microsoft Presidio + spaCy.

Preferred NER backend. Presidio's AnalyzerEngine combines spaCy NER with
Presidio's built-in recognizers and context-aware scoring — handles PERSON,
LOCATION, DATE, ORG, etc. far more reliably than a raw transformer.

The configured spaCy model must be installed explicitly before use.
Detection never downloads or installs executable model packages.
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
        """Require an already-installed spaCy model without network side effects."""
        import spacy

        try:
            spacy.load(self._spacy_model)
            return
        except OSError:
            pass

        raise RuntimeError(
            "The configured spaCy model is not installed. Install it explicitly "
            "before enabling NER."
        )

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
                # Do not inherit Presidio defaults that may ignore or lower
                # ORGANIZATION below our threshold in some package versions.
                "ner_model_configuration": {
                    "model_to_presidio_entity_mapping": {
                        "PER": "PERSON", "PERSON": "PERSON",
                        "LOC": "LOCATION", "LOCATION": "LOCATION",
                        "GPE": "LOCATION", "FAC": "LOCATION",
                        "ORG": "ORGANIZATION", "ORGANIZATION": "ORGANIZATION",
                        "DATE": "DATE_TIME", "TIME": "DATE_TIME",
                        "NORP": "NRP",
                    },
                    "labels_to_ignore": [],
                    "low_score_entity_names": [],
                    "default_score": 0.85,
                },
            }
        )
        self._analyzer = AnalyzerEngine(
            nlp_engine=provider.create_engine(),
            default_score_threshold=self._score_threshold,
        )
        supported = self._analyzer.get_supported_entities(language="en")
        mapped = {_LABEL_MAP[label] for label in supported if label in _LABEL_MAP}
        if self._entities is not None and not self._entities <= mapped:
            self._analyzer = None
            raise RuntimeError("Presidio does not support all requested entity types")
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
            if self._entities is not None and mapped not in self._entities:
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

