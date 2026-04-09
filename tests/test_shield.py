"""Tests for the Shield engine (end-to-end mask/unmask)."""

from shieldprompt import Shield, Vault
from shieldprompt.entities import EntityType


def _shield(**kwargs):
    """Create a Shield with a fresh vault to avoid cross-test leakage."""
    return Shield(vault=Vault(), **kwargs)


def test_mask_email():
    shield = _shield(entities={EntityType.EMAIL_ADDRESS}, use_ner=False)
    text = "Send to alice@example.com please."
    masked = shield.mask(text)
    assert "alice@example.com" not in masked
    assert "[EMAIL_ADDRESS_1]" in masked


def test_unmask_restores():
    shield = _shield(entities={EntityType.EMAIL_ADDRESS}, use_ner=False)
    text = "Send to alice@example.com please."
    masked = shield.mask(text)
    unmasked = shield.unmask(masked)
    assert unmasked == text


def test_roundtrip_multiple():
    shield = _shield(
        entities={EntityType.EMAIL_ADDRESS, EntityType.PHONE_NUMBER, EntityType.SSN},
        use_ner=False,
    )
    text = "Email: bob@test.com, Phone: (555) 123-4567, SSN: 123-45-6789"
    masked = shield.mask(text)
    assert "bob@test.com" not in masked
    assert "(555) 123-4567" not in masked
    assert "123-45-6789" not in masked

    unmasked = shield.unmask(masked)
    assert unmasked == text


def test_mask_and_track():
    shield = _shield(entities={EntityType.EMAIL_ADDRESS}, use_ner=False)
    text = "Contact alice@test.com"
    masked, mappings = shield.mask_and_track(text)
    assert "[EMAIL_ADDRESS_1]" in mappings
    assert mappings["[EMAIL_ADDRESS_1]"] == "alice@test.com"


def test_no_pii_passthrough():
    shield = _shield(entities={EntityType.EMAIL_ADDRESS}, use_ner=False)
    text = "The weather is nice today."
    masked = shield.mask(text)
    assert masked == text


def test_clear_vault():
    shield = _shield(entities={EntityType.EMAIL_ADDRESS}, use_ner=False)
    shield.mask("Email: a@b.com")
    shield.clear()
    assert shield.vault.mappings == {}


def test_idempotent_masking():
    shield = _shield(entities={EntityType.EMAIL_ADDRESS}, use_ner=False)
    text = "Email a@b.com and a@b.com again."
    masked = shield.mask(text)
    assert masked.count("[EMAIL_ADDRESS_1]") == 2


def test_ip_and_url():
    shield = _shield(
        entities={EntityType.IP_ADDRESS, EntityType.URL}, use_ner=False
    )
    text = "Server at 192.168.1.1, docs at https://docs.example.com/api"
    masked = shield.mask(text)
    assert "192.168.1.1" not in masked
    assert "https://docs.example.com/api" not in masked
    unmasked = shield.unmask(masked)
    assert unmasked == text
