"""Step 7 - The main graph: discover -> one subgraph per repo -> connector -> report."""
import json
import operator
from typing import Annotated

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from typing_extensions import TypedDict

from agents import Agents, run_agent, run_llm
from citations import resolve_revision
from config import MAX_REPOS, MAX_SYMBOLS
from linking import link_calculations, match_boundaries
from prompts import CONNECTOR_PROMPT
from repo_graph import build_repo_graph
from report import write_reports


class MainState(TypedDict):
    element: str
    aliases: list[str]
    verify: bool
    by_repo: dict[str, list[dict]]
    repo_reports: Annotated[list[dict], operator.add]   # each repo appends its own report
    handoffs: list[dict]
    conflicts: list[str]


class RepoJob(TypedDict):
    element: str
    repo: str
    symbols: list[dict]
    verify: bool


def build_main_graph(agents: Agents, catalog: dict, out_dir: str):

    async def discover(state: MainState):
        res = await run_agent(agents.discovery,
                              f"Business element: {state['element']}\n"
                              f"Aliases: {', '.join(state['aliases'])}")
        by_repo: dict[str, list[dict]] = {}
        for s in res.symbols:
            by_repo.setdefault(s.repo, []).append(s.model_dump())
        by_repo = {r: syms[:MAX_SYMBOLS] for r, syms in list(by_repo.items())[:MAX_REPOS]}
        print(f"[discover] found the element in {len(by_repo)} repos: {list(by_repo)}")
        return {"by_repo": by_repo}

    def fan_out(state: MainState):
        if not state["by_repo"]:
            return ["report"]
        return [Send("repo_trace", {"element": state["element"], "repo": r,
                                    "symbols": syms, "verify": state["verify"]})
                for r, syms in state["by_repo"].items()]

    async def repo_trace(job: RepoJob):
        revision = await resolve_revision(agents.tools, job["repo"])
        print(f"[repo] tracing {job['repo']} @ {revision[:12]}")
        graph = build_repo_graph(agents, job["repo"], revision, job["verify"])
        final = await graph.ainvoke({
            "element": job["element"], "repo": job["repo"], "revision": revision,
            "frontier": job["symbols"], "visited": [], "edges": [], "boundaries": [],
            "depth": 0, "role": "", "summary": "", "calculations": [],
        })
        meta = catalog.get(job["repo"], {})
        return {"repo_reports": [{
            "repo": job["repo"],
            "system": meta.get("system", "unknown - add to repos.yaml"),
            "owner": meta.get("owner", "unknown"),
            "revision": revision,
            "role": final["role"],
            "summary": final["summary"],
            "calculations": final["calculations"],
            "boundaries": final["boundaries"],   # grounded, straight from the tracers
            "edges": final["edges"],
        }]}

    async def connector(state: MainState):
        exact = match_boundaries(state["repo_reports"])
        payload = json.dumps({
            "element": state["element"],
            "repos": [{"repo": r["repo"], "role": r["role"],
                       "calculations": [{"formula": c["formula"], "output": c["output"]["name"]}
                                        for c in r["calculations"]],
                       "boundaries": [{k: b[k] for k in ("direction", "channel", "name")}
                                      for b in r["boundaries"]]}
                      for r in state["repo_reports"]],
            "exact_handoffs": exact,
        }, indent=1)
        res = await run_llm(agents.connector, CONNECTOR_PROMPT, payload)
        return {"handoffs": exact + [h.model_dump() for h in res.extra_handoffs],
                "conflicts": res.conflicts}

    async def report(state: MainState):
        handoffs = state.get("handoffs", [])
        reports = link_calculations(state.get("repo_reports", []), handoffs)
        write_reports(state["element"], reports, handoffs, state.get("conflicts", []), out_dir)
        return {}

    g = StateGraph(MainState)
    g.add_node("discover", discover)
    g.add_node("repo_trace", repo_trace)
    g.add_node("connector", connector)
    g.add_node("report", report)
    g.add_edge(START, "discover")
    g.add_conditional_edges("discover", fan_out, ["repo_trace", "report"])
    g.add_edge("repo_trace", "connector")     # waits for every repo to finish
    g.add_edge("connector", "report")
    g.add_edge("report", END)
    return g.compile()
