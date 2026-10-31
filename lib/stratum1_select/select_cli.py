"""Command line for roko-stratum1-select: measure, choose and optionally install stratum-1 sources."""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

from stratum1_select.candidate_ranking import choose_sources, measure_all
from stratum1_select.chrony_sources import (InstallBlocked, find_sourcedir, install_sources,
                                            render_sources)

TOOLS_ROOT = Path(__file__).resolve().parents[2]
CATALOG = TOOLS_ROOT / "installer" / "stratum1-candidates.json"
EXIT_OK, EXIT_USAGE, EXIT_NONE_ELIGIBLE, EXIT_INSTALL_BLOCKED = 0, 2, 3, 4


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="roko-stratum1-select",
        description="Measure public stratum-1 NTP servers from this host, pick the nearest healthy ones "
                    "and print (or, with --install, apply) a Chrony sources file. Never steps the clock.")
    parser.add_argument("--candidate", action="append", default=[], metavar="HOST",
                        help="extra candidate server (repeatable), e.g. a nearby national time lab")
    parser.add_argument("--only-candidates", action="store_true", help="ignore the bundled catalog")
    parser.add_argument("--region", help="limit the bundled catalog to one region (americas, europe, asia)")
    parser.add_argument("--count", type=int, default=2, help="servers to select (1-4, default 2)")
    parser.add_argument("--samples", type=int, default=4, help="queries per server (2-8, default 4)")
    parser.add_argument("--spacing", type=float, default=4.0, help="seconds between queries to one server (min 2)")
    parser.add_argument("--timeout", type=float, default=2.0, help="seconds to wait for each reply")
    parser.add_argument("--json", action="store_true", help="print the measurements and choice as JSON")
    parser.add_argument("--install", action="store_true",
                        help="write the sources file into Chrony's sourcedir and reload sources (root)")
    return parser


def load_candidates(args) -> list[dict]:
    catalog = [] if args.only_candidates else json.loads(CATALOG.read_text())["candidates"]
    if args.region:
        catalog = [c for c in catalog if c["region"] == args.region]
    extra = [{"host": host, "operator": f"custom:{host}", "region": None} for host in args.candidate]
    return catalog + extra


def _validate(args) -> str | None:
    if not 1 <= args.count <= 4:
        return "--count must be 1-4"
    if not 2 <= args.samples <= 8:
        return "--samples must be 2-8"
    if args.spacing < 2:
        return "--spacing must be at least 2 seconds (be polite to public servers)"
    return None


def _print_table(ranked: list[dict], chosen: list[dict]) -> None:
    print(f"{'server':28} {'operator':10} {'stratum':>7} {'min RTT ms':>10}  status")
    for row in ranked:
        mark = "SELECTED" if row in chosen else ("ok" if row["eligible"] else row["reason"])
        print(f"{row['host'][:28]:28} {str(row.get('operator'))[:10]:10} {str(row.get('stratum', '-')):>7} "
              f"{str(row.get('minDelayMs', '-')):>10}  {mark}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    problem = _validate(args)
    candidates = load_candidates(args) if not problem else []
    if problem or not candidates:
        print(f"roko-stratum1-select: {problem or 'no candidates to measure'}", file=sys.stderr)
        return EXIT_USAGE
    ranked = measure_all(candidates, args.samples, args.spacing, args.timeout)
    chosen = choose_sources(ranked, args.count)
    generated = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    version = (TOOLS_ROOT / "VERSION").read_text().strip()
    sources_text = render_sources(chosen, generated, version) if chosen else ""
    if args.json:
        print(json.dumps({"schema": "roko.stratum1-selection.v1", "generatedAt": generated,
                          "ranked": ranked, "selected": [c["host"] for c in chosen],
                          "chronySources": sources_text}, indent=2))
    else:
        _print_table(ranked, chosen)
    if not chosen:
        print("roko-stratum1-select: no reachable stratum-1 server; check outbound UDP 123 "
              "or add a nearby server with --candidate", file=sys.stderr)
        return EXIT_NONE_ELIGIBLE
    if not args.install:
        if not args.json:
            print("\nChrony sources (preview; apply with sudo roko-stratum1-select --install):\n")
            print(sources_text, end="")
        return EXIT_OK
    return _install(sources_text, [c["host"] for c in chosen])


def _install(sources_text: str, hosts: list[str]) -> int:
    try:
        result = install_sources(sources_text, hosts, find_sourcedir())
    except InstallBlocked as blocked:
        print(f"roko-stratum1-select: {blocked}", file=sys.stderr)
        print(sources_text, end="", file=sys.stderr)
        return EXIT_INSTALL_BLOCKED
    print(f"\ninstalled {result['path']}" + (f" (previous kept at {result['backup']})" if result["backup"] else ""))
    if result["missingAfterReload"]:
        print("warning: chronyc does not list " + ", ".join(result["missingAfterReload"]) + " yet", file=sys.stderr)
    print("next: watch 'chronyc sources' for a few polls, then schedule checks with roko-stratum1-schedule")
    return EXIT_OK
