"""Hybrid detector combining regex and NER engines."""

from __future__ import annotations

import logging
from typing import Optional

from .regex_engine import Detection, RegexDetector
from ..entities import REGEX_ENTITIES, NER_ENTITIES

logger = logging.getLogger("shieldprompt")


class HybridDetector:
    """Combines regex (fast, deterministic) and NER (contextual) detection.

    NER is only loaded if NER entity types are requested AND the dependency
    is installed. Falls back gracefully to regex-only.
    """

    def __init__(
        self,
        entities: Optional[set[str]] = None,
        ner_model: str = "dslim/bert-base-NER",
        ner_threshold: float = 0.5,
    ) -> None:
        self._entities = entities
        self._ner_threshold = ner_threshold

        # Always init regex for the regex-detectable subset
        regex_entities = entities & REGEX_ENTITIES if entities else None
        self._regex = RegexDetector(entities=regex_entities)

        # Only init NER if needed
        self._ner = None
        need_ner = entities is None or bool(entities & NER_ENTITIES)
        if need_ner:
            try:
                from .ner_engine import NERDetector

                ner_entities = entities & NER_ENTITIES if entities else None
                self._ner = NERDetector(
                    model_name=ner_model, entities=ner_entities
                )
            except ImportError:
                logger.info(
                    "NER dependencies not installed. "
                    "Using regex-only detection. "
                    "Install with: pip install shieldprompt[ner]"
                )

    def detect(self, text: str) -> list[Detection]:
        """Run all enabled engines and merge results."""
        detections = self._regex.detect(text)

        if self._ner:
            try:
                ner_detections = self._ner.detect(text)
                # Filter by confidence threshold
                ner_detections = [
                    d for d in ner_detections if d.score >= self._ner_threshold
                ]
                detections = self._merge(detections, ner_detections)
            except Exception as e:
                logger.warning("NER detection failed, using regex only: %s", e)

        return detections

    @staticmethod
    def _merge(
        regex_dets: list[Detection], ner_dets: list[Detection]
    ) -> list[Detection]:
        """Merge detections, preferring regex for overlapping spans."""
        merged = list(regex_dets)
        regex_spans = {(d.start, d.end) for d in regex_dets}

        for nd in ner_dets:
            # Skip if it overlaps with any regex detection
            overlaps = any(
                nd.start < re and nd.end > rs for rs, re in regex_spans
            )
            if not overlaps:
                merged.append(nd)

        # Sort by position
        merged.sort(key=lambda d: d.start)
        return merged
