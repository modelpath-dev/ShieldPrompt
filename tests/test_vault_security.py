"""Recovery mappings must remain stable across loading and restoration."""
import pytest

from shieldprompt.vault import Vault


def test_loaded_counters_never_overwrite_existing_tokens():
    vault = Vault.from_dict({"[EMAIL_ADDRESS_7]": "old@example.test", "[PERSON_2]": "Example"})
    assert vault.store("EMAIL_ADDRESS", "new@example.test") == "[EMAIL_ADDRESS_8]"
    assert vault.store("PERSON", "Other") == "[PERSON_3]"
    assert vault.restore("[EMAIL_ADDRESS_7]") == "old@example.test"


def test_restore_is_single_pass_even_when_original_contains_another_token():
    vault = Vault.from_dict({"[EMAIL_ADDRESS_1]": "literal [PERSON_1]", "[PERSON_1]": "Example"})
    assert vault.restore_text("[EMAIL_ADDRESS_1] [PERSON_1]") == "literal [PERSON_1] Example"


@pytest.mark.parametrize("mappings", [[], {"": "value"}, {"[PERSON_0]": "value"}, {"[PERSON_1]": 42}, {42: "value"}])
def test_invalid_vaults_fail_closed(mappings):
    with pytest.raises(ValueError):
        Vault.from_dict(mappings)
