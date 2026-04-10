# ShieldPrompt

ShieldPrompt is a privacy bridge for LLM workflows.

It masks sensitive values before they leave your app/tooling, and restores them after the model responds.

## What You Get

- Deterministic PII masking with reversible tokens like `[EMAIL_ADDRESS_1]`
- Fast regex detection + optional local NER for contextual entities
- Multiple integration surfaces:
  - Python engine (`Shield`)
  - Decorator (`@mask_pii`)
  - CLI (`shieldprompt`, `pii`, `retrace`)
  - FastAPI middleware
  - MCP server tools

## 1. Install

### Core package

```bash
pip install shieldprompt
```

### Optional extras

```bash
# Local NER support
pip install "shieldprompt[ner]"

# FastAPI/Starlette middleware support
pip install "shieldprompt[fastapi]"

# Everything
pip install "shieldprompt[all]"
```

## 2. Quickest Start (Terminal)

### Mask text

```bash
pii "Email alice@example.com and call +1-415-555-1234"
```

Expected output shape:

```text
Email [EMAIL_ADDRESS_1] and call [PHONE_NUMBER_1]
```

### Restore text

```bash
retrace "Email [EMAIL_ADDRESS_1]" --vault vault.json
```

### File roundtrip (recommended for practical use)

```bash
# 1) Mask in-place and auto-save vault sidecar
pii --file secrets.txt --in-place --no-ner

# 2) Later restore from sidecar vault automatically
retrace --file secrets.txt --in-place
```

This creates/uses:

- `secrets.txt.shieldprompt.vault.json`

## 3. Python API

```python
from shieldprompt import Shield
from shieldprompt.entities import EntityType

shield = Shield(
    entities={EntityType.EMAIL_ADDRESS, EntityType.PHONE_NUMBER},
    use_ner=False,
)

text = "Email alice@example.com or call +1-415-555-1234"
masked = shield.mask(text)
print(masked)
# Email [EMAIL_ADDRESS_1] or call [PHONE_NUMBER_1]

restored = shield.unmask(masked)
print(restored)
# Email alice@example.com or call +1-415-555-1234
```

## 4. Decorator for LLM Calls

```python
from shieldprompt import mask_pii

@mask_pii(entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"])
def call_llm(prompt: str) -> str:
    # prompt is masked before this function executes
    masked_response = your_llm_client.generate(prompt)
    return masked_response

# return value is unmasked automatically
result = call_llm("Email john.doe@acme.com about the meeting with Alice")
print(result)
```

## 5. FastAPI Middleware

```python
from fastapi import FastAPI
from shieldprompt.middleware import ShieldPromptMiddleware

app = FastAPI()
app.add_middleware(
    ShieldPromptMiddleware,
    sensitivity="high",            # low | medium | high
    exclude_paths=["/health"],
    use_ner=False,
)
```

What it does:

- Masks request JSON string fields before your route handler runs
- Unmasks response text before returning to caller
- Keeps per-request vault mapping

## 6. MCP Wiring (for Claude Code / other MCP clients)

Run server:

```bash
python -m shieldprompt.mcp_server
```

Create `.claude/settings.json`:

```json
{
  "mcpServers": {
    "shieldprompt": {
      "command": "python",
      "args": ["-m", "shieldprompt.mcp_server"]
    }
  }
}
```

Available MCP tools:

- `shield_mask`
- `shield_unmask`
- `shield_inspect`
- `shield_vault`
- `shield_clear`

Important: MCP registration alone does not force masking.
Your agent prompt/policy must call `shield_mask` before external LLM calls and `shield_unmask` before user output.

## 7. CLI Reference

After install, available commands:

- `shieldprompt mask`
- `shieldprompt unmask`
- `shieldprompt inspect`
- `shieldprompt map`
- `shieldprompt pii` (alias of `mask`)
- `shieldprompt retrace` / `shieldprompt restore` (alias of `unmask`)
- Direct short scripts: `pii`, `retrace`

Examples:

```bash
# Mask text
shieldprompt mask "My email is alice@example.com"
shieldprompt pii "My email is alice@example.com"
pii "My email is alice@example.com"

# Mask from stdin
echo "Call me at +1-415-555-1234" | pii

# Mask file and save vault explicitly
shieldprompt mask --file input.txt --save-vault vault.json

# Restore with explicit vault
retrace "[EMAIL_ADDRESS_1]" --vault vault.json

# Show mappings
shieldprompt map --file secrets.txt --json

# Inspect detections
shieldprompt inspect "Alice from Acme can be reached at alice@acme.com"
```

## 8. Supported Entities

Regex-based:

- `EMAIL_ADDRESS`
- `PHONE_NUMBER`
- `CREDIT_CARD`
- `SSN`
- `IP_ADDRESS`
- `IBAN`
- `DATE_OF_BIRTH`
- `URL`
- `AWS_KEY`
- `API_KEY`

NER-based (optional):

- `PERSON`
- `ORGANIZATION`
- `LOCATION`
- `DATE`
- `MONEY`

## 9. Development

```bash
# Editable install with dev deps
pip install -e ".[dev]"

# Run tests
pytest
```

## 10. Release and Publish (Maintainers)

### A) Publish code to GitHub

```bash
git add README.md pyproject.toml src/shieldprompt/cli.py tests/test_cli_roundtrip.py src/shieldprompt/__init__.py
git commit -m "docs: improve onboarding and MCP wiring guide"
git push origin main
```

### B) Publish package to PyPI

1. Bump version in:

- `pyproject.toml`
- `src/shieldprompt/__init__.py`

2. Build distributions:

```bash
python -m build
```

3. Upload to PyPI:

```bash
python -m pip install --upgrade twine
python -m twine upload dist/*
```

If you use API token auth, set:

```bash
export TWINE_USERNAME=__token__
export TWINE_PASSWORD=<your_pypi_api_token>
```

## License

MIT
