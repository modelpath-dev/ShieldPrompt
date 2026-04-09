"""ShieldPrompt CLI — mask/unmask PII from the terminal.

Usage:
    shieldprompt mask "My email is alice@example.com"
    echo "some text" | shieldprompt mask
    shieldprompt unmask "[EMAIL_ADDRESS_1]" --vault vault.json
    shieldprompt mask --file input.txt --save-vault vault.json
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
    vault = Vault()
    data = json.loads(Path(path).read_text())
    for token, real in data.items():
        entity_type = token.split("_")[0].lstrip("[")
        vault._token_to_real[token] = real
        vault._real_to_token[real] = token
    return vault


def _save_vault(vault: Vault, path: str) -> None:
    """Save vault mappings to a JSON file."""
    Path(path).write_text(json.dumps(vault.mappings, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="shieldprompt",
        description="Mask or unmask PII in text.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- mask ---
    mask_p = sub.add_parser("mask", help="Mask PII in text")
    mask_p.add_argument("text", nargs="?", help="Text to mask (or pipe via stdin)")
    mask_p.add_argument("--file", "-f", help="Read text from file")
    mask_p.add_argument(
        "--entities", "-e", nargs="+",
        help="Entity types to detect (e.g. EMAIL_ADDRESS PERSON)",
    )
    mask_p.add_argument(
        "--save-vault", "-s", help="Save vault mappings to JSON file"
    )
    mask_p.add_argument("--no-ner", action="store_true", help="Disable NER model")

    # --- unmask ---
    unmask_p = sub.add_parser("unmask", help="Unmask tokens back to real values")
    unmask_p.add_argument("text", nargs="?", help="Text to unmask (or pipe via stdin)")
    unmask_p.add_argument("--file", "-f", help="Read text from file")
    unmask_p.add_argument(
        "--vault", "-v", required=True, help="Path to vault JSON file"
    )

    # --- inspect ---
    inspect_p = sub.add_parser("inspect", help="Show what PII would be detected")
    inspect_p.add_argument("text", nargs="?", help="Text to inspect (or stdin)")
    inspect_p.add_argument("--file", "-f", help="Read text from file")
    inspect_p.add_argument("--no-ner", action="store_true", help="Disable NER model")

    args = parser.parse_args()

    if args.command == "mask":
        _cmd_mask(args)
    elif args.command == "unmask":
        _cmd_unmask(args)
    elif args.command == "inspect":
        _cmd_inspect(args)


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
    text = _get_text(args)
    entities = {EntityType(e) for e in args.entities} if args.entities else None
    vault = Vault()
    shield = Shield(
        entities=entities,
        use_ner=not args.no_ner,
        vault=vault,
    )
    masked = shield.mask(text)
    print(masked)

    if args.save_vault:
        _save_vault(vault, args.save_vault)
        print(f"Vault saved to {args.save_vault}", file=sys.stderr)


def _cmd_unmask(args) -> None:
    text = _get_text(args)
    vault = _load_vault(args.vault)
    print(vault.restore_text(text))


def _cmd_inspect(args) -> None:
    text = _get_text(args)
    from .detector.hybrid import HybridDetector

    detector = HybridDetector()
    detections = detector.detect(text)
    if not detections:
        print("No PII detected.")
        return
    for d in detections:
        print(f"  {d.entity_type:20s}  {d.value!r:30s}  (pos {d.start}-{d.end}, score={d.score:.2f})")


if __name__ == "__main__":
    main()
