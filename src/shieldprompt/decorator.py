"""Python decorator for automatic PII masking/unmasking around LLM calls."""

from __future__ import annotations

import asyncio
import functools
import inspect
from typing import Any, Callable, Optional

from .entities import DEFAULT_ENTITIES, EntityType
from .shield import Shield
from .vault import Vault, reset_vault, set_vault


def mask_pii(
    entities: Optional[list[str]] = None,
    use_ner: Optional[bool] = None,
    ner_model: str = "dslim/bert-base-NER",
    ner_threshold: float = 0.5,
    param_name: str = "prompt",
    mask_kwargs: Optional[list[str]] = None,
    unmask_response: bool = True,
) -> Callable:
    """Decorator that masks PII in function arguments and unmasks the response.

    Works with both sync and async functions. The decorated function receives
    sanitized text, and its return value is automatically de-tokenized.

    Args:
        entities: List of entity type names to detect.
        use_ner: Whether to use NER model. Auto-detected if None.
        ner_model: HuggingFace model for NER.
        ner_threshold: Minimum NER confidence.
        param_name: Name of the parameter to mask (default: "prompt").
            Also masks the first positional string arg if param not found.
        mask_kwargs: Additional keyword argument names to mask.
        unmask_response: Whether to unmask the return value (default: True).

    Usage:
        @mask_pii(entities=["PERSON", "EMAIL_ADDRESS"])
        def call_llm(prompt: str) -> str:
            return openai_client.chat(prompt)

        @mask_pii()
        async def call_llm_async(prompt: str) -> str:
            return await anthropic_client.messages.create(prompt)
    """
    entity_set = (
        {EntityType(e) for e in entities} if entities else DEFAULT_ENTITIES
    )

    def decorator(func: Callable) -> Callable:
        sig = inspect.signature(func)

        def _create_shield() -> tuple[Shield, Vault]:
            vault = Vault()
            shield = Shield(
                entities=entity_set,
                use_ner=use_ner,
                ner_model=ner_model,
                ner_threshold=ner_threshold,
                vault=vault,
            )
            return shield, vault

        def _mask_args(
            shield: Shield, args: tuple, kwargs: dict
        ) -> tuple[tuple, dict]:
            """Mask the target parameter(s) in args/kwargs."""
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            # Mask the primary param
            if param_name in bound.arguments:
                val = bound.arguments[param_name]
                if isinstance(val, str):
                    bound.arguments[param_name] = shield.mask(val)
            else:
                # Fall back: mask first string argument by position
                for name, val in bound.arguments.items():
                    if isinstance(val, str):
                        bound.arguments[name] = shield.mask(val)
                        break

            # Mask additional kwargs
            if mask_kwargs:
                for kw in mask_kwargs:
                    if kw in bound.arguments and isinstance(
                        bound.arguments[kw], str
                    ):
                        bound.arguments[kw] = shield.mask(
                            bound.arguments[kw]
                        )

            new_args = tuple(bound.args)
            new_kwargs = bound.kwargs
            return new_args, new_kwargs

        def _unmask_result(shield: Shield, result: Any) -> Any:
            if not unmask_response:
                return result
            if isinstance(result, str):
                return shield.unmask(result)
            if isinstance(result, dict):
                return {
                    k: shield.unmask(v) if isinstance(v, str) else v
                    for k, v in result.items()
                }
            return result

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                shield, vault = _create_shield()
                ctx_token = set_vault(vault)
                try:
                    new_args, new_kwargs = _mask_args(shield, args, kwargs)
                    result = await func(*new_args, **new_kwargs)
                    return _unmask_result(shield, result)
                finally:
                    reset_vault(ctx_token)

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                shield, vault = _create_shield()
                ctx_token = set_vault(vault)
                try:
                    new_args, new_kwargs = _mask_args(shield, args, kwargs)
                    result = func(*new_args, **new_kwargs)
                    return _unmask_result(shield, result)
                finally:
                    reset_vault(ctx_token)

            return sync_wrapper

    return decorator
