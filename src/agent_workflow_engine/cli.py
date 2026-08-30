"""Installed CLI entry point for Agent Workflow Engine."""
from __future__ import annotations

import argparse
import asyncio
import json

from adapters import RagHttpTool
from engine import main as demo_main
from portfolio_pipeline import run_portfolio_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(prog="agent-workflow")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("demo", help="run the deterministic workflow demo")
    portfolio = subparsers.add_parser("portfolio", help="run the RAG portfolio pipeline")
    portfolio.add_argument("query")
    portfolio.add_argument("--rag-url", default="http://127.0.0.1:8000")
    portfolio.add_argument("--top-k", type=int, default=3)
    args = parser.parse_args()

    if args.command in {None, "demo"}:
        demo_main()
        return
    if args.command == "portfolio":
        result = asyncio.run(
            run_portfolio_pipeline(
                args.query,
                RagHttpTool(args.rag_url),
                top_k=args.top_k,
            )
        )
        print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
