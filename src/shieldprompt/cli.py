"""ShieldPrompt CLI — mask/unmask PII from the terminal.

Usage:
    shieldprompt mask "My email is alice@example.com"
    shieldprompt pii "My email is alice@example.com"
    echo "some text" | shieldprompt mask
    echo "some text" | pii
    shieldprompt unmask "[EMAIL_ADDRESS_1]" --vault vault.json
    retrace "[EMAIL_ADDRESS_1]" --vault vault.json
    shieldprompt mask --file input.txt --save-vault vault.json
    shieldprompt mask --file secrets.txt --in-place --no-ner
    shieldprompt unmask --file secrets.txt --in-place
    shieldprompt map --file secrets.txt
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .entities import EntityType
from .shield import Shield
from .vault import Vault


def _load_vault(path: str) -> Vault:
    """Load vault mappings from a JSON file."""
    data = json.loads(Path(path).read_text())
    return Vault.from_dict(data)


def _save_vault(vault: Vault, path: str) -> None:
    """Save vault mappings to a JSON file with owner-only permissions (0600)."""
    p = Path(path)
    p.write_text(json.dumps(vault.to_dict(), indent=2))
    try:
        p.chmod(0o600)
    except OSError:
        # chmod isn't meaningful on every platform (e.g. Windows); ignore.
        pass


def _default_vault_path(file_path: str) -> str:
    """Default sidecar vault path for a source file."""
    return f"{file_path}.shieldprompt.vault.json"


def _resolve_vault_path(file_path: str | None, explicit_path: str | None) -> str:
    """Resolve vault path from an explicit argument or a file sidecar."""
    if explicit_path:
        return explicit_path
    if file_path:
        return _default_vault_path(file_path)
    print("Error: provide --vault when not using --file", file=sys.stderr)
    sys.exit(1)


def _build_parser(prog: str = "shieldprompt") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Mask or unmask PII in text.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- mask ---
    mask_p = sub.add_parser("mask", aliases=["pii"], help="Mask PII in text")
    mask_p.add_argument("text", nargs="?", help="Text to mask (or pipe via stdin)")
    mask_p.add_argument("--file", "-f", help="Read text from file")
    mask_p.add_argument(
        "--entities", "-e", nargs="+",
        help="Entity types to detect (e.g. EMAIL_ADDRESS PERSON)",
    )
    mask_p.add_argument(
        "--save-vault", "-s", help="Save vault mappings to JSON file"
    )
    mask_p.add_argument(
        "--in-place",
        "-i",
        action="store_true",
        help="When used with --file, overwrite the file with masked text",
    )
    mask_p.add_argument("--no-ner", action="store_true", help="Disable NER model")

    # --- unmask ---
    unmask_p = sub.add_parser(
        "unmask",
        aliases=["retrace", "restore"],
        help="Unmask tokens back to real values",
    )
    unmask_p.add_argument("text", nargs="?", help="Text to unmask (or pipe via stdin)")
    unmask_p.add_argument("--file", "-f", help="Read text from file")
    unmask_p.add_argument("--vault", "-v", help="Path to vault JSON file")
    unmask_p.add_argument(
        "--in-place",
        "-i",
        action="store_true",
        help="When used with --file, overwrite the file with unmasked text",
    )

    # --- inspect ---
    inspect_p = sub.add_parser("inspect", help="Show what PII would be detected")
    inspect_p.add_argument("text", nargs="?", help="Text to inspect (or stdin)")
    inspect_p.add_argument("--file", "-f", help="Read text from file")
    inspect_p.add_argument("--no-ner", action="store_true", help="Disable NER model")

    # --- map ---
    map_p = sub.add_parser(
        "map",
        help="Show token->original mappings from a vault file",
    )
    map_p.add_argument("--file", "-f", help="Original file path (uses default sidecar vault)")
    map_p.add_argument("--vault", "-v", help="Path to vault JSON file")
    map_p.add_argument("--json", action="store_true", help="Print mappings as JSON")
    return parser


def main(argv: list[str] | None = None, prog: str = "shieldprompt") -> None:
    parser = _build_parser(prog=prog)
    args = parser.parse_args(argv)
    command = {
        "pii": "mask",
        "retrace": "unmask",
        "restore": "unmask",
    }.get(args.command, args.command)

    if command == "mask":
        _cmd_mask(args)
    elif command == "unmask":
        _cmd_unmask(args)
    elif command == "inspect":
        _cmd_inspect(args)
    elif command == "map":
        _cmd_map(args)


def _get_text(args) -> str:
    """Get input text from args, file, or stdin."""
    if args.file:
        return Path(args.file).read_text()
    if args.text:
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    print("Error: provide text as argument, --file, or pipe via stdin", file=sys.stderr)
    sys.exit(1)


def _cmd_mask(args) -> None:
    if args.in_place and not args.file:
        print("Error: --in-place requires --file", file=sys.stderr)
        sys.exit(1)

    text = _get_text(args)
    entities = {EntityType(e) for e in args.entities} if args.entities else None
    vault = Vault()
    shield = Shield(
        entities=entities,
        use_ner=not args.no_ner,
        vault=vault,
    )
    masked = shield.mask(text)
    if args.in_place:
        Path(args.file).write_text(masked)
    else:
        print(masked)

    should_save_vault = bool(args.save_vault or args.in_place)
    if should_save_vault:
        vault_path = args.save_vault or _default_vault_path(args.file)
        _save_vault(vault, vault_path)
        if args.in_place:
            print(f"Masked file in-place: {args.file}", file=sys.stderr)
        print(f"Vault saved to {vault_path}", file=sys.stderr)


def _cmd_unmask(args) -> None:
    if args.in_place and not args.file:
        print("Error: --in-place requires --file", file=sys.stderr)
        sys.exit(1)

    text = _get_text(args)
    vault_path = _resolve_vault_path(args.file, args.vault)
    vault = _load_vault(vault_path)
    unmasked = vault.restore_text(text)

    if args.in_place:
        Path(args.file).write_text(unmasked)
        print(f"Unmasked file in-place: {args.file}", file=sys.stderr)
    else:
        print(unmasked)


def _cmd_inspect(args) -> None:
    text = _get_text(args)
    from .detector.hybrid import HybridDetector
    from .entities import REGEX_ENTITIES

    entities = REGEX_ENTITIES if args.no_ner else None
    detector = HybridDetector(entities=entities)
    detections = detector.detect(text)
    if not detections:
        print("No PII detected.")
        return
    for d in detections:
        print(f"  {d.entity_type:20s}  {d.value!r:30s}  (pos {d.start}-{d.end}, score={d.score:.2f})")


def _cmd_map(args) -> None:
    vault_path = _resolve_vault_path(args.file, args.vault)
    mappings = _load_vault(vault_path).mappings
    if args.json:
        print(json.dumps(mappings, indent=2))
        return
    if not mappings:
        print("No mappings found.")
        return
    for token, real in mappings.items():
        print(f"{token} -> {real}")


_MASK_ALIASES = {"mask", "pii"}
_UNMASK_ALIASES = {"unmask", "retrace", "restore"}


def pii_main() -> None:
    """Entry point for the short `pii` command."""
    args = sys.argv[1:]
    # Tolerate users who write `pii mask ...` — strip the redundant subcommand.
    if args and args[0] in _MASK_ALIASES:
        args = args[1:]
    main(argv=["mask", *args], prog="pii")


def retrace_main() -> None:
    """Entry point for the short `retrace` command."""
    args = sys.argv[1:]
    if args and args[0] in _UNMASK_ALIASES:
        args = args[1:]
    main(argv=["unmask", *args], prog="retrace")


if __name__ == "__main__":
    main()
