"""Step 5 - Citations: pin a revision, build Sourcegraph links, verify lines against the file."""
import re
from urllib.parse import quote

from config import REVISION, SG_ENDPOINT

SHA_RE = re.compile(r"\b[0-9a-f]{40}\b")
LINE_RE = re.compile(r"^\s*(\d+)[\s:|]\s?(.*)$")
IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def as_text(out) -> str:
    """MCP tool results may be a string or a list of content blocks."""
    if isinstance(out, str):
        return out
    if isinstance(out, list):
        return "\n".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in out)
    return str(out)


async def resolve_revision(tools, repo: str) -> str:
    """LINEAGE_REVISION if set; else the newest commit sha commit_search returns; else HEAD."""
    if REVISION:
        return REVISION
    tool = next((t for t in tools if "commit_search" in t.name), None)
    if tool:
        try:
            m = SHA_RE.search(as_text(await tool.ainvoke({"repos": [repo]})))
            if m:
                return m.group(0)
        except Exception as e:
            print(f"  [{repo}] could not resolve commit ({e}); using HEAD")
    return "HEAD"


def build_url(repo: str, revision: str, path: str, start: int, end: int) -> str:
    rev = "" if revision in ("", "HEAD") else f"@{revision}"
    return f"{SG_ENDPOINT}/{repo}{rev}/-/blob/{quote(path)}?L{start}-{end}"


def make_citation(repo: str, revision: str, loc: dict | None) -> dict | None:
    """Turn an agent's loc into a pinned, linkable citation. Bad line numbers -> None."""
    if not loc or not loc.get("path"):
        return None
    try:
        start = int(loc["start_line"])
        end = int(loc.get("end_line") or start)
    except (KeyError, TypeError, ValueError):
        return None
    if start < 1 or end < start:
        return None
    return {"repo": repo, "path": loc["path"], "start_line": start, "end_line": end,
            "commit": revision, "url": build_url(repo, revision, loc["path"], start, end),
            "verified": None}


def finalize_calculation(repo: str, revision: str, draft: dict) -> dict | None:
    """Agent draft -> cited calculation record. Drops drafts without a valid main citation."""
    cite = make_citation(repo, revision, draft.get("loc"))
    if cite is None:
        return None
    short = repo.rstrip("/").split("/")[-1]
    out = draft["output"]
    return {
        "id": f"calc:{short}:{cite['path']}:{cite['start_line']}",
        "formula": draft["formula"],
        "citation": cite,
        "inputs": [{"name": i["name"], "origin": i["origin"], "source": i.get("source"),
                    "citation": make_citation(repo, revision, i.get("loc")), "computed_by": []}
                   for i in draft.get("inputs", [])],
        "output": {"name": out["name"], "stored_in": out.get("stored_in", []),
                   "citation": make_citation(repo, revision, out.get("loc"))},
        "feeds": [],
    }


def numbered_lines(text: str) -> dict[int, str]:
    """Parse read_file output into {line_number: text}, numbered or not."""
    raw = text.splitlines()
    matches = [LINE_RE.match(line) for line in raw]
    non_empty = [line for line in raw if line.strip()]
    if non_empty and sum(1 for m in matches if m) >= 0.6 * len(non_empty):
        return {int(m.group(1)): m.group(2) for m in matches if m}
    return {i: line for i, line in enumerate(raw, 1)}


def supports(lines: dict[int, str], start: int, end: int, names: list[str], slack: int = 2) -> bool:
    """True if any of the names appears within the cited lines (+/- slack)."""
    window = " ".join(lines.get(i, "") for i in range(max(1, start - slack), end + slack + 1))
    return any(re.search(rf"\b{re.escape(n)}\b", window, re.IGNORECASE) for n in names if n)


async def verify_calculation(read_tool, calc: dict, revision: str, cache: dict) -> None:
    """Re-read each cited file and mark citations verified True/False (None = could not check)."""

    async def lines_for(cite):
        key = (cite["repo"], cite["path"])
        if key not in cache:
            args = {"repo": cite["repo"], "path": cite["path"]}
            if revision not in ("", "HEAD"):
                args["revision"] = revision
            try:
                cache[key] = numbered_lines(as_text(await read_tool.ainvoke(args)))
            except Exception as e:
                print(f"  could not read {key}: {e}")
                cache[key] = None
        return cache[key]

    async def check(cite, names):
        if cite:
            lines = await lines_for(cite)
            cite["verified"] = None if lines is None else supports(
                lines, cite["start_line"], cite["end_line"], names)

    await check(calc["citation"], [calc["output"]["name"], *IDENT_RE.findall(calc["formula"])])
    for inp in calc["inputs"]:
        await check(inp["citation"], [inp["name"]])
    await check(calc["output"]["citation"], [calc["output"]["name"]])
