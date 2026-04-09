# ShieldPrompt

ShieldPrompt is a privacy layer for LLM apps.

It masks sensitive data before it leaves your app and restores it in the final response.

## Why ShieldPrompt

- Reduce accidental PII leakage to third-party LLM APIs
- Keep application logic simple with drop-in masking/unmasking
- Use deterministic regex detection and optional NER for contextual entities
- Integrate at multiple layers: decorator, engine, CLI, FastAPI middleware, MCP server

## Installation

### Core package

```bash
pip install shieldprompt
```

### With NER support

```bash
pip install "shieldprompt[ner]"
```

### FastAPI/Starlette middleware support

```bash
pip install "shieldprompt[fastapi]"
```

### Everything

```bash
pip install "shieldprompt[all]"
```

## Quick Start (Decorator)

```python
from shieldprompt import mask_pii

@mask_pii(entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"])
def call_llm(prompt: str) -> str:
    # `prompt` is masked before this function runs
    masked_response = your_llm_client.generate(prompt)
    return masked_response

# Return value is automatically unmasked
result = call_llm("Email john.doe@acme.com about the meeting with Alice.")
print(result)
```

## Direct Engine Usage

```python
from shieldprompt import Shield

shield = Shield(entities={"EMAIL_ADDRESS", "PERSON"})

text = "Contact Alice at alice@example.com"
masked = shield.mask(text)
print(masked)
# Contact [PERSON_1] at [EMAIL_ADDRESS_1]

restored = shield.unmask(masked)
print(restored)
# Contact Alice at alice@example.com
```

## FastAPI Middleware

```python
from fastapi import FastAPI
from shieldprompt.middleware import ShieldPromptMiddleware

app = FastAPI()
app.add_middleware(
    ShieldPromptMiddleware,
    sensitivity="high",            # low | medium | high
    exclude_paths=["/health"],     # paths to skip
)
```

What it does:
- Masks request JSON body string fields before your route handlers run
- Unmasks response text before it is sent to the client
- Maintains per-request vault mapping

## CLI Usage

After installation, use the `shieldprompt` command.

### Mask text

```bash
shieldprompt mask "My email is alice@example.com"
```

### Mask from stdin

```bash
echo "Call me at +1-415-555-1234" | shieldprompt mask
```

### Mask from file and save vault

```bash
shieldprompt mask --file input.txt --save-vault vault.json
```

### Unmask with vault

```bash
shieldprompt unmask "[EMAIL_ADDRESS_1]" --vault vault.json
```

### Inspect detected entities

```bash
shieldprompt inspect "Alice from Acme can be reached at alice@acme.com"
```

## MCP Server Integration

Run the MCP server:

```bash
python -m shieldprompt.mcp_server
```

Example Claude Code config (`.claude/settings.json`):

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

## Supported Entities

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

## Development

### Run tests

```bash
pytest
```

### Local editable install

```bash
pip install -e ".[dev]"
```

## License

MIT
