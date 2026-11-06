"""FastAPI/Starlette middleware for automatic PII shielding on all endpoints."""

from __future__ import annotations

import copy
import json
import logging
from typing import Optional

from .entities import ALL_ENTITIES, DEFAULT_ENTITIES, EntityType
from .shield import Shield
from .vault import Vault, reset_vault, set_vault

logger = logging.getLogger("shieldprompt")

_SENSITIVITY_MAP: dict[str, set] = {
    "low": {
        EntityType.EMAIL_ADDRESS,
        EntityType.CREDIT_CARD,
        EntityType.SSN,
    },
    "medium": DEFAULT_ENTITIES,
    "high": ALL_ENTITIES,
}


def ShieldPromptMiddleware(
    app,
    sensitivity: str = "medium",
    entities: Optional[list[str]] = None,
    exclude_paths: Optional[list[str]] = None,
    use_ner: Optional[bool] = None,
    ner_model: str = "dslim/bert-base-NER",
    max_request_bytes: int = 1024 * 1024,
    max_response_bytes: int = 1024 * 1024,
):
    """Create and return an ASGI middleware that masks PII in requests
    and unmasks it in finite JSON/text responses.

    Requests larger than max_request_bytes are rejected with 413. Streaming,
    compressed, non-text, and oversized responses are forwarded unchanged
    (still tokenized). Streams are never buffered or partially restored.
    """
    if max_request_bytes <= 0 or max_response_bytes <= 0:
        raise ValueError("Body size limits must be positive")
    try:
        from starlette.types import ASGIApp, Receive, Scope, Send, Message
    except ImportError:
        raise ImportError(
            "FastAPI/Starlette middleware requires extra dependencies. "
            "Install with: pip install shieldprompt[fastapi]"
        )

    if entities is not None:
        entity_set = {EntityType(e) for e in entities}
    else:
        entity_set = _SENSITIVITY_MAP.get(sensitivity, DEFAULT_ENTITIES)

    _exclude = set(exclude_paths or [])

    class _ShieldMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app
            self.template = Shield(
                entities=entity_set, use_ner=use_ner, ner_model=ner_model,
            )

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            path = scope.get("path", "")
            if path in _exclude:
                await self.app(scope, receive, send)
                return

            vault = Vault()
            shield = copy.copy(self.template)
            shield._vault = vault

            body_parts: list[bytes] = []
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                body = message.get("body", b"")
                size += len(body)
                if size > max_request_bytes:
                    await send({"type": "http.response.start", "status": 413,
                                "headers": [(b"content-length", b"0")]})
                    await send({"type": "http.response.body", "body": b""})
                    return
                body_parts.append(body)
                if not message.get("more_body", False):
                    break
            full_body = b"".join(body_parts)
            masked_body = full_body
            try:
                masked_body = json.dumps(_mask_json(shield, json.loads(full_body))).encode()
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

            scope = dict(scope)
            scope["headers"] = [
                (k, str(len(masked_body)).encode() if k.lower() == b"content-length" else v)
                for k, v in scope.get("headers", [])
            ]
            body_sent = False

            async def masked_receive() -> Message:
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {"type": "http.request", "body": masked_body, "more_body": False}
                # A synthetic disconnect cancels Starlette streaming responses.
                return await receive()

            start_message = None
            passthrough = False

            async def masked_send(message: Message) -> None:
                nonlocal start_message, passthrough
                if message["type"] == "http.response.start":
                    start_message = message
                    return
                if message["type"] == "http.response.body" and not passthrough:
                    body = message.get("body", b"")
                    headers = dict(start_message.get("headers", [])) if start_message else {}
                    content_type = headers.get(b"content-type", b"").split(b";", 1)[0].lower()
                    is_json = content_type == b"application/json" or content_type.endswith(b"+json")
                    is_text = content_type.startswith(b"text/")
                    passthrough = (message.get("more_body", False)
                                   or len(body) > max_response_bytes
                                   or b"content-encoding" in headers
                                   or not (is_json or is_text))
                    changed = False
                    if not passthrough:
                        try:
                            if is_json:
                                data = json.loads(body)
                                restored = _unmask_json(shield, data)
                                if restored != data:
                                    body = json.dumps(restored).encode()
                                    changed = True
                            else:
                                restored = shield.unmask(body.decode()).encode()
                                changed = restored != body
                                body = restored
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            pass
                    if start_message is not None:
                        sm = dict(start_message)
                        if changed:
                            # Body-dependent validators no longer describe this body.
                            sm["headers"] = [
                                (k, str(len(body)).encode() if k.lower() == b"content-length" else v)
                                for k, v in sm.get("headers", [])
                                if k.lower() not in (b"etag", b"content-md5", b"digest")
                            ]
                        await send(sm)
                        start_message = None
                    await send(dict(message, body=body))
                    return
                # Preserve ASGI extensions (e.g. pathsend) without delaying start.
                if start_message is not None:
                    await send(start_message)
                    start_message = None
                    passthrough = True
                await send(message)

            token = set_vault(vault)
            try:
                await self.app(scope, masked_receive, masked_send)
            finally:
                reset_vault(token)

    return _ShieldMiddleware(app)


def _mask_json(shield: Shield, data):
    """Recursively mask string values in a JSON structure."""
    if isinstance(data, str):
        return shield.mask(data)
    if isinstance(data, dict):
        return {k: _mask_json(shield, v) for k, v in data.items()}
    if isinstance(data, list):
        return [_mask_json(shield, item) for item in data]
    return data



def _unmask_json(shield: Shield, data):
    """Restore JSON values before serialization, preserving escaping and types."""
    if isinstance(data, str):
        return shield.unmask(data)
    if isinstance(data, dict):
        return {k: _unmask_json(shield, v) for k, v in data.items()}
    if isinstance(data, list):
        return [_unmask_json(shield, item) for item in data]
    return data
