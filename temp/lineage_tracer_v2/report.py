"""Step 8 - Write report.json, report.md, systems.mmd and calculations.mmd."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path


def _cite(c: dict | None) -> str:
    if not c:
        return "no citation"
    mark = {True: "verified", False: "NOT verified", None: "unchecked"}[c.get("verified")]
    return f"[{c['path']}:{c['start_line']}-{c['end_line']}]({c['url']}) ({mark})"


def _store_key(name: str) -> str:
    """table:analytics.t.c and analytics.t.c are the same store."""
    return "store:" + re.sub(r"^(table|topic|api|file|package):", "", name.lower())


def _label(text: str) -> str:
    return str(text).replace('"', "'").replace("|", "/")


def write_reports(element: str, reports: list[dict], handoffs: list[dict],
                  conflicts: list[str], out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    reports = sorted(reports, key=lambda r: r["repo"])

    # 1. Machine-readable result
    (out / "report.json").write_text(json.dumps({
        "element": element, "generated_at": datetime.now(timezone.utc).isoformat(),
        "repositories": reports, "handoffs": handoffs, "conflicts": conflicts,
    }, indent=2))

    # 2. Human-readable report, one section per repository
    md = [f"# Lineage of `{element}`", ""]
    for r in reports:
        md += [f"## {r['repo']}",
               f"System: {r['system']} | Owner: {r['owner']} | Role: {r['role'] or '?'} | "
               f"Revision: `{r['revision'][:12]}`", "", r["summary"], ""]
        for c in r["calculations"]:
            md += [f"### `{c['output']['name']} = {c['formula']}`",
                   f"Calculated at {_cite(c['citation'])}", "", "Inputs:"]
            for i in c["inputs"]:
                src = f" from `{i['source']}`" if i.get("source") else ""
                up = f" <- {', '.join(i['computed_by'])}" if i["computed_by"] else ""
                md.append(f"- `{i['name']}`: {i['origin']}{src}{up} - {_cite(i['citation'])}")
            o = c["output"]
            stores = ", ".join(f"`{s}`" for s in o["stored_in"])
            where = f"stored in {stores}" if stores else "not stored in this repo"
            md += [f"Output: `{o['name']}` {where} - {_cite(o['citation'])}"]
            if c["feeds"]:
                md.append(f"Feeds: {', '.join(c['feeds'])}")
            md.append("")
        for b in r["boundaries"]:
            verb = "Reads from" if b["direction"] == "in" else "Writes to"
            md.append(f"- {verb} {b['channel']} `{b['name']}` ({b['loc']['path']}:{b['loc']['start_line']})")
        md.append("")
    md += ["## Handoffs between systems", ""]
    md += [f"- {h['from_repo']} -> {h['to_repo']} via `{h['via']}` ({h['match']})"
           for h in handoffs] or ["- none found"]
    md += ["", "## Conflicts", ""] + ([f"- {c}" for c in conflicts] or ["- none found"])
    (out / "report.md").write_text("\n".join(md))

    # 3. System map: one node per repo, one arrow per handoff
    rid = {r["repo"]: f"r{i}" for i, r in enumerate(reports)}
    sysmap = ["flowchart LR"]
    for r in reports:
        sysmap.append(f'  {rid[r["repo"]]}["{_label(r["system"])}<br/>'
                      f'{_label(r["repo"].split("/")[-1])}<br/>{_label(r["role"])}"]')
    for h in handoffs:
        if h["from_repo"] in rid and h["to_repo"] in rid:
            sysmap.append(f'  {rid[h["from_repo"]]} -->|"{_label(h["via"])}"| {rid[h["to_repo"]]}')
    (out / "systems.mmd").write_text("\n".join(sysmap))

    # 4. Calculation lineage: sources -> calculations -> stores, grouped per repo
    ids: dict[str, str] = {}

    def nid(key: str) -> str:
        return ids.setdefault(key, f"n{len(ids)}")

    calc = ["flowchart LR"]
    for r in reports:
        calc.append(f'  subgraph {rid[r["repo"]]}["{_label(r["repo"].split("/")[-1])}"]')
        for c in r["calculations"]:
            calc.append(f'    {nid(c["id"])}["{_label(c["output"]["name"])} = {_label(c["formula"])}"]')
        calc.append("  end")
    for r in reports:
        for c in r["calculations"]:
            for i in c["inputs"]:
                if i["origin"] == "ingested" and i.get("source"):
                    calc.append(f'  {nid(_store_key(i["source"]))}[("{_label(i["source"])}")] '
                                f'-->|{_label(i["name"])}| {nid(c["id"])}')
            for f in c["feeds"]:
                calc.append(f'  {nid(c["id"])} --> {nid(f)}')
            for s in c["output"]["stored_in"]:
                calc.append(f'  {nid(c["id"])} --> {nid(_store_key(s))}[("{_label(s)}")]')
    (out / "calculations.mmd").write_text("\n".join(calc))

    print(f"[report] wrote {out}/report.json, report.md, systems.mmd, calculations.mmd")
