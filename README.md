# ShieldPrompt

**Stop leaking personal data to LLMs.**

<p align="center">
  <a href="https://pypi.org/project/shieldprompt/">
    <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=26&duration=2500&pause=800&color=36BCF7&center=true&vCenter=true&width=520&height=60&lines=%24+pip+install+shieldprompt" alt="pip install shieldprompt" />
  </a>
</p>

ShieldPrompt sits between your app and any Large Language Model (ChatGPT,
Claude, Gemini, a local model — doesn't matter which). Before your text
leaves the machine, it swaps real emails, phone numbers, names, credit
cards, and other sensitive values for reversible placeholders. When the
model's answer comes back, the placeholders are swapped back so your users
still see the real values.

**The model never sees the real data. Your users never see placeholders.**

---

## How it works

```
  Your text:         "Email alice@example.com about the invoice."
                                ↓ ShieldPrompt masks
  Sent to the LLM:   "Email [EMAIL_ADDRESS_1] about the invoice."
                                ↓ LLM answers
  Model reply:       "I'll draft an email to [EMAIL_ADDRESS_1]."
                                ↓ ShieldPrompt unmasks
  User sees:         "I'll draft an email to alice@example.com."
```

Under the hood:

1. **Detection** — a hybrid engine combines deterministic regex patterns
   (emails, phones, credit cards with Luhn validation, SSNs, IPs, IBANs,
   URLs, AWS/API keys) with Microsoft Presidio + spaCy NER for
   contextual entities (people, organizations, locations).
2. **Masking** — each detected value is stored in an in-memory vault and
   replaced with a stable token like `[PERSON_1]` or `[EMAIL_ADDRESS_2]`.
3. **Unmasking** — after the LLM responds, tokens are mapped back to the
   real values using the same vault. The vault is scoped to the request
   (or session) so data never leaks between users.

ShieldPrompt ships as:

- a **Python library** (`Shield`, `@mask_pii` decorator),
- a **FastAPI middleware** for automatic protection of chat endpoints,
- a **CLI** (`pii`, `retrace`, `shieldprompt`) for one-off file masking,
- an **MCP server** for Claude Code, Cursor, and other MCP-aware tools.

---

## Getting started

See **[SETUP.md](SETUP.md)** for installation, Claude Code integration, CLI
usage, the Python API, and troubleshooting.

## Contributing

See **[CONTRIBUTING.md](CONTRIBUTING.md)**. All changes land through pull
requests reviewed by the project owner.

## License

MIT
