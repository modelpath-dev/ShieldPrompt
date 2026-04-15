"""Tests for file-based CLI roundtrip workflows."""

from __future__ import annotations

import json

from shieldprompt import cli


def _run_cli(monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["shieldprompt", *argv])
    cli.main()


def test_file_mask_unmask_roundtrip_with_default_sidecar(tmp_path, monkeypatch, capsys):
    original = (
        "Name Alice\n"
        "Phone +1-415-555-1234\n"
        "Email alice@example.com\n"
        "API sk-abcdefghijklmnopqrstuvwxyz\n"
    )
    text_path = tmp_path / "secrets.txt"
    text_path.write_text(original)

    _run_cli(
        monkeypatch,
        "mask",
        "--file",
        str(text_path),
        "--entities",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "API_KEY",
        "--in-place",
        "--no-ner",
    )

    masked = text_path.read_text()
    assert "[EMAIL_ADDRESS_1]" in masked
    assert "[PHONE_NUMBER_1]" in masked
    assert "[API_KEY_1]" in masked
    assert "alice@example.com" not in masked
    assert "+1-415-555-1234" not in masked

    vault_path = tmp_path / "secrets.txt.shieldprompt.vault.json"
    assert vault_path.exists()
    mappings = json.loads(vault_path.read_text())
    assert mappings["[EMAIL_ADDRESS_1]"] == "alice@example.com"

    _run_cli(monkeypatch, "map", "--file", str(text_path), "--json")
    out = capsys.readouterr().out
    printed = json.loads(out)
    assert printed["[PHONE_NUMBER_1]"] == "+1-415-555-1234"

    _run_cli(
        monkeypatch,
        "unmask",
        "--file",
        str(text_path),
        "--in-place",
    )
    restored = text_path.read_text()
    assert restored == original


def test_short_aliases_pii_and_retrace(tmp_path, monkeypatch):
    original = "Email alice@example.com and phone +1-415-555-1234"
    text_path = tmp_path / "secret.txt"
    text_path.write_text(original)

    _run_cli(
        monkeypatch,
        "pii",
        "--file",
        str(text_path),
        "--entities",
        "EMAIL_ADDRESS",
        "PHONE_NUMBER",
        "--in-place",
        "--no-ner",
    )
    masked = text_path.read_text()
    assert "[EMAIL_ADDRESS_1]" in masked
    assert "[PHONE_NUMBER_1]" in masked

    _run_cli(monkeypatch, "retrace", "--file", str(text_path), "--in-place")
    assert text_path.read_text() == original


def test_direct_entrypoint_commands(tmp_path, monkeypatch):
    original = "alice@example.com"
    text_path = tmp_path / "direct.txt"
    text_path.write_text(original)

    monkeypatch.setattr(
        "sys.argv",
        [
            "pii",
            "--file",
            str(text_path),
            "--entities",
            "EMAIL_ADDRESS",
            "--in-place",
            "--no-ner",
        ],
    )
    cli.pii_main()
    assert "[EMAIL_ADDRESS_1]" in text_path.read_text()

    monkeypatch.setattr("sys.argv", ["retrace", "--file", str(text_path), "--in-place"])
    cli.retrace_main()
    assert text_path.read_text() == original


def test_pii_entrypoint_tolerates_redundant_mask_subcommand(tmp_path, monkeypatch):
    """Users who type `pii mask ...` should not hit an arg-parse error."""
    text_path = tmp_path / "redundant.txt"
    text_path.write_text("alice@example.com")

    monkeypatch.setattr(
        "sys.argv",
        [
            "pii",
            "mask",
            "--file",
            str(text_path),
            "--entities",
            "EMAIL_ADDRESS",
            "--in-place",
            "--no-ner",
        ],
    )
    cli.pii_main()
    assert "[EMAIL_ADDRESS_1]" in text_path.read_text()

    monkeypatch.setattr(
        "sys.argv",
        ["retrace", "unmask", "--file", str(text_path), "--in-place"],
    )
    cli.retrace_main()
    assert text_path.read_text() == "alice@example.com"


def test_vault_file_permissions_are_owner_only(tmp_path, monkeypatch):
    import os
    import stat

    text_path = tmp_path / "perms.txt"
    text_path.write_text("alice@example.com")

    _run_cli(
        monkeypatch,
        "mask",
        "--file",
        str(text_path),
        "--entities",
        "EMAIL_ADDRESS",
        "--in-place",
        "--no-ner",
    )
    vault_path = tmp_path / "perms.txt.shieldprompt.vault.json"
    assert vault_path.exists()
    if os.name == "posix":
        mode = stat.S_IMODE(vault_path.stat().st_mode)
        assert mode == 0o600, f"expected 0o600, got {oct(mode)}"
