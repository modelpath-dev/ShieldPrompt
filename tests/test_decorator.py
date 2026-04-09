"""Tests for the @mask_pii decorator."""

import asyncio

from shieldprompt import mask_pii


def test_sync_decorator():
    @mask_pii(entities=["EMAIL_ADDRESS"], use_ner=False)
    def echo(prompt: str) -> str:
        # The prompt should be masked
        assert "alice@test.com" not in prompt
        assert "[EMAIL_ADDRESS_1]" in prompt
        return f"Got: {prompt}"

    result = echo("Send to alice@test.com")
    # The result should be unmasked
    assert "alice@test.com" in result
    assert "[EMAIL_ADDRESS_1]" not in result


def test_async_decorator():
    @mask_pii(entities=["EMAIL_ADDRESS"], use_ner=False)
    async def echo_async(prompt: str) -> str:
        assert "bob@test.com" not in prompt
        return f"Got: {prompt}"

    result = asyncio.get_event_loop().run_until_complete(
        echo_async("Send to bob@test.com")
    )
    assert "bob@test.com" in result


def test_decorator_with_kwargs():
    @mask_pii(
        entities=["EMAIL_ADDRESS", "PHONE_NUMBER"],
        use_ner=False,
        mask_kwargs=["context"],
    )
    def process(prompt: str, context: str = "") -> str:
        assert "alice@test.com" not in prompt
        assert "(555) 123-4567" not in context
        return f"{prompt} | {context}"

    result = process(
        "Email alice@test.com", context="Call (555) 123-4567"
    )
    assert "alice@test.com" in result
    assert "(555) 123-4567" in result


def test_decorator_no_pii():
    @mask_pii(entities=["EMAIL_ADDRESS"], use_ner=False)
    def echo(prompt: str) -> str:
        return prompt

    result = echo("Hello world")
    assert result == "Hello world"


def test_decorator_dict_response():
    @mask_pii(entities=["EMAIL_ADDRESS"], use_ner=False)
    def respond(prompt: str) -> dict:
        return {"message": prompt, "status": "ok"}

    result = respond("Contact alice@test.com")
    assert "alice@test.com" in result["message"]
    assert result["status"] == "ok"


def test_positional_arg_fallback():
    @mask_pii(entities=["EMAIL_ADDRESS"], use_ner=False, param_name="nonexistent")
    def echo(text: str) -> str:
        assert "alice@test.com" not in text
        return text

    result = echo("Email alice@test.com")
    assert "alice@test.com" in result
