"""Step 8 - Run it.

    python run.py net_revenue --alias netRevenue --alias NET_REVENUE
"""
import argparse
import asyncio
import sys

from agents import Agents, load_sourcegraph_tools
from config import SG_ENDPOINT, SG_TOKEN, load_repo_catalog
from main_graph import build_main_graph


async def main(element: str, aliases: list[str], catalog_path: str, out_dir: str, verify: bool):
    if not SG_ENDPOINT or not SG_TOKEN:
        sys.exit("Set SRC_ENDPOINT and SRC_ACCESS_TOKEN first.")

    tools = await load_sourcegraph_tools()
    print("[mcp] tools:", [t.name for t in tools])

    graph = build_main_graph(Agents(tools), load_repo_catalog(catalog_path), out_dir)
    await graph.ainvoke({"element": element, "aliases": aliases, "verify": verify,
                         "by_repo": {}, "repo_reports": [], "handoffs": [], "conflicts": []})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Trace a business element, separated by repository")
    p.add_argument("element")
    p.add_argument("--alias", action="append", default=[])
    p.add_argument("--repos", default="repos.yaml")
    p.add_argument("--out", default=None)
    p.add_argument("--no-verify", action="store_true", help="skip re-reading cited lines")
    a = p.parse_args()
    asyncio.run(main(a.element, [a.element, *a.alias], a.repos,
                     a.out or f"lineage_{a.element}", not a.no_verify))
