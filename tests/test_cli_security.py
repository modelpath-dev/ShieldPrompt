"""Regression coverage for recovery-preserving CLI writes."""
import json
import os
import stat

import pytest

from shieldprompt import cli
from shieldprompt.vault import Vault


def mask(source, *extra):
    cli.main(["mask", "--file", str(source), "--in-place", "--no-ner", "--entities", "EMAIL_ADDRESS", *extra])


def test_vault_failure_leaves_source_untouched(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_text("fixture@example.test")
    def fail(*args):
        raise OSError("vault write failed")
    monkeypatch.setattr(cli, "_save_vault", fail)
    with pytest.raises(SystemExit):
        mask(source)
    assert source.read_text() == "fixture@example.test"


def test_source_failure_keeps_recovery_vault(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_text("fixture@example.test")
    def fail(*args):
        raise OSError("source replacement failed")
    monkeypatch.setattr(cli.os, "replace", fail)
    with pytest.raises(SystemExit):
        mask(source)
    assert source.read_text() == "fixture@example.test"
    vault = json.loads((tmp_path / "source.shieldprompt.vault.json").read_text())
    assert "fixture@example.test" in vault.values()
    assert not list(tmp_path.glob(".shieldprompt-*"))


def test_repeat_mask_preserves_both_files(tmp_path):
    source = tmp_path / "source"
    source.write_text("fixture@example.test")
    mask(source)
    sidecar = tmp_path / "source.shieldprompt.vault.json"
    before = (source.read_bytes(), sidecar.read_bytes())
    with pytest.raises(SystemExit):
        mask(source)
    assert (source.read_bytes(), sidecar.read_bytes()) == before
    with pytest.raises(SystemExit):
        mask(source, "--save-vault", str(tmp_path / "new-vault"))
    assert source.read_bytes() == before[0]
    cli.main(["unmask", "--file", str(source), "--in-place"])
    assert source.read_text() == "fixture@example.test"


@pytest.mark.parametrize("alias", ["same", "symlink", "hardlink"])
def test_source_vault_alias_rejected(tmp_path, alias):
    source = tmp_path / "source"
    source.write_text("fixture@example.test")
    vault = source if alias == "same" else tmp_path / "vault"
    if alias == "symlink":
        vault.symlink_to(source)
    elif alias == "hardlink":
        os.link(source, vault)
    with pytest.raises(SystemExit):
        mask(source, "--save-vault", str(vault))
    assert source.read_text() == "fixture@example.test"


def test_vault_cannot_overwrite_existing_or_symlink(tmp_path):
    existing = tmp_path / "existing"
    existing.write_text("keep")
    alias = tmp_path / "alias"
    alias.symlink_to(existing)
    for path in (existing, alias):
        with pytest.raises(FileExistsError):
            cli._save_vault(Vault(), str(path))
    assert existing.read_text() == "keep"
    assert not list(tmp_path.glob(".shieldprompt-*"))


@pytest.mark.skipif(os.name != "posix", reason="POSIX permission modes")
def test_private_permissions_at_publication_and_after_restore(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_text("fixture@example.test")
    source.chmod(0o644)
    real_link, real_replace = os.link, os.replace
    def check_link(src, dst):
        assert stat.S_IMODE(os.stat(src).st_mode) == 0o600
        return real_link(src, dst)
    def check_replace(src, dst):
        assert stat.S_IMODE(os.stat(src).st_mode) == 0o600
        return real_replace(src, dst)
    monkeypatch.setattr(cli.os, "link", check_link)
    monkeypatch.setattr(cli.os, "replace", check_replace)
    mask(source)
    cli.main(["unmask", "--file", str(source), "--in-place"])
    assert stat.S_IMODE(source.stat().st_mode) == 0o600


def test_unmask_rejects_source_equal_to_vault(tmp_path):
    source = tmp_path / "vault"
    original = '{"[PERSON_1]": "Fixture"}'
    source.write_text(original)
    with pytest.raises(SystemExit):
        cli.main(["unmask", "--file", str(source), "--vault", str(source), "--in-place"])
    assert source.read_text() == original


@pytest.mark.parametrize("stage", ["file", "directory"])
def test_vault_sync_failure_never_replaces_source(tmp_path, monkeypatch, stage):
    source = tmp_path / "source"
    source.write_text("fixture@example.test")
    def fail(*args):
        raise OSError("sync failed")
    if stage == "file":
        monkeypatch.setattr(cli.os, "fsync", fail)
    else:
        monkeypatch.setattr(cli, "_sync_directory", fail)
    with pytest.raises(SystemExit):
        mask(source)
    assert source.read_text() == "fixture@example.test"
    sidecar = tmp_path / "source.shieldprompt.vault.json"
    if stage == "directory":
        assert "fixture@example.test" in json.loads(sidecar.read_text()).values()
    else:
        assert not sidecar.exists()
    assert not list(tmp_path.glob(".shieldprompt-*"))


def test_vault_created_during_mask_cannot_be_overwritten(tmp_path, monkeypatch):
    source = tmp_path / "source"
    source.write_text("fixture@example.test")
    sidecar = tmp_path / "source.shieldprompt.vault.json"
    real_link = os.link
    def concurrent_link(src, dst):
        sidecar.write_text("concurrent recovery vault")
        return real_link(src, dst)
    monkeypatch.setattr(cli.os, "link", concurrent_link)
    with pytest.raises(SystemExit):
        mask(source)
    assert sidecar.read_text() == "concurrent recovery vault"
    assert source.read_text() == "fixture@example.test"
    assert not list(tmp_path.glob(".shieldprompt-*"))


def test_symlink_source_is_not_replaced(tmp_path):
    source = tmp_path / "source"
    source.write_text("fixture@example.test")
    alias = tmp_path / "alias"
    alias.symlink_to(source)
    with pytest.raises(SystemExit):
        mask(alias)
    assert alias.is_symlink()
    assert source.read_text() == "fixture@example.test"
