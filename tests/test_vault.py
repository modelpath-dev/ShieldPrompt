"""Tests for the vault module."""

from shieldprompt.vault import Vault, get_vault, set_vault, reset_vault


def test_store_and_restore():
    vault = Vault()
    token = vault.store("EMAIL_ADDRESS", "test@example.com")
    assert token == "[EMAIL_ADDRESS_1]"
    assert vault.restore(token) == "test@example.com"


def test_idempotent_store():
    vault = Vault()
    t1 = vault.store("EMAIL_ADDRESS", "test@example.com")
    t2 = vault.store("EMAIL_ADDRESS", "test@example.com")
    assert t1 == t2


def test_counter_increments():
    vault = Vault()
    t1 = vault.store("PERSON", "Alice")
    t2 = vault.store("PERSON", "Bob")
    assert t1 == "[PERSON_1]"
    assert t2 == "[PERSON_2]"


def test_restore_text():
    vault = Vault()
    vault.store("PERSON", "Alice")
    vault.store("EMAIL_ADDRESS", "alice@test.com")
    text = "Hello [PERSON_1], your email is [EMAIL_ADDRESS_1]."
    restored = vault.restore_text(text)
    assert restored == "Hello Alice, your email is alice@test.com."


def test_clear():
    vault = Vault()
    vault.store("PERSON", "Alice")
    vault.clear()
    assert vault.restore("[PERSON_1]") is None
    assert vault.mappings == {}


def test_context_var_isolation():
    vault1 = Vault()
    vault1.store("PERSON", "Alice")
    tok = set_vault(vault1)

    v = get_vault()
    assert v is vault1
    assert v.restore("[PERSON_1]") == "Alice"

    reset_vault(tok)
