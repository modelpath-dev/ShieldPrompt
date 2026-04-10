"""ShieldPrompt MCP Server — integrates with Claude Code, VS Code, JetBrains, etc.

Run with:
    python -m shieldprompt.mcp_server

Add to Claude Code settings (.claude/settings.json):
    {
      "mcpServers": {
        "shieldprompt": {
          "command": "python",
          "args": ["-m", "shieldprompt.mcp_server"]
        }
      }
    }
"""

from __future__ import annotations

import json
import sys
from typing import Any

from .entities import EntityType
from .shield import Shield
from .vault import Vault

# Persistent vault across calls within the same server session
_session_vault = Vault()
_session_shield: Shield | None = None


def _get_shield(entities: list[str] | None = None) -> Shield:
    global _session_shield
    if _session_shield is None:
        entity_set = {EntityType(e) for e in entities} if entities else None
        _session_shield = Shield(
            entities=entity_set, use_ner=False, vault=_session_vault
        )
    return _session_shield


# --- JSON-RPC over stdio (MCP protocol) ---

def _make_response(id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _make_error(id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": id, "error": {"code": code, "message": message}}


def _handle_initialize(id: Any, params: dict) -> dict:
    return _make_response(id, {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {
            "name": "shieldprompt",
            "version": "0.1.2",
        },
    })


def _handle_tools_list(id: Any, params: dict) -> dict:
    tools = [
        {
            "name": "shield_mask",
            "description": (
                "Mask PII in text. Replaces emails, phone numbers, SSNs, "
                "credit cards, IPs, names, etc. with tokens like [EMAIL_ADDRESS_1]. "
                "Use this BEFORE sending sensitive user data to any LLM or external service."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text containing PII to mask.",
                    },
                },
                "required": ["text"],
            },
        },
        {
            "name": "shield_unmask",
            "description": (
                "Restore masked tokens back to their original PII values. "
                "Use this to convert [EMAIL_ADDRESS_1] etc. back to real data "
                "after receiving a response from an LLM."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text containing tokens like [PERSON_1] to restore.",
                    },
                },
                "required": ["text"],
            },
        },
        {
            "name": "shield_inspect",
            "description": (
                "Detect and list all PII entities found in text without masking. "
                "Returns a list of detected entities with their types and positions."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to scan for PII.",
                    },
                },
                "required": ["text"],
            },
        },
        {
            "name": "shield_vault",
            "description": (
                "Show the current vault mappings (token -> real value). "
                "Useful for debugging or auditing what PII has been masked."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
        },
        {
            "name": "shield_clear",
            "description": "Clear all vault mappings. Start fresh.",
            "inputSchema": {
                "type": "object",
                "properties": {},
            },
        },
    ]
    return _make_response(id, {"tools": tools})


def _handle_tools_call(id: Any, params: dict) -> dict:
    name = params.get("name", "")
    args = params.get("arguments", {})

    try:
        if name == "shield_mask":
            shield = _get_shield()
            masked = shield.mask(args["text"])
            return _make_response(id, {
                "content": [{"type": "text", "text": masked}],
            })

        elif name == "shield_unmask":
            text = _session_vault.restore_text(args["text"])
            return _make_response(id, {
                "content": [{"type": "text", "text": text}],
            })

        elif name == "shield_inspect":
            shield = _get_shield()
            detections = shield._detector.detect(args["text"])
            lines = []
            for d in detections:
                lines.append(
                    f"- {d.entity_type}: {d.value!r} (pos {d.start}-{d.end})"
                )
            result = "\n".join(lines) if lines else "No PII detected."
            return _make_response(id, {
                "content": [{"type": "text", "text": result}],
            })

        elif name == "shield_vault":
            mappings = _session_vault.mappings
            if not mappings:
                text = "Vault is empty."
            else:
                lines = [f"  {tok} -> {val}" for tok, val in mappings.items()]
                text = "Current vault mappings:\n" + "\n".join(lines)
            return _make_response(id, {
                "content": [{"type": "text", "text": text}],
            })

        elif name == "shield_clear":
            _session_vault.clear()
            global _session_shield
            _session_shield = None
            return _make_response(id, {
                "content": [{"type": "text", "text": "Vault cleared."}],
            })

        else:
            return _make_error(id, -32601, f"Unknown tool: {name}")

    except Exception as e:
        return _make_error(id, -32603, str(e))


def _handle_notifications_initialized(params: dict) -> None:
    pass


_HANDLERS = {
    "initialize": _handle_initialize,
    "tools/list": _handle_tools_list,
    "tools/call": _handle_tools_call,
}

_NOTIFICATIONS = {
    "notifications/initialized": _handle_notifications_initialized,
}


def main() -> None:
    """Run the MCP server over stdio."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue

        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params", {})

        # Handle notifications (no id, no response)
        if msg_id is None:
            handler = _NOTIFICATIONS.get(method)
            if handler:
                handler(params)
            continue

        # Handle requests
        handler = _HANDLERS.get(method)
        if handler:
            response = handler(msg_id, params)
        else:
            response = _make_error(msg_id, -32601, f"Method not found: {method}")

        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
