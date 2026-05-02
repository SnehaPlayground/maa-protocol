"""CLI module — maa-x command-line tool."""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    """Entry point for the maa-x CLI."""
    parser = argparse.ArgumentParser(
        prog="maa-x",
        description="Maa-X: Enterprise AI orchestration CLI",
    )
    sub = parser.add_subparsers(dest="command")

    # Swarm commands
    swarm = sub.add_parser("swarm", help="Swarm orchestration commands")
    swarm_sp = swarm.add_subparsers(dest="swarm_cmd")
    sp_init = swarm_sp.add_parser("init", help="Initialize a swarm")
    sp_init.add_argument("--topology", default="hierarchical", choices=["hierarchical", "mesh", "fanout"])
    sp_init.add_argument("--max-agents", type=int, default=8)
    sp_init.add_argument("--strategy", default="specialized", choices=["specialized", "generalist"])
    sp_status = swarm_sp.add_parser("status", help="Show swarm status")
    sp_run = swarm_sp.add_parser("run", help="Run a swarm task")
    sp_run.add_argument("task", help="Task description")

    # Plugin commands
    plug = sub.add_parser("plugin", help="Plugin management")
    plug_sp = plug.add_subparsers(dest="plug_cmd")
    plug_list = plug_sp.add_parser("list", help="List registered plugins")
    plug_enable = plug_sp.add_parser("enable", help="Enable a plugin")
    plug_enable.add_argument("name", help="Plugin name")
    plug_disable = plug_sp.add_parser("disable", help="Disable a plugin")
    plug_disable.add_argument("name", help="Plugin name")
    plug_stats = plug_sp.add_parser("stats", help="Show plugin stats")
    plug_discover = plug_sp.add_parser("discover", help="Discover installable plugins")
    plug_install = plug_sp.add_parser("install", help="Install a discovered plugin")
    plug_install.add_argument("name", help="Plugin name")

    # MCP commands
    mcp = sub.add_parser("mcp", help="MCP tool registry")
    mcp_sp = mcp.add_subparsers(dest="mcp_cmd")
    mcp_list = mcp_sp.add_parser("tools", help="List available MCP tools")
    mcp_list.add_argument("--group", default=None, help="Filter by group name")
    mcp_search = mcp_sp.add_parser("search", help="Search MCP tools")
    mcp_search.add_argument("query", help="Search query")
    mcp_caps = mcp_sp.add_parser("capabilities", help="Show MCP capabilities")
    mcp_modes = mcp_sp.add_parser("modes", help="List preset modes")

    # Model routing commands
    route = sub.add_parser("route", help="Model routing")
    route_sp = route.add_subparsers(dest="route_cmd")
    route_list = route_sp.add_parser("list", help="List available models")
    route_route = route_sp.add_parser("resolve", help="Resolve best model for a request")
    route_route.add_argument("--capabilities", nargs="*", default=[], help="Required capabilities")
    route_route.add_argument("--strategy", default="latency", choices=["latency", "cost", "capability"])

    # Security commands
    sec = sub.add_parser("security", help="Security scanning")
    sec_sp = sec.add_subparsers(dest="sec_cmd")
    sec_scan = sec_sp.add_parser("scan", help="Scan content for threats")
    sec_scan.add_argument("content", help="Content to scan")
    sec_redact = sec_sp.add_parser("redact", help="Redact PII from content")
    sec_redact.add_argument("content", help="Content to redact")

    # Worker commands
    worker = sub.add_parser("worker", help="Background worker management")
    worker_sp = worker.add_subparsers(dest="worker_cmd")
    worker_start = worker_sp.add_parser("start", help="Start background worker pool")
    worker_start.add_argument("--num-workers", type=int, default=4)
    worker_status = worker_sp.add_parser("status", help="Show worker pool status")

    # Memory commands
    mem = sub.add_parser("memory", help="Memory operations")
    mem_sp = mem.add_subparsers(dest="mem_cmd")
    mem_list = mem_sp.add_parser("namespaces", help="List memory namespaces")
    mem_stats = mem_sp.add_parser("stats", help="Memory stats")

    # Governance commands
    gov = sub.add_parser("governance", help="Governance controls")
    gov_sp = gov.add_subparsers(dest="gov_cmd")
    gov_approvals = gov_sp.add_parser("approvals", help="List pending approvals")
    gov_audit = gov_sp.add_parser("audit", help="Show audit log")
    gov_audit.add_argument("--tenant", default=None, help="Tenant ID filter")

    # Version
    sub.add_parser("version", help="Print version")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "version":
        print("maa-x 0.1.0")
        return 0

    # ── Swarm ────────────────────────────────────────────────────────────────

    if args.command == "swarm":
        if args.swarm_cmd == "init":
            from maa_x.swarm import SwarmConfig, SwarmExecutionEngine, Topology
            topo = {"hierarchical": Topology.HIERARCHICAL, "mesh": Topology.MESH, "fanout": Topology.FANOUT}
            config = SwarmConfig(
                topology=topo.get(args.topology, Topology.HIERARCHICAL),
                max_agents=args.max_agents,
                strategy=args.strategy,
            )
            engine = SwarmExecutionEngine()
            plan = engine.create_plan("swarm-init", config)
            print(f"✓ Swarm initialized")
            print(f"  Topology:   {args.topology}")
            print(f"  Max agents:  {args.max_agents}")
            print(f"  Strategy:    {args.strategy}")
            print(f"  Agents:      {plan.agent_count()}")
            print(f"  Coordinator: {plan.coordinator_id}")
            return 0

        if args.swarm_cmd == "status":
            from maa_x.swarm import SwarmExecutionEngine, SwarmConfig, swarm_stats
            stats = swarm_stats()
            print(f"Active plans:       {stats.get('active_plans', 0)}")
            print(f"Completed swarms:   {stats.get('completed_swarm_count', 0)}")
            by_outcome = stats.get("by_outcome", {})
            if by_outcome:
                print("By outcome:")
                for outcome, count in by_outcome.items():
                    print(f"  {outcome}: {count}")
            return 0

        if args.swarm_cmd == "run":
            from maa_x.swarm import run_swarm
            print(f"Running swarm task: {args.task[:60]}")
            metrics = run_swarm(args.task)
            print(f"✓ Swarm completed")
            print(f"  ID:         {metrics.swarm_id}")
            print(f"  Outcome:    {metrics.outcome}")
            print(f"  Duration:   {metrics.duration_ms:.1f}ms")
            print(f"  Agents:     {metrics.agent_count}")
            print(f"  Rounds:     {metrics.total_rounds}")
            print(f"  Consensus:  {metrics.consensus_steps}")
            return 0

    # ── Plugin ───────────────────────────────────────────────────────────────

    if args.command == "plugin":
        from maa_x.plugins import (
            get_registry, enable_plugin, disable_plugin,
            list_plugins, discover_plugins, install_plugin,
            PluginKind, PluginState,
        )

        if args.plug_cmd == "list":
            plugins = list_plugins()
            print(f"Total plugins: {len(plugins)}")
            for p in plugins:
                loaded = "✓" if p.is_loaded() else "✗"
                print(f"  [{loaded}] {p.name:<30} v{p.version}  [{p.kind.value}]  {p.state.value}")
            return 0

        if args.plug_cmd == "enable":
            ok = enable_plugin(args.name)
            print(f"Plugin '{args.name}' {'enabled ✓' if ok else 'NOT found ✗'}")
            return 0

        if args.plug_cmd == "disable":
            disable_plugin(args.name)
            print(f"Plugin '{args.name}' disabled")
            return 0

        if args.plug_cmd == "stats":
            registry = get_registry()
            stats = registry.stats()
            print(f"Total plugins:  {stats['total']}")
            print(f"Loaded:        {stats['loaded']}")
            print("By state:")
            for state, count in stats["by_state"].items():
                print(f"  {state}: {count}")
            print("By kind:")
            for kind, count in stats["by_kind"].items():
                print(f"  {kind}: {count}")
            return 0

        if args.plug_cmd == "discover":
            found = discover_plugins()
            print(f"Discovered plugins: {len(found)}")
            for name in found:
                print(f"  {name}")
            return 0

        if args.plug_cmd == "install":
            ok = install_plugin(args.name)
            print(f"Plugin '{args.name}' {'installed ✓' if ok else 'install failed ✗'}")
            return 0

    # ── MCP ─────────────────────────────────────────────────────────────────

    if args.command == "mcp":
        from maa_x.mcp import list_tools, get_tool, search_tools, mcp_capabilities

        if args.mcp_cmd == "tools":
            if args.group:
                from maa_x.mcp import get_tool_group
                tools = get_tool_group(args.group)
                print(f"Tools in group '{args.group}': {len(tools)}")
            else:
                tools = list_tools()
                print(f"Available tools: {len(tools)}")
            for t in (list_tools() if not args.group else tools):
                tool = get_tool(t) if not args.group else get_tool(t)
                if tool:
                    print(f"  {tool.name:<20} [{tool.category}]  {tool.description[:60]}")
            return 0

        if args.mcp_cmd == "search":
            results = search_tools(args.query)
            print(f"Results for '{args.query}': {len(results)}")
            for t in results:
                print(f"  {t.name:<20} [{t.category}]")
            return 0

        if args.mcp_cmd == "capabilities":
            caps = mcp_capabilities()
            print(f"Tool count:  {caps['tool_count']}")
            print(f"Group count: {caps['group_count']}")
            print(f"Mode count:  {caps['mode_count']}")
            print("Categories:")
            for cat, count in caps["categories"].items():
                print(f"  {cat}: {count}")
            print(f"Transports:  {caps['transports']}")
            return 0

        if args.mcp_cmd == "modes":
            from maa_x.mcp import list_preset_modes
            modes = list_preset_modes()
            print(f"Preset modes: {len(modes)}")
            for m in modes:
                print(f"  {m}")
            return 0

    # ── Routing ──────────────────────────────────────────────────────────────

    if args.command == "route":
        from maa_x.routing import MultiProviderRouter

        if args.route_cmd == "list":
            router = MultiProviderRouter()
            models = router.list_models()
            print(f"Available models: {len(models)}")
            for m in models:
                print(f"  {m.name:<25} {m.provider:<15} latency={m.latency_ms_estimate:.0f}ms  cost={m.cost_per_1k_input + m.cost_per_1k_output:.4f}")
            return 0

        if args.route_cmd == "resolve":
            router = MultiProviderRouter(strategy=args.strategy)
            request = {"required_capabilities": args.capabilities}
            model = router.route(request)
            if model:
                print(f"Selected: {model.name} ({model.provider})")
                print(f"  Latency: {model.latency_ms_estimate}ms")
                print(f"  Cost per 1k: ${model.cost_per_1k_input + model.cost_per_1k_output:.4f}")
            else:
                print("No suitable model found")
            return 0

    # ── Security ─────────────────────────────────────────────────────────────

    if args.command == "security":
        from maa_x.security import ThreatDetector, ThreatLedger, redact_pii

        if args.sec_cmd == "scan":
            detector = ThreatDetector()
            results = detector.scan(args.content)
            if results:
                print(f"⚠ Threats found: {len(results)}")
                for r in results:
                    print(f"  [{r.severity.upper()}] {r.threat_type}: '{r.matched_pattern}'")
            else:
                print("✓ No threats detected")
            pii_found = detector.scan_pii(args.content)
            if pii_found:
                print(f"PII detected: {len(pii_found)} type(s)")
                for pii_type, matched, _ in pii_found:
                    print(f"  {pii_type}: {matched[:30]}")
            return 0

        if args.sec_cmd == "redact":
            result = redact_pii(args.content)
            print(result)
            return 0

    # ── Worker ───────────────────────────────────────────────────────────────

    if args.command == "worker":
        if args.worker_cmd == "start":
            from maa_x.workers import BackgroundWorker
            worker = BackgroundWorker(num_workers=args.num_workers)
            worker.start()
            print(f"✓ Worker pool started with {args.num_workers} workers")
            return 0

        if args.worker_cmd == "status":
            print("Worker pool: status endpoint not yet wired (results store pending)")
            return 0

    # ── Memory ───────────────────────────────────────────────────────────────

    if args.command == "memory":
        from maa_x.memory import AgentDB
        db = AgentDB()
        if args.mem_cmd == "namespaces":
            namespaces = db.list_namespaces()
            print(f"Namespaces: {len(namespaces)}")
            for ns in namespaces:
                print(f"  {ns}")
            return 0

        if args.mem_cmd == "stats":
            db2 = AgentDB()
            namespaces = db2.list_namespaces()
            total = sum(db2._conn.execute(f"SELECT COUNT(*) FROM memories WHERE namespace = ?", (ns,)).fetchone()[0] for ns in namespaces)
            print(f"Namespaces: {len(namespaces)}")
            print(f"Total memories: {total}")
            db2.close()
            return 0

    # ── Governance ────────────────────────────────────────────────────────────

    if args.command == "governance":
        from maa_x.persistence import SQLiteBackend
        db = SQLiteBackend()
        if args.gov_cmd == "approvals":
            rows = db.conn.execute("SELECT approval_id, tenant_id, action, risk_score, approved FROM approvals").fetchall()
            print(f"Approvals: {len(rows)}")
            for r in rows:
                print(f"  [{'✓' if r[4] else '✗'}] {r[0][:8]}...  tenant={r[1]}  action={r[2]}  risk={r[3]:.2f}")
            return 0

        if args.gov_cmd == "audit":
            rows = db.conn.execute(
                f"SELECT event_id, tenant_id, event_type, payload FROM audit_events{' WHERE tenant_id = ?' if args.tenant else ''} ORDER BY ROWID DESC LIMIT 20",
                (([args.tenant]) if args.tenant else []),
            ).fetchall()
            print(f"Audit events (last 20): {len(rows)}")
            for r in rows:
                print(f"  {r[0][:8]}...  tenant={r[1]}  {r[2]}  {r[3][:60]}")
            return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())