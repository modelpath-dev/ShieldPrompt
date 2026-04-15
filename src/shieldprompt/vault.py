"""Zero-persistence vault using contextvars for thread/async safety."""

from __future__ import annotations

import contextvars
import threading
from typing import Optional


_vault_var: contextvars.ContextVar[Optional["Vault"]] = contextvars.ContextVar(
    "shieldprompt_vault", default=None
)


class Vault:
    """Maps PII tokens <-> real values. Lives only in memory, scoped to context."""

    def __init__(self) -> None:
        self._token_to_real: dict[str, str] = {}
        self._real_to_token: dict[str, str] = {}
        self._counters: dict[str, int] = {}
        self._lock = threading.Lock()

    def store(self, entity_type: str, real_value: str) -> str:
        """Store a real value and return its token. Idempotent for same value."""
        with self._lock:
            if real_value in self._real_to_token:
                return self._real_to_token[real_value]

            count = self._counters.get(entity_type, 0) + 1
            self._counters[entity_type] = count
            token = f"[{entity_type}_{count}]"

            self._token_to_real[token] = real_value
            self._real_to_token[real_value] = token
            return token

    def restore(self, token: str) -> Optional[str]:
        """Get the real value for a token."""
        return self._token_to_real.get(token)

    def restore_text(self, text: str) -> str:
        """Replace all tokens in text with their real values."""
        result = text
        # Sort by token length descending to avoid partial replacement issues
        for token, real in sorted(
            self._token_to_real.items(), key=lambda x: len(x[0]), reverse=True
        ):
            result = result.replace(token, real)
        return result

    @property
    def mappings(self) -> dict[str, str]:
        """Return a copy of token->real mappings (for debugging)."""
        return dict(self._token_to_real)

    def to_dict(self) -> dict[str, str]:
        """Return a copy of token->real mappings, suitable for JSON serialization."""
        return dict(self._token_to_real)

    @classmethod
    def from_dict(cls, mappings: dict[str, str]) -> "Vault":
        """Rebuild a Vault from a token->real mapping dict."""
        vault = cls()
        with vault._lock:
            for token, real in mappings.items():
                vault._token_to_real[token] = real
                vault._real_to_token[real] = token
        return vault

    def clear(self) -> None:
        """Wipe all mappings."""
        with self._lock:
            self._token_to_real.clear()
            self._real_to_token.clear()
            self._counters.clear()


def get_vault() -> Vault:
    """Get the vault for the current context, creating one if needed."""
    vault = _vault_var.get()
    if vault is None:
        vault = Vault()
        _vault_var.set(vault)
    return vault


def set_vault(vault: Vault) -> contextvars.Token:
    """Set a vault for the current context. Returns a reset token."""
    return _vault_var.set(vault)


def reset_vault(token: contextvars.Token) -> None:
    """Reset the vault to its previous state."""
    _vault_var.reset(token)
