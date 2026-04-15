"""Hybrid detector combining regex and NER engines."""

from __future__ import annotations

import logging
from typing import Optional

from .regex_engine import Detection, RegexDetector
from ..entities import REGEX_ENTITIES, NER_ENTITIES

logger = logging.getLogger("shieldprompt")


class HybridDetector:
    """Combines regex (fast, deterministic) and NER (contextual) detection.

    NER backend selection order:
      1. Presidio (presidio-analyzer + spaCy en_core_web_lg) — preferred
      2. HuggingFace transformer (dslim/bert-base-NER) — fallback
      3. Regex only — if neither is installed
    """

    def __init__(
        self,
        entities: Optional[set[str]] = None,
        ner_model: str = "dslim/bert-base-NER",
        ner_threshold: float = 0.35,
        use_ner: bool = True,
        spacy_model: str = "en_core_web_sm",
    ) -> None:
        self._entities = entities
        self._ner_threshold = ner_threshold

        regex_entities = entities & REGEX_ENTITIES if entities else None
        self._regex = RegexDetector(entities=regex_entities)

        self._ner = None
        need_ner = use_ner and (entities is None or bool(entities & NER_ENTITIES))
        if need_ner:
            self._ner = self._init_ner_backend(
                entities=entities,
                spacy_model=spacy_model,
                ner_model=ner_model,
                ner_threshold=ner_threshold,
            )

    @staticmethod
    def _init_ner_backend(
        entities: Optional[set[str]],
        spacy_model: str,
        ner_model: str,
        ner_threshold: float,
    ):
        ner_entities = entities & NER_ENTITIES if entities else None

        # Try Presidio first.
        try:
            from .presidio_engine import PresidioDetector

            detector = PresidioDetector(
                spacy_model=spacy_model,
                score_threshold=ner_threshold,
                entities=ner_entities,
            )
            # Force-load so missing spaCy model fails fast here instead of at
            # first detect() call — lets us fall back to the transformer.
            detector._load()
            logger.info("Using Presidio NER backend")
            return detector
        except ImportError as e:
            logger.info("Presidio not available (%s); trying transformer backend", e)
        except Exception as e:
            logger.warning("Presidio failed to initialize (%s); trying transformer backend", e)

        # Fall back to transformer.
        try:
            from .ner_engine import NERDetector

            logger.info("Using HuggingFace transformer NER backend: %s", ner_model)
            return NERDetector(model_name=ner_model, entities=ner_entities)
        except ImportError:
            logger.info(
                "No NER backend installed — regex-only detection. "
                "Install with: pip install shieldprompt[presidio] "
                "or: pip install shieldprompt[ner]"
            )
            return None

    def detect(self, text: str) -> list[Detection]:
        """Run all enabled engines and merge results."""
        detections = self._regex.detect(text)

        if self._ner:
            try:
                ner_detections = self._ner.detect(text)
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
            overlaps = any(
                nd.start < re and nd.end > rs for rs, re in regex_spans
            )
            if not overlaps:
                merged.append(nd)

        merged.sort(key=lambda d: d.start)
        return merged
