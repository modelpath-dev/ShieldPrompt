"""Python decorator for automatic PII masking/unmasking around LLM calls."""

from __future__ import annotations

import asyncio
import copy
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
        {EntityType(e) for e in entities} if entities is not None else DEFAULT_ENTITIES
    )

    def decorator(func: Callable) -> Callable:
        sig = inspect.signature(func)

        # Detectors may load expensive models. Share only detector/configuration;
        # every invocation gets its own vault, including concurrent calls.
        template = Shield(
            entities=entity_set, use_ner=use_ner, ner_model=ner_model,
            ner_threshold=ner_threshold,
        )

        def _create_shield() -> tuple[Shield, Vault]:
            vault = Vault()
            shield = copy.copy(template)
            shield._vault = vault
            return shield, vault

        def _mask_args(
            shield: Shield, args: tuple, kwargs: dict
        ) -> tuple[tuple, dict]:
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            extra_name = next((name for name, p in sig.parameters.items()
                               if p.kind == inspect.Parameter.VAR_KEYWORD), None)
            extras = bound.arguments.get(extra_name, {})
            targets = set()

            def select(name):
                if name in bound.arguments and isinstance(bound.arguments[name], str):
                    targets.add((name, None))
                    return True
                if name in extras and isinstance(extras[name], str):
                    targets.add((extra_name, name))
                    return True
                return False

            if not select(param_name):
                # Fallback is positional only, including strings inside *args.
                for name, p in sig.parameters.items():
                    value = bound.arguments.get(name)
                    if p.kind in (inspect.Parameter.POSITIONAL_ONLY,
                                  inspect.Parameter.POSITIONAL_OR_KEYWORD):
                        if isinstance(value, str):
                            targets.add((name, None))
                            break
                    elif p.kind == inspect.Parameter.VAR_POSITIONAL:
                        index = next((i for i, v in enumerate(value or ())
                                      if isinstance(v, str)), None)
                        if index is not None:
                            targets.add((name, index))
                            break
            for name in mask_kwargs or []:
                select(name)

            # A target is masked exactly once even if it is listed repeatedly.
            for name, key in sorted(targets, key=repr):
                if key is None:
                    bound.arguments[name] = shield.mask(bound.arguments[name])
                elif isinstance(key, int):
                    values = list(bound.arguments[name])
                    values[key] = shield.mask(values[key])
                    bound.arguments[name] = tuple(values)
                else:
                    bound.arguments[name][key] = shield.mask(bound.arguments[name][key])
            return tuple(bound.args), bound.kwargs

        def _unmask_result(shield: Shield, result: Any) -> Any:
            if not unmask_response:
                return result
            if isinstance(result, str):
                return shield.unmask(result)
            if isinstance(result, dict):
                return {k: _unmask_result(shield, v) for k, v in result.items()}
            if isinstance(result, list):
                return [_unmask_result(shield, v) for v in result]
            if isinstance(result, tuple):
                return tuple(_unmask_result(shield, v) for v in result)
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

