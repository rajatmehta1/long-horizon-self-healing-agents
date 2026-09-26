"""Test 2 - Contract check: are the Sourcegraph MCP tools we rely on there, and do they answer?

    python check_tools.py                 # list tools and their arguments
    python check_tools.py net_revenue     # also run one real keyword_search
"""
import asyncio
import json
import sys

from agents import load_sourcegraph_tools, tool_named
from citations import as_text

REQUIRED = ["keyword_search", "read_file", "go_to_definition", "find_references"]
OPTIONAL = ["commit_search"]   # used to pin citations to a commit; falls back to HEAD


async def main(query: str | None):
    tools = await load_sourcegraph_tools()
    print("Tools on this server:", sorted(t.name for t in tools), "\n")

    missing = []
    for name in REQUIRED + OPTIONAL:
        t = tool_named(tools, name)
        status = "ok" if t else ("MISSING" if name in REQUIRED else "missing (optional)")
        print(f"{name:18} {status}")
        if t:
            print("   args:", json.dumps(t.args)[:300])
        elif name in REQUIRED:
            missing.append(name)

    if query:
        kw = tool_named(tools, "keyword_search")
        key = "query" if "query" in kw.args else next(iter(kw.args))
        out = as_text(await kw.ainvoke({key: query}))
        print(f"\nkeyword_search({key}={query!r}) returned {len(out)} chars:\n{out[:800]}")

    if missing:
        sys.exit(f"\nMissing required tools: {missing}. Use the /.api/mcp/all endpoint.")
    print("\nContract OK")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
