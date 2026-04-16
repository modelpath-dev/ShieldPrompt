"""Tests for the vault module."""

from shieldprompt.vault import Vault, get_vault, set_vault, reset_vault


def test_store_and_restore():
    vault = Vault()
    token = vault.store("EMAIL_ADDRESS", "test@example.com")
    assert token == "[EMAIL_ADDRESS_1]"
    assert vault.restore(token) == "test@example.com"


def test_store_accepts_enum_entity_type():
    """Python 3.11 changed Enum.__format__; passing EntityType must still
    yield a clean token like [PHONE_NUMBER_1], never [EntityType.PHONE_NUMBER_1]."""
    from shieldprompt.entities import EntityType

    vault = Vault()
    token = vault.store(EntityType.PHONE_NUMBER, "+1-415-555-1234")
    assert token == "[PHONE_NUMBER_1]"
    assert vault.restore(token) == "+1-415-555-1234"


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


def test_to_dict_and_from_dict_roundtrip():
    original = Vault()
    original.store("EMAIL_ADDRESS", "alice@example.com")
    original.store("PHONE_NUMBER", "+1-415-555-1234")

    snapshot = original.to_dict()
    assert snapshot == {
        "[EMAIL_ADDRESS_1]": "alice@example.com",
        "[PHONE_NUMBER_1]": "+1-415-555-1234",
    }

    rebuilt = Vault.from_dict(snapshot)
    assert rebuilt.restore("[EMAIL_ADDRESS_1]") == "alice@example.com"
    text = "Hi [EMAIL_ADDRESS_1] at [PHONE_NUMBER_1]"
    assert rebuilt.restore_text(text) == "Hi alice@example.com at +1-415-555-1234"


def test_context_var_isolation():
    vault1 = Vault()
    vault1.store("PERSON", "Alice")
    tok = set_vault(vault1)

    v = get_vault()
    assert v is vault1
    assert v.restore("[PERSON_1]") == "Alice"

    reset_vault(tok)
