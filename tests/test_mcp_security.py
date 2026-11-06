"""Protocol and model-visible privacy boundary regressions."""
import io
import json

from shieldprompt import Shield, Vault, __version__
from shieldprompt import mcp_server as server


def test_no_secret_returning_tools(monkeypatch):
    vault = Vault()
    vault.store('EMAIL_ADDRESS', 'alice@example.com')
    monkeypatch.setattr(server, '_session_vault', vault)
    names = {t['name'] for t in server._handle_tools_list(1, {})['result']['tools']}
    assert names == {'shield_mask', 'shield_inspect', 'shield_clear'}
    for name in ('shield_unmask', 'shield_vault'):
        response = server._handle_tools_call(1, {'name': name, 'arguments': {'text': '[EMAIL_ADDRESS_1]'}})
        assert 'error' in response
        assert 'alice@example.com' not in json.dumps(response)


def test_inspection_does_not_return_originals(monkeypatch):
    monkeypatch.setattr(server, '_session_shield', Shield(entities={'EMAIL_ADDRESS'}, use_ner=False, vault=Vault()))
    result = server._handle_tools_call(1, {'name': 'shield_inspect', 'arguments': {'text': 'alice@example.com'}})
    assert 'EMAIL_ADDRESS' in json.dumps(result)
    assert 'alice@example.com' not in json.dumps(result)


def test_dispatch_survives_bad_shapes():
    for request in ([1], None, {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': None}):
        assert 'error' in server._dispatch(request)
    for args in (None, [], {'text': 123}):
        response = server._dispatch({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {'name': 'shield_mask', 'arguments': args}})
        assert response['error']['code'] == -32602
    assert server._dispatch({'jsonrpc': '2.0', 'id': 2, 'method': 'ping'})['result'] == {}
    assert server._handle_initialize(1, {})['result']['serverInfo']['version'] == __version__


def test_parse_errors_do_not_stop_stdio(monkeypatch):
    monkeypatch.setattr(server.sys, 'stdin', io.StringIO('invalid\n[1]\n{"jsonrpc":"2.0","id":3,"method":"ping"}\n'))
    output = io.StringIO()
    monkeypatch.setattr(server.sys, 'stdout', output)
    server.main()
    results = [json.loads(line) for line in output.getvalue().splitlines()]
    assert results[0]['error']['code'] == -32700
    assert results[1]['error']['code'] == -32600
    assert results[2] == {'jsonrpc': '2.0', 'id': 3, 'result': {}}
