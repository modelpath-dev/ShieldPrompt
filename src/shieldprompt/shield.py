"""Core Shield engine — mask and unmask text through the vault."""

from __future__ import annotations

from typing import Optional

from .detector.hybrid import HybridDetector
from .detector.regex_engine import RegexDetector
from .entities import DEFAULT_ENTITIES, NER_ENTITIES, EntityType
from .vault import Vault, get_vault


class Shield:
    """The main ShieldPrompt engine.

    Detects PII in text, replaces it with tokens, and can restore
    tokens back to their original values.

    Args:
        entities: Set of entity types to detect. Defaults to common PII types.
        use_ner: Whether to use the NER model. Auto-detected if None.
        ner_model: HuggingFace model name for NER.
        ner_threshold: Minimum confidence for NER detections.
        vault: Optional vault instance. Uses context-local vault if None.
    """

    def __init__(
        self,
        entities: Optional[set[str]] = None,
        use_ner: Optional[bool] = None,
        ner_model: str = "dslim/bert-base-NER",
        ner_threshold: float = 0.5,
        vault: Optional[Vault] = None,
    ) -> None:
        self._entities = (
            {EntityType(e) if isinstance(e, str) else e for e in entities}
            if entities
            else DEFAULT_ENTITIES
        )
        self._vault = vault

        # Decide whether to use NER
        needs_ner = bool(self._entities & NER_ENTITIES)
        if use_ner is False or not needs_ner:
            self._detector = RegexDetector(entities=self._entities)
        else:
            self._detector = HybridDetector(
                entities=self._entities,
                ner_model=ner_model,
                ner_threshold=ner_threshold,
            )

    @property
    def vault(self) -> Vault:
        return self._vault if self._vault else get_vault()

    def mask(self, text: str) -> str:
        """Detect PII and replace with tokens. Returns masked text."""
        detections = self._detector.detect(text)
        if not detections:
            return text

        # Sort by position descending so replacements don't shift indices
        detections.sort(key=lambda d: d.start, reverse=True)

        result = text
        for det in detections:
            token = self.vault.store(det.entity_type, det.value)
            result = result[:det.start] + token + result[det.end:]

        return result

    def unmask(self, text: str) -> str:
        """Restore tokens in text back to their real values."""
        return self.vault.restore_text(text)

    def mask_and_track(self, text: str) -> tuple[str, dict[str, str]]:
        """Mask text and return (masked_text, mappings_dict)."""
        masked = self.mask(text)
        return masked, self.vault.mappings

    def clear(self) -> None:
        """Clear the vault mappings."""
        self.vault.clear()
