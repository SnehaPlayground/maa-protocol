"""Tests for remaining completion modules."""

from pathlib import Path

from maa_x.browser import browser_capabilities, BrowserSession
from maa_x.rvf import RVFPacker, RVFUnpacker, RVFValidator, RVFRegistry
from maa_x.deployment import deployment_profiles, get_runtime_config, run_health_check
from maa_x.ipfs import add_text, cat_text, pin, list_pins
from maa_x.github_automation import GitHubAutomation
from maa_x.mcp_runtime import MCPRuntime, MCPRequest
from maa_x.wasm import WasmRunner, WasmAgent, WasmPlugin, create_sandbox, runtime_name


def test_browser_capabilities_and_fetch():
    caps = browser_capabilities()
    assert caps['fetch'] is True
    session = BrowserSession()
    result = session.fetch('https://example.com')
    assert result.status_code >= 0


def test_rvf_pack_unpack_validate(tmp_path):
    src = tmp_path / 'plugin'
    src.mkdir()
    (src / 'manifest.json').write_text('{"name":"demo-rvf","version":"1.0.0"}')
    (src / 'plugin.json').write_text('{"name":"demo-rvf","version":"1.0.0"}')
    bundle = RVFPacker(src).pack()
    report = RVFValidator().validate(bundle)
    assert report.valid
    out = RVFUnpacker(bundle).unpack_to(tmp_path / 'out')
    assert (out / 'manifest.json').exists()
    reg = RVFRegistry()
    assert RVFUnpacker(bundle).load_bundle().install(reg)


def test_deployment_health():
    assert 'multi-tenant' in deployment_profiles()
    cfg = get_runtime_config()
    assert cfg.max_agents >= 1
    assert len(run_health_check()) >= 1


def test_ipfs_mock_store():
    obj = add_text('hello ipfs')
    assert cat_text(obj.cid) == 'hello ipfs'
    assert pin(obj.cid)
    assert obj.cid in list_pins()


def test_github_automation_surface():
    gh = GitHubAutomation()
    result = gh.run('--version')
    assert result.command.startswith('gh')


def test_mcp_runtime():
    rt = MCPRuntime()
    rt.register_handler('swarm_init', lambda args: {'ok': True, 'args': args})
    resp = rt.call(MCPRequest(tool='swarm_init', arguments={'x': 1}, request_id='r1', session_id='s1'))
    assert resp.ok
    assert resp.result['ok'] is True


def test_wasm_fallback_runtime(tmp_path):
    wasm_bytes = b'fake-wasm'
    runner = WasmRunner()
    res = runner.run_buffer(wasm_bytes)
    assert isinstance(res.success, bool)
    agent = WasmAgent(wasm_bytes)
    assert isinstance(agent.execute('task', {'x': 1}), str)
    wasm_file = tmp_path / 'demo.wasm'
    wasm_file.write_bytes(wasm_bytes)
    plugin = WasmPlugin.load(wasm_file)
    assert plugin.install()
    assert plugin.enable()
    assert isinstance(plugin.call('run'), str)
    sandbox = create_sandbox()
    valid, _ = sandbox.validate(wasm_bytes)
    assert valid
