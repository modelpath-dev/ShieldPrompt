"""ShieldPrompt — Privacy bridge for LLMs.

Mask PII before it leaves your machine, unmask it when the response comes back.
"""

from .decorator import mask_pii
from .entities import EntityType
from .shield import Shield
from .vault import Vault, get_vault

__version__ = "0.1.0"

__all__ = [
    "Shield",
    "Vault",
    "EntityType",
    "mask_pii",
    "get_vault",
    "__version__",
]
