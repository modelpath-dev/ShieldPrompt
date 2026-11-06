"""Regression coverage for integration boundaries using synthetic PII only."""
import asyncio
import json

import pytest

from shieldprompt.decorator import mask_pii
from shieldprompt.middleware import ShieldPromptMiddleware
from shieldprompt.vault import get_vault

EMAIL = "synthetic@example.com"


def test_variadic_keywords_deduplicated_and_nested_result():
    @mask_pii(entities=["EMAIL_ADDRESS"], use_ner=False,
              mask_kwargs=["prompt", "context", "context"])
    def echo(**kwargs):
        assert EMAIL not in repr(kwargs)
        assert "\u200b" not in repr(kwargs)
        return {"nested": [kwargs["prompt"], {"context": kwargs["context"]}]}

    assert echo(prompt=EMAIL, context=EMAIL) == {"nested": [EMAIL, {"context": EMAIL}]}


def test_variadic_positional_fallback():
    @mask_pii(entities=["EMAIL_ADDRESS"], use_ner=False)
    def echo(*args):
        assert EMAIL not in repr(args)
        return args

    assert echo(123, EMAIL) == (123, EMAIL)


@pytest.mark.asyncio
async def test_async_decorator_isolates_concurrent_vaults():
    @mask_pii(entities=["EMAIL_ADDRESS"], use_ner=False)
    async def echo(prompt):
        await asyncio.sleep(0)
        assert len(get_vault().mappings) == 1
        return [prompt]

    values = ["synthetic1@example.com", "synthetic2@example.com"]
    assert await asyncio.gather(*(echo(v) for v in values)) == [[v] for v in values]


async def invoke(app, body=b"{}", extra_messages=None):
    received = [{"type": "http.request", "body": body, "more_body": False}]
    received += extra_messages or []
    sent = []

    async def receive():
        if received:
            return received.pop(0)
        await asyncio.Future()

    async def send(message):
        sent.append(message)

    await app({"type": "http", "path": "/", "headers": []}, receive, send)
    return sent


@pytest.mark.asyncio
async def test_json_restoration_escapes_values_and_preserves_types():
    async def app(scope, receive, send):
        await receive()
        # Synthetic value deliberately exercises JSON escaping, independent of detectors.
        token = get_vault().store("PHONE_NUMBER", '555\n123\t"4567')
        body = json.dumps({"nested": [token, 3, None]}).encode()
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode()), (b"etag", b"old")]})
        await send({"type": "http.response.body", "body": body})

    sent = await invoke(ShieldPromptMiddleware(app, entities=["EMAIL_ADDRESS"], use_ner=False))
    assert json.loads(sent[1]["body"]) == {"nested": ['555\n123\t"4567', 3, None]}
    assert dict(sent[0]["headers"])[b"content-length"] == str(len(sent[1]["body"])).encode()
    assert b"etag" not in dict(sent[0]["headers"])


@pytest.mark.asyncio
async def test_streams_forward_immediately_without_fake_disconnect():
    sent = []
    messages = iter([{"type": "http.request", "body": b"{}"},
                     {"type": "http.request", "body": b"", "more_body": False}])

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    async def app(scope, receive, send):
        await receive()
        assert (await receive())["type"] == "http.request"
        token = get_vault().store("EMAIL_ADDRESS", EMAIL)
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/event-stream")]})
        await send({"type": "http.response.body", "body": token.encode(), "more_body": True})
        assert len(sent) == 2  # no waiting for stream completion
        await send({"type": "http.response.body", "body": b"done", "more_body": False})

    await ShieldPromptMiddleware(app, entities=["EMAIL_ADDRESS"], use_ner=False)(
        {"type": "http", "path": "/", "headers": []}, receive, send)
    assert sent[1]["body"] == b"[EMAIL_ADDRESS_1]"
    assert sent[2]["body"] == b"done"


@pytest.mark.asyncio
async def test_request_limit_rejects_before_app_runs():
    async def app(*args):
        pytest.fail("Oversized request must not reach app")

    wrapped = ShieldPromptMiddleware(app, entities=["EMAIL_ADDRESS"], use_ner=False, max_request_bytes=4)
    sent = await invoke(wrapped, b"12345")
    assert sent[0]["status"] == 413


@pytest.mark.asyncio
async def test_response_limit_preserves_tokenized_body():
    async def app(scope, receive, send):
        await receive()
        token = get_vault().store("EMAIL_ADDRESS", EMAIL)
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"text/plain")]})
        await send({"type": "http.response.body", "body": token.encode()})

    wrapped = ShieldPromptMiddleware(app, entities=["EMAIL_ADDRESS"], use_ner=False, max_response_bytes=4)
    sent = await invoke(wrapped)
    assert sent[1]["body"] == b"[EMAIL_ADDRESS_1]"


@pytest.mark.asyncio
async def test_middleware_reuses_detector_and_isolates_concurrent_requests():
    detectors = []

    async def app(scope, receive, send):
        data = json.loads((await receive())["body"])
        assert "@" not in data["prompt"]
        await asyncio.sleep(0)
        assert len(get_vault().mappings) == 1
        await send({"type": "http.response.start", "status": 200,
                    "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": json.dumps(data).encode()})

    wrapped = ShieldPromptMiddleware(app, entities=["EMAIL_ADDRESS"], use_ner=False)
    original_detect = wrapped.template._detector.detect

    def detect(text):
        detectors.append(wrapped.template._detector)
        return original_detect(text)

    wrapped.template._detector.detect = detect
    values = ["synthetic1@example.com", "synthetic2@example.com"]
    results = await asyncio.gather(*(invoke(wrapped, json.dumps({"prompt": v}).encode()) for v in values))
    assert [json.loads(r[1]["body"])["prompt"] for r in results] == values
    assert len(detectors) == 2
    assert detectors[0] is detectors[1]


@pytest.mark.asyncio
async def test_request_disconnect_does_not_call_app():
    async def app(*args):
        pytest.fail("Disconnected request must not reach app")

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        pytest.fail("No response should be sent after disconnect")

    wrapped = ShieldPromptMiddleware(app, entities=["EMAIL_ADDRESS"], use_ner=False)
    await wrapped({"type": "http", "path": "/", "headers": []}, receive, send)
