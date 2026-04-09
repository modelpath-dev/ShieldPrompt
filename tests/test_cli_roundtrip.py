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
