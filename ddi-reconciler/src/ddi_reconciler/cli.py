"""cham-reconcile CLI.

Exit codes (contract used by nightly-drift CI — do not change casually):
  0 — converged (dry-run found no drift, or apply converged)
  1 — operational error (config, network, auth, convergence failure)
  2 — drift found (dry-run only)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from ddi_reconciler.config import Config, ConfigError, load_config
from ddi_reconciler.desired_file import load_desired, save_desired
from ddi_reconciler.model import CanonicalRecord, Diff
from ddi_reconciler.runner import ConvergenceError, apply_edge, plan_edge


def _build_providers(config: Config) -> dict:
    """Edge name -> constructed provider. Lazy imports keep file-mode dry-runs
    from paying the Azure SDK import cost. Tests monkeypatch this function."""
    from ddi_reconciler.providers.azure import AzureProvider
    from ddi_reconciler.providers.cloudflare import CloudflareProvider

    providers = {}
    for edge in config.edges:
        if edge.provider == "azure":
            providers[edge.name] = AzureProvider(
                subscription_id=os.environ["AZURE_SUBSCRIPTION_ID"],
                resource_group=config.azure_resource_group)
        elif edge.provider == "cloudflare":
            providers[edge.name] = CloudflareProvider(
                zone_name=edge.zone,
                api_token=os.environ["CLOUDFLARE_API_TOKEN"])
    return providers


def _fetch_desired(config: Config, args: argparse.Namespace) -> list[CanonicalRecord]:
    if args.desired_from_file:
        return load_desired(Path(args.desired_from_file))
    from ddi_reconciler.providers.spatium import SpatiumProvider
    spatium = SpatiumProvider(base_url=config.spatium_base_url,
                              token=os.environ.get("SPATIUM_API_TOKEN", ""))
    return spatium.fetch_desired({edge.zone for edge in config.edges})


def _print_diff(edge_name: str, diff: Diff) -> None:
    for r in sorted(diff.to_add, key=lambda r: r.key):
        print(f"[{edge_name}] ADD    {r.name} {r.rtype} {','.join(r.values)} ttl={r.ttl}")
    for u in sorted(diff.to_update, key=lambda u: u.desired.key):
        print(f"[{edge_name}] UPDATE {u.desired.name} {u.desired.rtype} "
              f"{','.join(u.actual.values)} ttl={u.actual.ttl} -> "
              f"{','.join(u.desired.values)} ttl={u.desired.ttl}")
    for r in sorted(diff.to_delete, key=lambda r: r.key):
        print(f"[{edge_name}] DELETE {r.name} {r.rtype} {','.join(r.values)} ttl={r.ttl}")
    if diff.is_converged:
        print(f"[{edge_name}] converged (0 changes)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cham-reconcile",
        description="Converge DNS edges toward SpatiumDDI truth")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="print diff; exit 2 on drift")
    mode.add_argument("--apply", action="store_true", help="apply changes, verify convergence")
    mode.add_argument("--export", metavar="PATH",
                      help="write SpatiumDDI truth snapshot as JSON and exit")
    parser.add_argument("--config", default="config.toml", help="path to config.toml")
    parser.add_argument("--desired-from-file", metavar="PATH",
                        help="read desired state from a JSON snapshot instead of SpatiumDDI (CI mode)")
    parser.add_argument("--edge", action="append", metavar="NAME",
                        help="limit to named edge(s); repeatable")
    args = parser.parse_args(argv)

    try:
        config = load_config(Path(args.config))

        if args.export:
            records = _fetch_desired(config, args)
            save_desired(records, Path(args.export))
            print(f"exported {len(records)} records to {args.export}")
            return 0

        edges = config.edges
        if args.edge:
            unknown = set(args.edge) - {e.name for e in edges}
            if unknown:
                raise ConfigError(f"unknown edge(s): {', '.join(sorted(unknown))}")
            edges = tuple(e for e in edges if e.name in set(args.edge))

        desired_all = _fetch_desired(config, args)
        providers = _build_providers(config)

        adds = updates = deletes = 0
        for edge in edges:
            run = apply_edge if args.apply else plan_edge
            result = run(edge, desired_all, providers[edge.name])
            _print_diff(edge.name, result.diff)
            adds += len(result.diff.to_add)
            updates += len(result.diff.to_update)
            deletes += len(result.diff.to_delete)

        drifted = bool(adds or updates or deletes)
        applied = " — applied" if args.apply and drifted else ""
        print(f"summary: {adds} add, {updates} update, {deletes} delete "
              f"across {len(edges)} edge(s){applied}")
        return 2 if (args.dry_run and drifted) else 0
    except (ConfigError, ConvergenceError, KeyError, OSError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
