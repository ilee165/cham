"""
cham-reconcile cli entry point

Usage (installed script, or `python -m cham.ddi-reconciler.cli`):
    cham-reconcile --dry-run # print diff, exit if drift found (CI signal)
    cham-reconcile --apply # apply changes to the cluster
"""
import sys
import argparse

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="cham-reconcile",
        description="cham-reconcile cli",
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="print diff, exit if drift found (CI signal)",
    )
    mode_group.add_argument(
        "--apply",
        action="store_true",
        help="apply changes to the cluster",
    )
    parser.parse_args()

    print (
        "Error: reconciliation providers are not implemented (Phase 4).",
        file=sys.stderr,
    )
    return 1

if __name__ == "__main__":
    sys.exit(main())
