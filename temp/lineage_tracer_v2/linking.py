"""Step 7 - Link repos (boundaries) and calculations (inputs <-> outputs) in plain code."""
import copy
import re


def norm(name: str) -> str:
    """net_revenue, netRevenue and NET-REVENUE all become netrevenue."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())


def match_boundaries(reports: list[dict]) -> list[dict]:
    """Exact-name match of one repo's 'out' boundary to another repo's 'in' boundary."""
    outs = [(r["repo"], b) for r in reports for b in r["boundaries"] if b["direction"] == "out"]
    ins = [(r["repo"], b) for r in reports for b in r["boundaries"] if b["direction"] == "in"]
    return [
        {"from_repo": src, "to_repo": dst, "via": f"{ob['channel']}:{ob['name']}",
         "carries": ob.get("carries", []), "match": "exact"}
        for src, ob in outs for dst, ib in ins
        if src != dst and ob["name"].lower() == ib["name"].lower()
    ]


def link_calculations(reports: list[dict], handoffs: list[dict]) -> list[dict]:
    """Fill inputs[].computed_by (trace up) and feeds (trace down). Returns new reports.

    An input links to a calculation whose output has the same (normalised) name,
    in the same repo first; across repos only when a handoff connects the two repos.
    """
    reports = copy.deepcopy(reports)
    connected = {(h["from_repo"], h["to_repo"]) for h in handoffs}
    producers: dict[str, list[tuple[str, dict]]] = {}
    for r in reports:
        for c in r["calculations"]:
            producers.setdefault(norm(c["output"]["name"]), []).append((r["repo"], c))

    for r in reports:
        for c in r["calculations"]:
            for inp in c["inputs"]:
                cands = [(repo, p) for repo, p in producers.get(norm(inp["name"]), [])
                         if p["id"] != c["id"]]
                same = [p for repo, p in cands if repo == r["repo"]]
                cross = [p for repo, p in cands if (repo, r["repo"]) in connected]
                inp["computed_by"] = [p["id"] for p in (same or cross)]
                for p in (same or cross):
                    if c["id"] not in p["feeds"]:
                        p["feeds"].append(c["id"])
    return reports


def trace_chain(reports: list[dict], calc_id: str, direction: str = "up") -> list[str]:
    """Every calculation upstream ('up') or downstream ('down') of calc_id, nearest first."""
    index = {c["id"]: c for r in reports for c in r["calculations"]}

    def nxt(cid):
        c = index[cid]
        if direction == "up":
            return [p for inp in c["inputs"] for p in inp["computed_by"]]
        return list(c["feeds"])

    seen, queue, order = {calc_id}, [calc_id], []
    while queue:
        for n in nxt(queue.pop(0)):
            if n not in seen and n in index:
                seen.add(n)
                order.append(n)
                queue.append(n)
    return order
