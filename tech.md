# ShieldPrompt - Technical Deep Dive

A complete line-by-line breakdown of how ShieldPrompt works, what each piece does, and how they connect.

---

## Table of Contents

1. [What is ShieldPrompt?](#what-is-shieldprompt)
2. [Architecture Flowchart](#architecture-flowchart)
3. [File Structure](#file-structure)
4. [Module-by-Module Breakdown](#module-by-module-breakdown)
   - [entities.py - PII Type Definitions](#1-entitiespy---pii-type-definitions)
   - [vault.py - Token Storage Engine](#2-vaultpy---token-storage-engine)
   - [detector/regex_engine.py - Pattern Matching](#3-detectorregex_enginepy---pattern-matching)
   - [detector/ner_engine.py - AI-Based Detection](#4-detectorner_enginepy---ai-based-detection)
   - [detector/hybrid.py - Combined Detection](#5-detectorhybridpy---combined-detection)
   - [shield.py - Core Engine](#6-shieldpy---core-engine)
   - [decorator.py - Function Wrapper](#7-decoratorpy---function-wrapper)
   - [middleware.py - FastAPI Integration](#8-middlewarepy---fastapi-integration)
   - [cli.py - Command Line Tool](#9-clipy---command-line-tool)
   - [mcp_server.py - Claude Code Integration](#10-mcp_serverpy---claude-code-integration)
   - [__init__.py - Package Exports](#11-__init__py---package-exports)
   - [__main__.py - Module Runner](#12-__main__py---module-runner)
5. [Data Flow Diagrams](#data-flow-diagrams)
6. [Key Design Patterns](#key-design-patterns)

---

## What is ShieldPrompt?

ShieldPrompt is a privacy library that acts as a **bridge between your app and LLMs**. It:

1. **Detects** PII (emails, phone numbers, names, SSNs, etc.) in text
2. **Replaces** each PII with a safe token like `[EMAIL_ADDRESS_1]`
3. **Sends** the sanitized text to the LLM
4. **Restores** the original values in the LLM's response

Your sensitive data never leaves your machine.

---

## Architecture Flowchart

```
                         SHIELDPROMPT ARCHITECTURE
    ================================================================

    User Input (contains PII)
         |
         v
    +------------------+
    |   ENTRY POINTS   |    <-- How users interact with ShieldPrompt
    |  (pick one)      |
    +------------------+
    |  - Shield API    |    Direct Python: shield.mask(text)
    |  - @mask_pii     |    Decorator on functions
    |  - Middleware     |    FastAPI auto-shielding
    |  - CLI           |    Terminal: shieldprompt mask "..."
    |  - MCP Server    |    Claude Code integration
    +--------+---------+
             |
             v
    +------------------+
    |   SHIELD ENGINE   |    shield.py - Orchestrates everything
    |   (shield.py)     |
    +--------+---------+
             |
             v
    +------------------+
    |   DETECTION       |    Finds PII in text
    +------------------+
    |                  |
    v                  v
  +--------+    +--------+
  | Regex  |    |  NER   |    regex_engine.py / ner_engine.py
  | Engine |    | Engine |
  +--------+    +--------+
  | Emails |    | Names  |
  | Phones |    | Orgs   |
  | SSNs   |    | Places |
  | Cards  |    | Dates  |
  | IPs    |    | Money  |
  | URLs   |    +---+----+
  | Keys   |        |
  +---+----+        |
      |             |
      v             v
    +------------------+
    |  HYBRID MERGER   |    hybrid.py - Combines both results
    |  (hybrid.py)     |    Prefers regex for overlaps
    +--------+---------+
             |
             | List of Detection objects
             v
    +------------------+
    |   VAULT           |    vault.py - The token<->value map
    |   (vault.py)      |
    +------------------+
    | store("alice@     |
    |   example.com")   |
    |   --> returns     |
    |   [EMAIL_ADDRESS_1]|
    +--------+---------+
             |
             v
    +------------------+
    |  MASKED OUTPUT    |    PII replaced with tokens
    +------------------+
    | "Email            |
    | [EMAIL_ADDRESS_1] |
    | about meeting     |
    | with [PERSON_1]"  |
    +--------+---------+
             |
             v
       Send to LLM safely
             |
             v
    +------------------+
    |  LLM RESPONSE     |    LLM responds using tokens
    +------------------+
    | "Sure, I'll email |
    | [EMAIL_ADDRESS_1] |
    | to notify         |
    | [PERSON_1]"       |
    +--------+---------+
             |
             v
    +------------------+
    |  UNMASK (vault)   |    vault.restore_text()
    +------------------+
    | Replaces tokens   |
    | with originals    |
    +--------+---------+
             |
             v
    +------------------+
    |  FINAL OUTPUT     |    Real values restored
    +------------------+
    | "Sure, I'll email |
    | alice@example.com |
    | to notify Alice"  |
    +------------------+
```

### Decorator Flow (Simplified)

```
    @mask_pii()
    def call_llm(prompt):          User calls call_llm("Email alice@example.com")
        return llm.generate(prompt)                    |
                                                       v
                                          +------------------------+
                                          | 1. Create Shield+Vault |
                                          | 2. Set context var     |
                                          | 3. Mask "prompt" arg   |
                                          +----------+-------------+
                                                     |
                                          call_llm("Email [EMAIL_ADDRESS_1]")
                                                     |
                                                     v
                                          +------------------------+
                                          | 4. Original func runs  |
                                          |    with masked input   |
                                          +----------+-------------+
                                                     |
                                          LLM returns "[EMAIL_ADDRESS_1] notified"
                                                     |
                                                     v
                                          +------------------------+
                                          | 5. Unmask response     |
                                          | 6. Reset context       |
                                          +----------+-------------+
                                                     |
                                          Returns "alice@example.com notified"
```

### Middleware Flow (Simplified)

```
    HTTP Request                          HTTP Response
    POST /chat                            200 OK
    {"prompt": "Email alice@..."}         {"reply": "Emailed alice@..."}
         |                                       ^
         v                                       |
    +----------+                           +----------+
    | Read     |                           | Unmask   |
    | request  |                           | response |
    | body     |                           | body     |
    +----+-----+                           +----+-----+
         |                                       ^
         v                                       |
    +----------+                           +----------+
    | JSON     |                           | Buffer   |
    | parse &  |                           | response |
    | mask all |                           | parts    |
    | strings  |                           +----------+
    +----+-----+                                 ^
         |                                       |
         v                                       |
    +----+-----+                           +-----+----+
    | Forward  | ---------> App ---------> | App      |
    | masked   |   (sees only tokens)      | response |
    | request  |                           | (tokens) |
    +----------+                           +----------+
```

---

## File Structure

```
src/shieldprompt/
  __init__.py          Package exports (Shield, Vault, mask_pii, etc.)
  __main__.py          Enables `python -m shieldprompt`
  shield.py            Core masking/unmasking engine
  vault.py             Token <-> real value storage
  entities.py          PII entity type definitions (enum)
  decorator.py         @mask_pii decorator for functions
  middleware.py        FastAPI/Starlette ASGI middleware
  cli.py               Command-line interface (mask/unmask/inspect)
  mcp_server.py        MCP server for Claude Code integration
  detector/
    __init__.py        Exports detectors
    regex_engine.py    Fast pattern matching (emails, phones, etc.)
    ner_engine.py      NLP model detection (names, orgs, etc.)
    hybrid.py          Combines regex + NER results
```

---

## Module-by-Module Breakdown

---

### 1. `entities.py` - PII Type Definitions

**Purpose:** Defines all the types of PII that ShieldPrompt can detect.

```python
# Line 3: Import Python's Enum class for creating named constants
from enum import Enum

# Line 6: EntityType inherits from both str and Enum.
# Inheriting str means each value IS a string (EntityType.EMAIL_ADDRESS == "EMAIL_ADDRESS")
# This makes it easy to serialize to JSON or use in string formatting
class EntityType(str, Enum):
```

**Regex-detected entities (Lines 8-17):**
These are detected by pattern matching — deterministic and fast.

| Entity            | Example                      |
| ----------------- | ---------------------------- |
| `EMAIL_ADDRESS` | alice@example.com            |
| `PHONE_NUMBER`  | (555) 123-4567               |
| `CREDIT_CARD`   | 4111-1111-1111-1111          |
| `SSN`           | 123-45-6789                  |
| `IP_ADDRESS`    | 192.168.1.1                  |
| `IBAN`          | GB29 NWBK 6016 1331 9268 19  |
| `DATE_OF_BIRTH` | (currently no regex pattern) |
| `URL`           | https://example.com          |
| `AWS_KEY`       | AKIAIOSFODNN7EXAMPLE         |
| `API_KEY`       | sk-abc123..., ghp_abc123...  |

**NER-detected entities (Lines 20-24):**
These need an AI model (BERT) because they depend on context, not patterns.

| Entity           | Example               |
| ---------------- | --------------------- |
| `PERSON`       | "Alice", "John Smith" |
| `ORGANIZATION` | "Google", "MIT"       |
| `LOCATION`     | "New York", "France"  |
| `DATE`         | "last Tuesday"        |
| `MONEY`        | "$500"                |

**Sets (Lines 27-58):**

```python
# Line 27-38: REGEX_ENTITIES - set of all pattern-detectable types
REGEX_ENTITIES = {EntityType.EMAIL_ADDRESS, EntityType.PHONE_NUMBER, ...}

# Line 40-46: NER_ENTITIES - set of all NER-detectable types
NER_ENTITIES = {EntityType.PERSON, EntityType.ORGANIZATION, ...}

# Line 48: ALL_ENTITIES - union of both sets (| is set union operator)
ALL_ENTITIES = REGEX_ENTITIES | NER_ENTITIES

# Line 50-58: DEFAULT_ENTITIES - the most common PII types
# Used when the user doesn't specify what to detect
DEFAULT_ENTITIES = {EMAIL_ADDRESS, PHONE_NUMBER, CREDIT_CARD, SSN, PERSON, ORGANIZATION, LOCATION}
```

**Why these defaults?** They cover the most common privacy-sensitive data without requiring every possible type.

---

### 2. `vault.py` - Token Storage Engine

**Purpose:** Maps PII tokens (`[EMAIL_ADDRESS_1]`) to real values (`alice@example.com`). Lives only in memory, never persisted to disk automatically.

```python
# Line 5-6: Two key imports for thread safety
import contextvars   # Python's async-safe thread-local storage
import threading     # For mutual exclusion locks
```

**Context Variable (Lines 10-12):**

```python
# This creates a "context variable" — like a thread-local variable but also works
# with async/await. Each async task or thread gets its own vault automatically.
_vault_var: contextvars.ContextVar[Optional["Vault"]] = contextvars.ContextVar(
    "shieldprompt_vault", default=None
)
```

**Why contextvars?** If you have 100 concurrent API requests in a FastAPI app, each needs its own vault so PII from request A doesn't leak into request B. `contextvars` ensures this automatically.

**Vault Class (Lines 15-63):**

```python
class Vault:
    def __init__(self) -> None:
        # Line 19: token -> real value. E.g., {"[EMAIL_ADDRESS_1]": "alice@example.com"}
        self._token_to_real: dict[str, str] = {}

        # Line 20: Reverse mapping for idempotency. E.g., {"alice@example.com": "[EMAIL_ADDRESS_1]"}
        self._real_to_token: dict[str, str] = {}

        # Line 21: Counts per entity type. E.g., {"EMAIL_ADDRESS": 2, "PERSON": 1}
        self._counters: dict[str, int] = {}

        # Line 22: Thread lock — prevents two threads from creating tokens simultaneously
        self._lock = threading.Lock()
```

**store() method (Lines 24-36) — The core of the vault:**

```python
def store(self, entity_type: str, real_value: str) -> str:
    with self._lock:                           # Acquire lock (thread safety)
        if real_value in self._real_to_token:   # Already seen this value?
            return self._real_to_token[real_value]  # Return same token (idempotent)

        count = self._counters.get(entity_type, 0) + 1  # Increment counter
        self._counters[entity_type] = count              # Save new count
        token = f"[{entity_type}_{count}]"               # Build token string

        self._token_to_real[token] = real_value   # Map token -> real
        self._real_to_token[real_value] = token   # Map real -> token
        return token
```

**Key insight: Idempotency.** If `alice@example.com` appears 5 times in the text, it always maps to `[EMAIL_ADDRESS_1]`. This keeps the masked text consistent.

**restore_text() method (Lines 42-50) — Unmask all tokens in text:**

```python
def restore_text(self, text: str) -> str:
    result = text
    # Sort by token length DESCENDING to avoid partial replacement
    # Without this: [PERSON_1] might be partially replaced before [PERSON_10]
    for token, real in sorted(
        self._token_to_real.items(), key=lambda x: len(x[0]), reverse=True
    ):
        result = result.replace(token, real)
    return result
```

**Why sort by length?** If you have `[PERSON_1]` and `[PERSON_10]`, replacing `[PERSON_1]` first would corrupt `[PERSON_10]` into `<real_value>0]`. Longest-first prevents this.

**Context helper functions (Lines 65-81):**

```python
# get_vault(): Get the vault for THIS context (thread/async task)
# Creates one automatically if none exists
def get_vault() -> Vault:
    vault = _vault_var.get()
    if vault is None:
        vault = Vault()
        _vault_var.set(vault)
    return vault

# set_vault(): Explicitly set a vault, returns a reset token
# The reset token lets you restore the previous vault later
def set_vault(vault: Vault) -> contextvars.Token:
    return _vault_var.set(vault)

# reset_vault(): Restore the vault to what it was before set_vault()
def reset_vault(token: contextvars.Token) -> None:
    _vault_var.reset(token)
```

---

### 3. `detector/regex_engine.py` - Pattern Matching

**Purpose:** Fast, deterministic PII detection using compiled regex patterns.

**Detection dataclass (Lines 12-19):**

```python
@dataclass
class Detection:
    entity_type: str   # E.g., "EMAIL_ADDRESS"
    value: str         # E.g., "alice@example.com"
    start: int         # Start position in text
    end: int           # End position in text
    score: float = 1.0 # Confidence (always 1.0 for regex — it's certain)
```

**Luhn Algorithm (Lines 22-32) — Credit card validation:**

```python
def _luhn_check(number: str) -> bool:
    digits = [int(d) for d in number if d.isdigit()]  # Extract only digits
    if len(digits) < 13:        # Real cards have 13-19 digits
        return False
    odd_digits = digits[-1::-2]   # Every other digit from the right
    even_digits = digits[-2::-2]  # The other digits
    total = sum(odd_digits)
    for d in even_digits:
        total += sum(divmod(d * 2, 10))  # Double, then sum digits if > 9
    return total % 10 == 0  # Valid if divisible by 10
```

**Why Luhn?** Not every 16-digit number is a credit card. The Luhn algorithm is the industry-standard checksum that real credit card numbers satisfy. This prevents false positives like random 16-digit numbers.

**Pattern definitions (Lines 36-105):**

Each pattern is a tuple of `(entity_type, compiled_regex, optional_validator)`:

| Pattern               | Regex Explanation                                                                                                                 |
| --------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **Email**       | `\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b` — word boundary, local part, @, domain, TLD (2+ letters)                  |
| **Phone**       | `(?<!\d)(\+?1[\s-.]?)?((\d{3})[\s-.]?)\d{3}[\s-.]?\d{4}(?!\d)` — optional +1 country code, 3-3-4 digit groups, with separators |
| **Credit Card** | `\b(\d[ -]*?){13,19}\b` — 13-19 digits with optional spaces/dashes, **plus Luhn validation**                             |
| **SSN**         | `\b(?!000                                                                                                                         |
| **IP Address**  | `\b(25[0-5]                                                                                                                       |
| **IBAN**        | `\b[A-Z]{2}\d{2}[\s]?[\dA-Z]{4}...` — country code + check digits + account                                                    |
| **URL**         | `https?://[^\s<>"']{3,}` — http or https followed by non-whitespace chars                                                      |
| **AWS Key**     | `\b(AKIA                                                                                                                          |
| **API Key**     | `\b(sk-[A-Za-z0-9]{20+}                                                                                                           |

**RegexDetector class (Lines 108-135):**

```python
class RegexDetector:
    def __init__(self, entities=None):
        self._entities = entities   # Optional filter: only detect these types

    def detect(self, text: str) -> list[Detection]:
        detections = []
        for entity_type, pattern, validator in _PATTERNS:
            # Skip this pattern if user only wants specific entity types
            if self._entities and entity_type not in self._entities:
                continue

            for match in pattern.finditer(text):  # Find ALL matches
                value = match.group()
                # If there's a validator (e.g., Luhn for credit cards), check it
                if validator and not validator(value):
                    continue
                detections.append(Detection(
                    entity_type=entity_type,
                    value=value,
                    start=match.start(),
                    end=match.end(),
                ))
        return detections
```

---

### 4. `detector/ner_engine.py` - AI-Based Detection

**Purpose:** Detects contextual PII (names, organizations, locations) using a pre-trained BERT model. This catches things regex can't — like knowing "Apple" is a company vs. a fruit.

**Label mapping (Lines 14-34):**

```python
# NER models output labels like "PER", "B-PER", "I-PER"
# We map all variations to our EntityType values
_LABEL_MAP = {
    "PER": EntityType.PERSON,      # Different models use different labels
    "PERSON": EntityType.PERSON,   # for the same entity type
    "B-PER": EntityType.PERSON,    # B- prefix = "beginning of entity"
    "I-PER": EntityType.PERSON,    # I- prefix = "inside/continuation of entity"
    # ... same pattern for ORG, LOC, DATE, MONEY
}
```

**Why so many mappings?** Different NER models use different labeling schemes (BIO tagging, simple labels, etc.). This map normalizes them all.

**NERDetector class (Lines 37-97):**

```python
class NERDetector:
    def __init__(self, model_name="dslim/bert-base-NER", entities=None):
        self._model_name = model_name
        self._entities = entities
        self._pipeline = None   # Lazy loaded — model isn't loaded until first use

    def _load(self):
        if self._pipeline is not None:  # Already loaded
            return
        # Import transformers only when needed (it's a heavy dependency)
        from transformers import pipeline
        self._pipeline = pipeline(
            "ner",                              # Named Entity Recognition task
            model=self._model_name,             # dslim/bert-base-NER by default
            aggregation_strategy="simple",      # Merge sub-word tokens into whole entities
        )
```

**Why lazy loading?** The BERT model is ~400MB. Loading it at import time would slow down every startup, even if NER is never used.

```python
    def detect(self, text: str) -> list[Detection]:
        self._load()                                    # Load model if needed
        results = self._pipeline(text)                  # Run NER inference
        detections = []

        for ent in results:
            label = ent.get("entity_group", ent.get("entity", ""))
            mapped = _LABEL_MAP.get(label)              # Convert model label to our type
            if mapped is None:                          # Unknown label, skip
                continue
            if self._entities and mapped not in self._entities:  # Not requested
                continue

            value = text[ent["start"]:ent["end"]]       # Extract the actual text
            if len(value.strip()) < 2:                  # Skip noise (single chars)
                continue

            detections.append(Detection(
                entity_type=mapped,
                value=value,
                start=ent["start"],
                end=ent["end"],
                score=float(ent.get("score", 0.0)),     # Confidence from model
            ))
        return detections
```

---

### 5. `detector/hybrid.py` - Combined Detection

**Purpose:** Runs both regex and NER, then intelligently merges the results.

**Constructor (Lines 21-50):**

```python
class HybridDetector:
    def __init__(self, entities=None, ner_model="dslim/bert-base-NER", ner_threshold=0.5):
        self._ner_threshold = ner_threshold

        # Always create regex detector for pattern-based entities
        regex_entities = entities & REGEX_ENTITIES if entities else None
        self._regex = RegexDetector(entities=regex_entities)

        # Only create NER detector if NER entity types are requested
        self._ner = None
        need_ner = entities is None or bool(entities & NER_ENTITIES)
        if need_ner:
            try:
                from .ner_engine import NERDetector    # Import inside try block
                ner_entities = entities & NER_ENTITIES if entities else None
                self._ner = NERDetector(model_name=ner_model, entities=ner_entities)
            except ImportError:
                # NER deps not installed — gracefully fall back to regex only
                logger.info("NER dependencies not installed. Using regex-only detection.")
```

**Why the try/except?** NER requires `transformers` and `torch` (~2GB of dependencies). If they're not installed, ShieldPrompt still works with regex-only detection.

**detect() method (Lines 52-67):**

```python
def detect(self, text: str) -> list[Detection]:
    detections = self._regex.detect(text)    # Always run regex first (fast)

    if self._ner:                            # If NER is available...
        try:
            ner_detections = self._ner.detect(text)
            # Filter out low-confidence NER results
            ner_detections = [d for d in ner_detections if d.score >= self._ner_threshold]
            detections = self._merge(detections, ner_detections)
        except Exception as e:
            logger.warning("NER detection failed, using regex only: %s", e)

    return detections
```

**_merge() method (Lines 69-87) — The smart merger:**

```python
@staticmethod
def _merge(regex_dets, ner_dets) -> list[Detection]:
    merged = list(regex_dets)                    # Start with all regex results
    regex_spans = {(d.start, d.end) for d in regex_dets}  # Track regex spans

    for nd in ner_dets:
        # Does this NER detection overlap with ANY regex detection?
        overlaps = any(nd.start < re and nd.end > rs for rs, re in regex_spans)
        if not overlaps:
            merged.append(nd)    # Only add NER detection if no overlap

    merged.sort(key=lambda d: d.start)  # Sort by position for orderly processing
    return merged
```

**Why prefer regex over NER for overlaps?** Regex gives exact matches with 100% confidence (an email IS an email). NER might detect the same text as a PERSON. Regex wins because it's more precise.

---

### 6. `shield.py` - Core Engine

**Purpose:** The main class that orchestrates detection and masking/unmasking. This is what users interact with.

**Constructor (Lines 27-51):**

```python
class Shield:
    def __init__(self, entities=None, use_ner=None, ner_model="dslim/bert-base-NER",
                 ner_threshold=0.5, vault=None):

        # Normalize entity types: accept strings or EntityType enums
        self._entities = (
            {EntityType(e) if isinstance(e, str) else e for e in entities}
            if entities else DEFAULT_ENTITIES
        )
        self._vault = vault  # Use provided vault, or get from context later

        # Smart detector selection:
        needs_ner = bool(self._entities & NER_ENTITIES)  # Any NER types requested?
        if use_ner is False or not needs_ner:
            self._detector = RegexDetector(entities=self._entities)    # Fast path
        else:
            self._detector = HybridDetector(                          # Full detection
                entities=self._entities, ner_model=ner_model, ner_threshold=ner_threshold,
            )
```

**Key decision:** If the user only asks for EMAIL_ADDRESS and PHONE_NUMBER (both regex types), NER is never loaded. This keeps things fast when you don't need AI.

**vault property (Lines 53-55):**

```python
@property
def vault(self) -> Vault:
    return self._vault if self._vault else get_vault()
```

Uses the explicitly provided vault, OR falls back to the context-local vault.

**mask() method (Lines 57-71) — The heart of ShieldPrompt:**

```python
def mask(self, text: str) -> str:
    detections = self._detector.detect(text)   # Step 1: Find all PII
    if not detections:
        return text                             # No PII found, return as-is

    # Step 2: Sort DESCENDING by position
    # WHY? If we replace from left to right, each replacement shifts all
    # subsequent positions. Replacing from right to left avoids this.
    detections.sort(key=lambda d: d.start, reverse=True)

    result = text
    for det in detections:
        # Step 3: Store in vault and get token
        token = self.vault.store(det.entity_type, det.value)
        # Step 4: Replace the PII text with the token
        result = result[:det.start] + token + result[det.end:]

    return result
```

**Example walkthrough:**

```
Input:  "Email alice@example.com, call 555-1234"
               ^                       ^
               pos 6-23                pos 31-39

Detections (sorted descending by start):
  1. PHONE_NUMBER at pos 31-39  ("555-1234")
  2. EMAIL_ADDRESS at pos 6-23  ("alice@example.com")

Replace PHONE first (rightmost):
  "Email alice@example.com, call [PHONE_NUMBER_1]"
  Positions 0-30 unchanged!

Replace EMAIL next (leftmost):
  "Email [EMAIL_ADDRESS_1], call [PHONE_NUMBER_1]"

If we did LEFT to RIGHT instead:
  Replace EMAIL: "Email [EMAIL_ADDRESS_1], call 555-1234"
  Now "555-1234" is no longer at position 31-39! Its position shifted.
  The second replacement would corrupt the text.
```

**unmask() method (Lines 73-75):**

```python
def unmask(self, text: str) -> str:
    return self.vault.restore_text(text)  # Delegates to vault
```

**mask_and_track() method (Lines 77-80):**

```python
def mask_and_track(self, text: str) -> tuple[str, dict[str, str]]:
    masked = self.mask(text)
    return masked, self.vault.mappings   # Returns both masked text AND the mapping dict
```

Useful for debugging or auditing.

---

### 7. `decorator.py` - Function Wrapper

**Purpose:** The `@mask_pii` decorator automatically masks function inputs and unmasks outputs. Zero code changes to your existing LLM calls.

**Decorator factory (Lines 15-50):**

```python
def mask_pii(
    entities=None,         # Which PII to detect
    use_ner=None,          # Auto-detect NER need
    param_name="prompt",   # Which function argument to mask
    mask_kwargs=None,      # Additional kwargs to mask
    unmask_response=True,  # Whether to unmask the return value
) -> Callable:
    # Convert entity names to EntityType enums
    entity_set = {EntityType(e) for e in entities} if entities else DEFAULT_ENTITIES
```

**Inner decorator (Lines 52-140):**

```python
    def decorator(func):
        sig = inspect.signature(func)   # Capture function signature for argument binding

        def _create_shield():
            vault = Vault()             # Fresh vault per call (no cross-call leakage)
            shield = Shield(entities=entity_set, vault=vault, ...)
            return shield, vault

        def _mask_args(shield, args, kwargs):
            bound = sig.bind(*args, **kwargs)  # Bind positional/keyword args to param names
            bound.apply_defaults()              # Fill in default values

            # Mask the target parameter
            if param_name in bound.arguments:
                val = bound.arguments[param_name]
                if isinstance(val, str):
                    bound.arguments[param_name] = shield.mask(val)
            else:
                # Fallback: mask the first string argument (any name)
                for name, val in bound.arguments.items():
                    if isinstance(val, str):
                        bound.arguments[name] = shield.mask(val)
                        break

            # Mask any additional kwargs specified in mask_kwargs
            if mask_kwargs:
                for kw in mask_kwargs:
                    if kw in bound.arguments and isinstance(bound.arguments[kw], str):
                        bound.arguments[kw] = shield.mask(bound.arguments[kw])

            return tuple(bound.args), bound.kwargs

        def _unmask_result(shield, result):
            if not unmask_response:
                return result
            if isinstance(result, str):      # String -> unmask directly
                return shield.unmask(result)
            if isinstance(result, dict):     # Dict -> unmask all string values
                return {k: shield.unmask(v) if isinstance(v, str) else v
                        for k, v in result.items()}
            return result                    # Anything else -> pass through
```

**Sync vs Async handling (Lines 111-140):**

```python
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                shield, vault = _create_shield()
                ctx_token = set_vault(vault)       # Set vault in async context
                try:
                    new_args, new_kwargs = _mask_args(shield, args, kwargs)
                    result = await func(*new_args, **new_kwargs)  # await for async
                    return _unmask_result(shield, result)
                finally:
                    reset_vault(ctx_token)          # Always clean up context
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                shield, vault = _create_shield()
                ctx_token = set_vault(vault)
                try:
                    new_args, new_kwargs = _mask_args(shield, args, kwargs)
                    result = func(*new_args, **new_kwargs)
                    return _unmask_result(shield, result)
                finally:
                    reset_vault(ctx_token)
            return sync_wrapper
```

**Why `finally`?** Even if the wrapped function throws an exception, the context vault is always cleaned up. This prevents memory leaks.

---

### 8. `middleware.py` - FastAPI Integration

**Purpose:** ASGI middleware that automatically masks ALL incoming request bodies and unmasks ALL outgoing response bodies. Add one line to your FastAPI app and every endpoint gets privacy protection.

**Sensitivity levels (Lines 15-23):**

```python
_SENSITIVITY_MAP = {
    "low":    {EMAIL_ADDRESS, CREDIT_CARD, SSN},           # Just the critical stuff
    "medium": DEFAULT_ENTITIES,                              # Common PII (default)
    "high":   ALL_ENTITIES,                                  # Everything including URLs, API keys
}
```

**Middleware factory (Lines 26-167):**

```python
def ShieldPromptMiddleware(app, sensitivity="medium", exclude_paths=None, ...):
    # Import starlette types (only needed if middleware is used)
    from starlette.types import ASGIApp, Receive, Scope, Send, Message
```

**Request handling (Lines 65-99):**

```python
    # For each HTTP request:
    vault = Vault()                    # Fresh vault per request
    shield = Shield(entities=entity_set, vault=vault)

    # Read the ENTIRE request body (may arrive in chunks)
    body_parts = []
    while True:
        message = await receive()
        body_parts.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    full_body = b"".join(body_parts)

    # Try to parse as JSON and mask all string values
    try:
        data = json.loads(full_body)
        masked_data = _mask_json(shield, data)    # Recursive masking
        masked_body = json.dumps(masked_data).encode()
    except (json.JSONDecodeError, UnicodeDecodeError):
        pass   # Not JSON? Pass through unchanged
```

**Recursive JSON masking (Lines 170-178):**

```python
def _mask_json(shield, data):
    if isinstance(data, str):     # String -> mask it
        return shield.mask(data)
    if isinstance(data, dict):    # Dict -> recurse into values
        return {k: _mask_json(shield, v) for k, v in data.items()}
    if isinstance(data, list):    # List -> recurse into items
        return [_mask_json(shield, item) for item in data]
    return data                   # Numbers, booleans, null -> pass through
```

This handles ANY JSON structure: nested objects, arrays of objects, deeply nested strings.

**Response handling (Lines 117-165):**

```python
    # Buffer the response body (may arrive in chunks)
    async def masked_send(message):
        if message["type"] == "http.response.start":
            start_message = message   # Save headers, don't send yet
            return

        if message["type"] == "http.response.body":
            response_parts.append(body)
            if not more:                           # Last chunk
                full_resp = b"".join(response_parts)
                unmasked = shield.unmask(full_resp.decode())  # Unmask!
                full_resp = unmasked.encode()

                # Update Content-Length header (unmasked text may differ in size)
                # Then send everything
```

**Why buffer the response?** The app might stream the response in chunks. We need the FULL response to unmask properly (a token might be split across chunks).

---

### 9. `cli.py` - Command Line Tool

**Purpose:** Terminal interface for masking/unmasking/inspecting text.

**Three commands:**

**`mask` command (Lines 94-108):**

```python
def _cmd_mask(args):
    text = _get_text(args)                          # From arg, file, or stdin
    entities = {EntityType(e) for e in args.entities} if args.entities else None
    vault = Vault()
    shield = Shield(entities=entities, use_ner=not args.no_ner, vault=vault)
    masked = shield.mask(text)
    print(masked)                                   # Output masked text

    if args.save_vault:
        _save_vault(vault, args.save_vault)         # Save mappings for later unmask
```

**`unmask` command (Lines 111-114):**

```python
def _cmd_unmask(args):
    text = _get_text(args)
    vault = _load_vault(args.vault)                 # Load previously saved vault
    print(vault.restore_text(text))                 # Restore all tokens
```

**`inspect` command (Lines 117-127):**

```python
def _cmd_inspect(args):
    text = _get_text(args)
    detector = HybridDetector()
    detections = detector.detect(text)              # Detect but don't mask
    for d in detections:
        print(f"  {d.entity_type}  {d.value!r}  (pos {d.start}-{d.end}, score={d.score:.2f})")
```

**Input flexibility (Lines 82-91):**

```python
def _get_text(args) -> str:
    if args.file:                       # --file flag
        return Path(args.file).read_text()
    if args.text:                       # Positional argument
        return args.text
    if not sys.stdin.isatty():          # Piped input (echo "text" | shieldprompt mask)
        return sys.stdin.read()
    # None of the above — error
    print("Error: provide text as argument, --file, or pipe via stdin", file=sys.stderr)
    sys.exit(1)
```

---

### 10. `mcp_server.py` - Claude Code Integration

**Purpose:** An MCP (Model Context Protocol) server that lets Claude Code use ShieldPrompt as a tool. It speaks JSON-RPC 2.0 over stdin/stdout.

**Session state (Lines 28-39):**

```python
_session_vault = Vault()          # One vault per server session (persistent)
_session_shield: Shield | None = None   # Lazily created

def _get_shield(entities=None):
    global _session_shield
    if _session_shield is None:
        _session_shield = Shield(entities=entity_set, use_ner=False, vault=_session_vault)
    return _session_shield
```

**Why persistent vault?** The MCP server runs as a long-lived process. A user might mask in one call and unmask in a later call. The vault persists between calls.

**Five tools exposed (Lines 63-137):**

| Tool               | What it does                          |
| ------------------ | ------------------------------------- |
| `shield_mask`    | Masks PII in text                     |
| `shield_unmask`  | Restores tokens to real values        |
| `shield_inspect` | Lists detected PII without masking    |
| `shield_vault`   | Shows current token-to-value mappings |
| `shield_clear`   | Clears all mappings                   |

**Main loop (Lines 213-244):**

```python
def main():
    for line in sys.stdin:           # Read JSON-RPC messages line by line
        msg = json.loads(line)
        method = msg.get("method")
        msg_id = msg.get("id")

        if msg_id is None:           # Notification (no response needed)
            handler = _NOTIFICATIONS.get(method)
            if handler: handler(params)
            continue

        handler = _HANDLERS.get(method)  # Request (needs response)
        if handler:
            response = handler(msg_id, params)
        else:
            response = _make_error(msg_id, -32601, f"Method not found: {method}")

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()                # Flush immediately for real-time communication
```

---

### 11. `__init__.py` - Package Exports

**Purpose:** Defines what `from shieldprompt import ...` gives you.

```python
from .decorator import mask_pii     # The @mask_pii decorator
from .entities import EntityType    # The PII type enum
from .shield import Shield          # The core engine
from .vault import Vault, get_vault # Token storage

__version__ = "0.1.0"

__all__ = ["Shield", "Vault", "EntityType", "mask_pii", "get_vault", "__version__"]
```

---

### 12. `__main__.py` - Module Runner

**Purpose:** Enables running as `python -m shieldprompt`.

```python
from .cli import main
main()    # Just calls the CLI entry point
```

---

## Data Flow Diagrams

### Flow 1: Direct API Usage

```
from shieldprompt import Shield

shield = Shield()

# MASK
text = "Contact alice@example.com or call 555-123-4567"
masked = shield.mask(text)
# masked = "Contact [EMAIL_ADDRESS_1] or call [PHONE_NUMBER_1]"

# ... send masked text to LLM ...
# LLM responds: "I'll reach out to [EMAIL_ADDRESS_1]"

# UNMASK
response = shield.unmask("I'll reach out to [EMAIL_ADDRESS_1]")
# response = "I'll reach out to alice@example.com"
```

### Flow 2: Decorator Usage

```
@mask_pii(entities=["PERSON", "EMAIL_ADDRESS"])
def ask_llm(prompt: str) -> str:
    # prompt is ALREADY masked when this runs
    # e.g., "Schedule meeting with [PERSON_1] at [EMAIL_ADDRESS_1]"
    return openai.chat(prompt)
    # Return value is AUTOMATICALLY unmasked before caller gets it

# User just calls normally:
result = ask_llm("Schedule meeting with Alice at alice@example.com")
# result contains real names and emails, even though the LLM never saw them
```

### Flow 3: CLI Usage

```bash
# Mask and save vault
$ shieldprompt mask "SSN: 123-45-6789" --save-vault vault.json
SSN: [SSN_1]

# Later, unmask using saved vault
$ shieldprompt unmask "[SSN_1]" --vault vault.json
123-45-6789

# Inspect (detect without masking)
$ shieldprompt inspect "Email alice@example.com at Google"
  EMAIL_ADDRESS       'alice@example.com'     (pos 6-23, score=1.00)
  ORGANIZATION        'Google'                (pos 27-33, score=0.95)
```

---

## Key Design Patterns

### 1. Strategy Pattern (Detector Selection)

Shield picks Regex or Hybrid detector based on what entity types you request. You don't need to know which engine is used.

### 2. Context Variables (Vault Isolation)

`contextvars.ContextVar` ensures each async task/thread gets its own vault. No PII leaks between concurrent requests.

### 3. Idempotent Token Generation

Same PII value always produces the same token. `"alice@example.com"` is always `[EMAIL_ADDRESS_1]`, even if it appears 10 times.

### 4. Graceful Degradation

NER dependencies missing? Falls back to regex-only. No crashes, no configuration needed.

### 5. Right-to-Left Replacement

Detections are sorted by position descending before replacement, preventing index corruption.

### 6. Length-Sorted Unmasking

Tokens are sorted by length descending during restoration, preventing `[PERSON_10]` from being partially corrupted by `[PERSON_1]` replacement.

### 7. Lazy Loading

The NER model (~400MB) is only loaded when `detect()` is first called, not at import time.

### 8. Recursive JSON Masking

The middleware handles any JSON structure depth — nested objects, arrays, mixed types.
