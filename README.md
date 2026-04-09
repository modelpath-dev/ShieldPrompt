# ShieldPrompt

Privacy bridge for LLMs. Mask PII before it leaves your machine, unmask it when the response comes back.

## Install

```bash
pip install shieldprompt
```

For NER-based name/org/location detection:

```bash
pip install shieldprompt[ner]
```

## Quick Start

```python
from shieldprompt import mask_pii

@mask_pii(entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"])
def call_llm(prompt: str) -> str:
    # prompt is already sanitized here
    return your_llm_client.generate(prompt)

# Return value has real names restored automatically
result = call_llm("Email john.doe@acme.com about the meeting with Alice")
```

## FastAPI Middleware

```python
from fastapi import FastAPI
from shieldprompt.middleware import ShieldPromptMiddleware

app = FastAPI()
app.add_middleware(ShieldPromptMiddleware, sensitivity="high", exclude_paths=["/health"])
```

## Direct Usage

```python
from shieldprompt import Shield

shield = Shield(entities={"EMAIL_ADDRESS", "PERSON"})
masked = shield.mask("Contact alice@example.com")
# "Contact [EMAIL_ADDRESS_1]"

restored = shield.unmask(masked)
# "Contact alice@example.com"
```
