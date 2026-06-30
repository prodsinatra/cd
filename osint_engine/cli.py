"""Minimal CLI for ad-hoc trigger evaluation.

Usage:
    python -m osint_engine.cli --query "..." [--context "..."] \\
        [--tool name] [--previous-results-file path] [--config config.json]

Prints the alert banner if one fires, or "OK" if the query was a silent
allow. Exits non-zero on BLOCK so it composes with shell pipelines.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from osint_engine.config import EngineConfig, load_config
from osint_engine.engine import TriggerEngine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="osint-engine")
    parser.add_argument("--query", required=True)
    parser.add_argument("--context", default="")
    parser.add_argument("--tool", default="cli")
    parser.add_argument("--previous-results-file", default=None)
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)

    config: EngineConfig
    if args.config:
        config = load_config(args.config)
    else:
        config = EngineConfig()

    previous = ""
    if args.previous_results_file:
        previous = Path(args.previous_results_file).read_text()

    engine = TriggerEngine(config)
    decision = engine.evaluate(
        query=args.query,
        context=args.context,
        tool_name=args.tool,
        previous_results=previous,
    )

    if decision.banner:
        print(decision.banner)
    else:
        print("OK — no alert fired.")

    return 1 if decision.action == "BLOCK" else 0


if __name__ == "__main__":
    sys.exit(main())
