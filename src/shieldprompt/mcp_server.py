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

from . import __version__
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
        # NER on by default so PERSON / ORG / LOCATION actually get masked —
        # Presidio is a hard dependency since 0.1.4, no ImportError risk.
        _session_shield = Shield(entities=entity_set, vault=_session_vault)
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
            "version": __version__,
        },
    })


def _handle_tools_list(id: Any, params: dict) -> dict:
    tools = [
        {
            "name": "shield_mask",
            "description": (
                "Mask PII in text. Replaces emails, phone numbers, SSNs, "
                "credit cards, IPs, names, etc. with tokens like [EMAIL_ADDRESS_1]. "
                "This helper does not intercept model inputs. Mask locally with the CLI "
                "before sending secrets to the model. Never pass secrets already excluded from its context."
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
    if not isinstance(args, dict):
        return _make_error(id, -32602, "arguments must be an object")
    if name in {"shield_mask", "shield_inspect"} and not isinstance(args.get("text"), str):
        return _make_error(id, -32602, "text must be a string")

    try:
        if name == "shield_mask":
            shield = _get_shield()
            masked = shield.mask(args["text"])
            return _make_response(id, {
                "content": [{"type": "text", "text": masked}],
            })

        elif name == "shield_inspect":
            shield = _get_shield()
            detections = shield._detector.detect(args["text"])
            lines = []
            for d in detections:
                lines.append(
                    f"- {d.entity_type} (pos {d.start}-{d.end})"
                )
            result = "\n".join(lines) if lines else "No PII detected."
            return _make_response(id, {
                "content": [{"type": "text", "text": result}],
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
        return _make_error(id, -32603, "Tool failed; no successful masking result is available.")


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


def _dispatch(msg: Any) -> dict | None:
    """Validate messages before dispatch; never expose exception data or PII."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return _make_error(None, -32600, "Invalid Request")
    msg_id = msg.get("id")
    method = msg.get("method")
    if not isinstance(method, str) or isinstance(msg_id, (dict, list, bool)):
        return _make_error(None, -32600, "Invalid Request")
    params = msg.get("params", {})
    if not isinstance(params, dict):
        return _make_error(msg_id, -32602, "params must be an object") if "id" in msg else None
    if "id" not in msg:
        handler = _NOTIFICATIONS.get(method)
        if handler:
            handler(params)
        return None
    if method == "ping":
        return _make_response(msg_id, {})
    handler = _HANDLERS.get(method)
    if handler is None:
        return _make_error(msg_id, -32601, "Method not found")
    try:
        return handler(msg_id, params)
    except Exception:
        return _make_error(msg_id, -32603, "Internal error")


def main() -> None:
    """Run the MCP helper; raw vault values are never returned as tool output."""
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            response = _dispatch(json.loads(line))
        except json.JSONDecodeError:
            response = _make_error(None, -32700, "Parse error")
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
