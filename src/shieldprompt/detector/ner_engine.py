"""Contextual PII detection using a local NER model (optional dependency)."""

from __future__ import annotations

import logging
from typing import Optional

from .regex_engine import Detection
from ..entities import EntityType

logger = logging.getLogger("shieldprompt")

# Map NER labels to our entity types
_LABEL_MAP: dict[str, str] = {
    "PER": EntityType.PERSON,
    "PERSON": EntityType.PERSON,
    "B-PER": EntityType.PERSON,
    "I-PER": EntityType.PERSON,
    "ORG": EntityType.ORGANIZATION,
    "ORGANIZATION": EntityType.ORGANIZATION,
    "B-ORG": EntityType.ORGANIZATION,
    "I-ORG": EntityType.ORGANIZATION,
    "LOC": EntityType.LOCATION,
    "LOCATION": EntityType.LOCATION,
    "GPE": EntityType.LOCATION,
    "B-LOC": EntityType.LOCATION,
    "I-LOC": EntityType.LOCATION,
    "DATE": EntityType.DATE,
    "B-DATE": EntityType.DATE,
    "I-DATE": EntityType.DATE,
    "MONEY": EntityType.MONEY,
    "B-MONEY": EntityType.MONEY,
    "I-MONEY": EntityType.MONEY,
}


class NERDetector:
    """Detects named entities using a local transformer model."""

    def __init__(
        self,
        model_name: str = "dslim/bert-base-NER",
        entities: Optional[set[str]] = None,
    ) -> None:
        self._model_name = model_name
        self._entities = entities
        self._pipeline = None

    def _load(self) -> None:
        if self._pipeline is not None:
            return
        try:
            from transformers import pipeline

            self._pipeline = pipeline(
                "ner",
                model=self._model_name,
                aggregation_strategy="simple",
            )
            logger.info("NER model loaded: %s", self._model_name)
        except ImportError:
            raise ImportError(
                "NER detection requires extra dependencies. "
                "Install with: pip install shieldprompt[ner]"
            )

    def detect(self, text: str) -> list[Detection]:
        self._load()
        assert self._pipeline is not None

        results = self._pipeline(text)
        detections: list[Detection] = []

        for ent in results:
            label = ent.get("entity_group", ent.get("entity", ""))
            mapped = _LABEL_MAP.get(label)
            if mapped is None:
                continue
            if self._entities and mapped not in self._entities:
                continue

            value = text[ent["start"]:ent["end"]]
            # Skip very short detections (likely noise)
            if len(value.strip()) < 2:
                continue

            detections.append(
                Detection(
                    entity_type=mapped,
                    value=value,
                    start=ent["start"],
                    end=ent["end"],
                    score=float(ent.get("score", 0.0)),
                )
            )

        return detections
