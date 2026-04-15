"""Local PII-masking proxy for the Anthropic API.

You talk to this script. It masks PII locally with ShieldPrompt, sends the
masked prompt to Claude, then unmasks the reply before printing it. The
Anthropic API only ever sees tokens like [PERSON_1] and [PHONE_NUMBER_1].

Setup:
    pip install -e .          # from repo root, installs shieldprompt
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-ant-...

Run:
    python examples/proxy_chat.py
"""

from __future__ import annotations

import os
import sys

from anthropic import Anthropic

from shieldprompt import Shield

MODEL = os.environ.get("SHIELDPROMPT_MODEL", "claude-opus-4-5")
SYSTEM = (
    "You are a helpful assistant. The user's message may contain placeholder "
    "tokens like [PERSON_1], [EMAIL_ADDRESS_1], [PHONE_NUMBER_1]. Treat each "
    "token as a stable opaque identifier for a real value you cannot see. "
    "Preserve the exact token spelling in your reply so it can be restored."
)


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: set ANTHROPIC_API_KEY", file=sys.stderr)
        sys.exit(1)

    shield = Shield(use_ner=False)
    client = Anthropic()
    history: list[dict] = []

    print(f"shieldprompt proxy chat ({MODEL}) — Ctrl-C to exit\n")
    while True:
        try:
            user_msg = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not user_msg:
            continue

        masked_in = shield.mask(user_msg)
        history.append({"role": "user", "content": masked_in})

        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM,
            messages=history,
        )
        masked_out = resp.content[0].text
        history.append({"role": "assistant", "content": masked_out})

        print(f"\nclaude> {shield.unmask(masked_out)}\n")

        if shield.vault.mappings:
            print(
                f"  [vault holds {len(shield.vault.mappings)} masked value(s) "
                "— never sent to the API]\n"
            )


if __name__ == "__main__":
    main()
