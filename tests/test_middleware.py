"""Tests for the FastAPI middleware."""

import pytest

try:
    from fastapi import FastAPI
    from httpx import AsyncClient, ASGITransport
    from shieldprompt.middleware import ShieldPromptMiddleware

    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="fastapi not installed")


def _make_app():
    app = FastAPI()

    @app.post("/chat")
    async def chat(data: dict):
        prompt = data.get("prompt", "")
        return {"response": f"Received: {prompt}"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    wrapped = ShieldPromptMiddleware(
        app,
        sensitivity="medium",
        exclude_paths=["/health"],
        use_ner=False,
    )
    return wrapped


@pytest.mark.asyncio
async def test_health_excluded():
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_chat_masks_and_unmasks():
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/chat",
            json={"prompt": "My email is alice@example.com"},
        )
        assert resp.status_code == 200
        body = resp.json()
        # The response should contain the unmasked email
        assert "alice@example.com" in body["response"]
