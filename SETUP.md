# ShieldPrompt — Setup & Usage

This guide walks you through installing ShieldPrompt, wiring it into
Claude Code, and using it from the CLI or Python.

**Contents**

1. [Setup Claude Code](#1-setup-claude-code)
2. [Install the package](#2-install-the-package)
3. [CLI usage](#3-cli-usage)
4. [Python library](#4-python-library)
5. [FastAPI middleware](#5-fastapi-middleware)
6. [What ShieldPrompt detects](#6-what-shieldprompt-detects)
7. [FAQ & gotchas](#7-faq--gotchas)

---

## 1. Setup Claude Code

ShieldPrompt includes an MCP (Model Context Protocol) server so Claude
Code can mask PII in any conversation, automatically.

### Prerequisites


| What                | Check with          | If missing                                               |
| ------------------- | ------------------- | -------------------------------------------------------- |
| Python 3.9 or newer | `python3 --version` | Install from https://www.python.org/downloads            |
| Claude Code CLI     | `claude --version`  | Install from https://docs.claude.com/en/docs/claude-code |

### Step 1 — Install ShieldPrompt

<p align="center">
  <a href="https://pypi.org/project/shieldprompt/">
    <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=26&duration=2500&pause=800&color=36BCF7&center=true&vCenter=true&width=520&height=60&lines=%24+pip+install+shieldprompt" alt="pip install shieldprompt" />
  </a>
</p>

```bash
pip install shieldprompt
```

The first run will automatically download the spaCy `en_core_web_sm`
model (~12 MB). No separate download step needed.

### Step 2 — Register the MCP server with Claude Code

Run this **one command** — it writes the required JSON into Claude Code's
config for you, no manual editing:

```bash
claude mcp add shieldprompt -- python -m shieldprompt.mcp_server
```

That's it. Verify it was added:

```bash
claude mcp list
```

You should see `shieldprompt` in the output.

> **Prefer to edit JSON yourself?** Add this block to your Claude Code
> settings (`~/.claude.json` for user-scope, or `.mcp.json` in your project
> for project-scope):
>
> ```json
> {
>   "mcpServers": {
>     "shieldprompt": {
>       "command": "python",
>       "args": ["-m", "shieldprompt.mcp_server"]
>     }
>   }
> }
> ```

### Step 3 — Restart Claude Code

Close and reopen your Claude Code session. The ShieldPrompt tools will
now be available: `shield_mask`, `shield_unmask`, `shield_inspect`,
`shield_vault`, `shield_clear`.

### Step 4 — Try it

In Claude Code, type:

> Mask the PII in this sentence: "Email alice@example.com and call
> +1-415-555-1234, my name is Chandan Kumar."

Claude will invoke `shield_mask` and reply with:

```
Email [EMAIL_ADDRESS_1] and call [PHONE_NUMBER_1], my name is [PERSON_1].
```

Now you can send that masked text to any external service safely. Ask
Claude to `shield_unmask` the reply when you're done to get the real
values back.

Or if you want this in complete session. Just write

~~~
Use shield_mask for this complete session
~~~

This will work for enitre session. You write your prompt normally as you do.
Your ShieldPrompt will handle everything.

**You're live.** ShieldPrompt is active in Claude Code.

---

## 2. Install the package

```bash
pip install shieldprompt
```

Optional extras (install only if you need them):


| Extra     | Command                               | What it adds                                                       |
| --------- | ------------------------------------- | ------------------------------------------------------------------ |
| `ner`     | `pip install "shieldprompt[ner]"`     | HuggingFace transformer NER as a fallback/alternative to Presidio. |
| `fastapi` | `pip install "shieldprompt[fastapi]"` | The FastAPI / Starlette middleware.                                |
| `all`     | `pip install "shieldprompt[all]"`     | Everything.                                                        |

The core install already includes Presidio + spaCy, so name/organization/
location detection works out of the box.

---

## 3. CLI usage

Three commands are installed: `shieldprompt` (full), `pii` (shortcut for
masking), `retrace` (shortcut for unmasking).

```bash
# --- masking ---
pii "My email is alice@example.com"                    # one-liner
echo "Call +1-415-555-1234" | pii                      # from stdin
pii --file notes.txt --in-place                        # file in place (+ sidecar vault)
pii "text" --save-vault my_vault.json                  # explicit vault path
pii "text" --entities EMAIL_ADDRESS CREDIT_CARD        # only these types
pii "text" --no-ner                                    # regex-only, skip Presidio

# --- unmasking ---
retrace "Hi [EMAIL_ADDRESS_1]" --vault my_vault.json   # explicit vault
retrace --file notes.txt --in-place                    # uses sidecar automatically

# --- inspect what would be detected (no masking) ---
shieldprompt inspect "Alice works at alice@acme.com"

# --- dump a vault file for debugging ---
shieldprompt map --vault my_vault.json
shieldprompt map --file notes.txt --json
```

**Example: mask a file and unmask it back.**

```bash
# starting file
echo "Email alice@example.com about the invoice." > notes.txt

# mask in place (writes notes.txt + notes.txt.shieldprompt.vault.json)
pii --file notes.txt --in-place

cat notes.txt
# → Email [EMAIL_ADDRESS_1] about the invoice.

# unmask using the sidecar vault automatically
retrace --file notes.txt --in-place

cat notes.txt
# → Email alice@example.com about the invoice.
```

Vault files are written with `0600` permissions (owner-only). **Treat
them like password files** — anyone who reads the vault can re-identify
every redaction.

---

## 4. Python library

```python
from shieldprompt import Shield

shield = Shield()

masked = shield.mask("Email alice@example.com or call +1-415-555-1234")
# → "Email [EMAIL_ADDRESS_1] or call [PHONE_NUMBER_1]"

original = shield.unmask(masked)
# → "Email alice@example.com or call +1-415-555-1234"
```

Pick specific entity types:

```python
from shieldprompt import Shield
from shieldprompt.entities import EntityType

shield = Shield(entities={EntityType.EMAIL_ADDRESS, EntityType.CREDIT_CARD})
```

Wrap an LLM call with the decorator:

```python
from shieldprompt import mask_pii
from openai import OpenAI

client = OpenAI()

@mask_pii(entities=["EMAIL_ADDRESS", "PHONE_NUMBER", "PERSON"])
def ask_llm(prompt: str) -> str:
    reply = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )
    return reply.choices[0].message.content

answer = ask_llm("Draft a reply to alice@example.com about Friday.")
# `answer` still mentions alice@example.com — the model never saw it.
```

Works with `async def` too — the decorator detects sync vs async
automatically.

---

## 5. FastAPI middleware

```bash
pip install "shieldprompt[fastapi]"
```

```python
from fastapi import FastAPI
from shieldprompt.middleware import ShieldPromptMiddleware

app = FastAPI()
app.add_middleware(
    ShieldPromptMiddleware,
    sensitivity="high",          # low | medium | high
    exclude_paths=["/health"],
)

@app.post("/chat")
async def chat(payload: dict):
    # payload["prompt"] is already masked here
    reply = call_your_llm(payload["prompt"])
    return {"response": reply}
    # the JSON response is unmasked before the client sees it
```

Each request gets its own vault, so data never leaks across users.

---

## 6. What ShieldPrompt detects

**Regex-based (fast, deterministic, always on):**

- `EMAIL_ADDRESS`
- `PHONE_NUMBER`
- `CREDIT_CARD` (Luhn-validated)
- `SSN`
- `IP_ADDRESS`
- `IBAN`
- `URL`
- `AWS_KEY`
- `API_KEY` (OpenAI, GitHub tokens)

**NER-based (Presidio + spaCy, contextual):**

- `PERSON`
- `ORGANIZATION`
- `LOCATION`
- `DATE`
- `MONEY`

---

## 7. FAQ & gotchas

**Q: Is the vault safe?**
The vault is plaintext JSON on your disk. ShieldPrompt writes it with
`0600` permissions, but anyone with file access can re-identify every
redaction. Never commit it to git, never send it to the LLM, clean it up
when you're done.

**Q: Do placeholder numbers stay consistent across runs?**
No. Each `Shield` instance starts counting from 1. Always unmask with the
vault produced by the same masking run — don't stitch vaults from
different processes together.

**Q: Will the LLM get confused by placeholders?**
Modern models handle `[EMAIL_ADDRESS_1]`-style tokens well. For best
results add a system prompt hint: *"Placeholders like `[EMAIL_ADDRESS_1]`
refer to real values; keep them unchanged in your response."*

**Q: What if the model hallucinates a placeholder I never gave it?**
That placeholder isn't in the vault, so `unmask` leaves it as text.
Nothing crashes — but your user will see a literal `[EMAIL_ADDRESS_99]`.
Worth post-processing if it matters.

**Q: Does it slow things down?**
Regex is microseconds per KB. Presidio + spaCy loads once (a couple of
seconds) then runs fast. Network calls to the LLM dwarf both.
