"""FastAPI/Starlette middleware for automatic PII shielding on all endpoints."""

from __future__ import annotations

import json
import logging
from typing import Optional

from .entities import ALL_ENTITIES, DEFAULT_ENTITIES, EntityType
from .shield import Shield
from .vault import Vault

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
):
    """Create and return an ASGI middleware that masks PII in requests
    and unmasks it in responses."""
    try:
        from starlette.types import ASGIApp, Receive, Scope, Send, Message
    except ImportError:
        raise ImportError(
            "FastAPI/Starlette middleware requires extra dependencies. "
            "Install with: pip install shieldprompt[fastapi]"
        )

    if entities:
        entity_set = {EntityType(e) for e in entities}
    else:
        entity_set = _SENSITIVITY_MAP.get(sensitivity, DEFAULT_ENTITIES)

    _exclude = set(exclude_paths or [])

    class _ShieldMiddleware:
        def __init__(self, app: ASGIApp) -> None:
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
            if scope["type"] != "http":
                await self.app(scope, receive, send)
                return

            path = scope.get("path", "")
            if path in _exclude:
                await self.app(scope, receive, send)
                return

            vault = Vault()
            shield = Shield(
                entities=entity_set,
                use_ner=use_ner,
                ner_model=ner_model,
                vault=vault,
            )

            # Read the entire request body first
            body_parts: list[bytes] = []
            while True:
                message = await receive()
                body_parts.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break

            full_body = b"".join(body_parts)

            # Try to mask JSON body
            masked_body = full_body
            try:
                data = json.loads(full_body)
                masked_data = _mask_json(shield, data)
                masked_body = json.dumps(masked_data).encode()
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

            # Update content-length in scope headers
            new_headers = []
            for k, v in scope.get("headers", []):
                if k == b"content-length":
                    new_headers.append((k, str(len(masked_body)).encode()))
                else:
                    new_headers.append((k, v))
            scope["headers"] = new_headers

            # Provide masked body via a new receive
            body_sent = False

            async def masked_receive() -> Message:
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {
                        "type": "http.request",
                        "body": masked_body,
                        "more_body": False,
                    }
                # After body is consumed, return disconnect
                return {"type": "http.disconnect"}

            # Buffer response body for unmasking
            response_started = False
            start_message = None
            response_parts: list[bytes] = []

            async def masked_send(message: Message) -> None:
                nonlocal response_started, start_message

                if message["type"] == "http.response.start":
                    response_started = True
                    start_message = message
                    return

                if message["type"] == "http.response.body":
                    body = message.get("body", b"")
                    more = message.get("more_body", False)
                    response_parts.append(body)

                    if not more:
                        full_resp = b"".join(response_parts)
                        try:
                            text = full_resp.decode()
                            unmasked = shield.unmask(text)
                            full_resp = unmasked.encode()
                        except (UnicodeDecodeError, Exception):
                            pass

                        # Send start with updated content-length
                        if start_message:
                            sm = dict(start_message)
                            new_h = []
                            for k, v in sm.get("headers", []):
                                if k == b"content-length":
                                    new_h.append(
                                        (k, str(len(full_resp)).encode())
                                    )
                                else:
                                    new_h.append((k, v))
                            sm["headers"] = new_h
                            await send(sm)

                        msg = dict(message)
                        msg["body"] = full_resp
                        msg["more_body"] = False
                        await send(msg)
                    return

                await send(message)

            await self.app(scope, masked_receive, masked_send)

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
