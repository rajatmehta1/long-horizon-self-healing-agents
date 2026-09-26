"""Step 6 - The per-repository subgraph: trace waves -> profile -> verify citations."""
import asyncio
import json

from langgraph.graph import END, START, StateGraph
from typing_extensions import TypedDict

from agents import Agents, run_agent, run_llm, tool_named
from citations import finalize_calculation, verify_calculation
from config import MAX_DEPTH, MAX_SYMBOLS
from models import RepoProfile
from prompts import REPO_PROFILER_PROMPT


class RepoState(TypedDict):
    element: str
    repo: str
    revision: str
    frontier: list[dict]      # symbols to trace in the next wave
    visited: list[str]
    edges: list[dict]
    boundaries: list[dict]
    depth: int
    role: str
    summary: str
    calculations: list[dict]


def sid(s: dict) -> str:
    return f"{s['repo']}:{s['path']}:{s['name']}"


def build_repo_graph(agents: Agents, repo: str, revision: str, verify: bool = True):
    tracers = agents.tracers_for(repo, revision)
    read_tool = tool_named(agents.tools, "read_file")

    async def trace(state: RepoState):
        jobs = [(role, s) for s in state["frontier"] for role in tracers]
        results = await asyncio.gather(*[
            run_agent(tracers[role],
                      f"Business element: {state['element']}\nSymbol to trace: {json.dumps(s)}")
            for role, s in jobs
        ], return_exceptions=True)

        edges, boundaries = list(state["edges"]), list(state["boundaries"])
        seen_e = {(e["source"], e["target"], e["relation"]) for e in edges}
        seen_b = {(b["direction"], b["name"].lower()) for b in boundaries}
        visited = set(state["visited"]) | {sid(s) for s in state["frontier"]}
        next_wave = {}

        for (role, _), r in zip(jobs, results):
            if isinstance(r, Exception):
                print(f"  [{repo}] {role} failed: {r}")
                continue
            for e in r.edges:
                key = (e.source, e.target, e.relation)
                if key not in seen_e:
                    seen_e.add(key)
                    edges.append({**e.model_dump(), "found_by": role})
            for b in r.boundaries:
                key = (b.direction, b.name.lower())
                if key not in seen_b:
                    seen_b.add(key)
                    boundaries.append(b.model_dump())
            for s in r.new_symbols:
                if s.repo != repo:          # segregation guard: never leave this repo
                    continue
                if s.id not in visited:
                    next_wave[s.id] = s.model_dump()

        frontier = list(next_wave.values())[:MAX_SYMBOLS]
        print(f"  [{repo}] wave {state['depth'] + 1}: {len(edges)} edges, "
              f"{len(boundaries)} boundaries, {len(frontier)} queued")
        return {"edges": edges, "boundaries": boundaries, "visited": sorted(visited),
                "frontier": frontier, "depth": state["depth"] + 1}

    def keep_going(state: RepoState):
        return "trace" if state["frontier"] and state["depth"] < MAX_DEPTH else "profile"

    async def profile(state: RepoState):
        payload = json.dumps({"repo": repo, "element": state["element"],
                              "edges": state["edges"], "boundaries": state["boundaries"]},
                             indent=1)
        prof: RepoProfile = await run_llm(agents.repo_profiler, REPO_PROFILER_PROMPT, payload)
        calcs = [finalize_calculation(repo, state["revision"], c.model_dump())
                 for c in prof.calculations]
        return {"role": prof.role, "summary": prof.summary,
                "calculations": [c for c in calcs if c]}

    async def verify_citations(state: RepoState):
        if not (verify and read_tool):
            return {}
        cache: dict = {}
        calcs = [dict(c) for c in state["calculations"]]
        for c in calcs:
            await verify_calculation(read_tool, c, state["revision"], cache)
        ok = sum(1 for c in calcs if c["citation"]["verified"])
        print(f"  [{repo}] citations verified: {ok}/{len(calcs)} calculations")
        return {"calculations": calcs}

    g = StateGraph(RepoState)
    g.add_node("trace", trace)
    g.add_node("profile", profile)
    g.add_node("verify", verify_citations)
    g.add_edge(START, "trace")
    g.add_conditional_edges("trace", keep_going, ["trace", "profile"])
    g.add_edge("profile", "verify")
    g.add_edge("verify", END)
    return g.compile()
