"""Governance-focused maa-x CLI."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from importlib.metadata import PackageNotFoundError, version

from maa_protocol.persistence import SQLiteBackend


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="maa-x",
        description="Maa Protocol governance CLI",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("version", help="Print installed version")

    gov = sub.add_parser("governance", help="Inspect governance persistence")
    gov_sub = gov.add_subparsers(dest="gov_cmd")
    gov_approvals = gov_sub.add_parser("approvals", help="List approvals")
    gov_approvals.add_argument("--db", default=":memory:", help="SQLite database path")
    gov_audit = gov_sub.add_parser("audit", help="List audit events")
    gov_audit.add_argument("--db", default=":memory:", help="SQLite database path")
    gov_audit.add_argument("--tenant", default=None, help="Filter by tenant id")
    gov_audit.add_argument("--limit", type=int, default=20, help="Max events to show")

    swarm = sub.add_parser("swarm", help="Compatibility swarm commands")
    swarm_sub = swarm.add_subparsers(dest="swarm_cmd")
    swarm_init = swarm_sub.add_parser(
        "init",
        help="Initialize compatibility swarm metadata",
    )
    swarm_init.add_argument(
        "--topology",
        default="hierarchical",
        choices=["hierarchical", "mesh", "fanout"],
    )
    swarm_init.add_argument("--max-agents", type=int, default=8)
    swarm_init.add_argument(
        "--strategy",
        default="specialized",
        choices=["specialized", "generalist"],
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "version":
        try:
            print(f"maa-x {version('maa-protocol')}")
        except PackageNotFoundError:
            print("maa-x 0.3.1")
        return 0

    if args.command == "governance":
        if args.gov_cmd is None:
            parser.print_help()
            return 1
        backend = SQLiteBackend(args.db)
        try:
            if args.gov_cmd == "approvals":
                approvals = backend.list_approvals()
                print(f"Approvals: {len(approvals)}")
                for approval in approvals:
                    status = "approved" if approval.approved else "pending"
                    print(
                        f"- {approval.approval_id} tenant={approval.tenant_id} "
                        f"action={approval.action} status={status} risk={approval.risk_score:.2f}"
                    )
                return 0
            if args.gov_cmd == "audit":
                events = backend.list_audit_events(tenant_id=args.tenant, limit=args.limit)
                print(f"Audit events: {len(events)}")
                for event in events:
                    print(
                        f"- {event.event_id} tenant={event.tenant_id} "
                        f"type={event.event_type} payload={event.payload[:80]}"
                    )
                return 0
            print("Unknown governance command")
            return 1
        finally:
            backend.close()

    if args.command == "swarm":
        if args.swarm_cmd != "init":
            print("Unknown swarm command")
            return 1
        print("Swarm compatibility initialized")
        print(f"Topology: {args.topology}")
        print(f"Max agents: {args.max_agents}")
        print(f"Strategy: {args.strategy}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
