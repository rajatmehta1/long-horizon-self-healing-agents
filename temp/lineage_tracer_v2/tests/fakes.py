"""Fake agents and tools so the whole graph runs offline, with no LLM and no Sourcegraph."""
from models import (Boundary, CalculationDraft, ConnectorResult, DiscoveryResult, Edge,
                    InputDraft, Loc, OutputDraft, RepoProfile, Symbol, TraceResult)

A = "github.com/acme/data-pipeline"
B = "github.com/acme/finance-dashboard"
SHA = "a" * 40

FILES = {
    (A, "models/fct_orders.sql"): "\n".join(
        [f"{n}  -- filler" for n in range(1, 40)]
        + ["40  select", "41    order_id,", "42    gross_amount - discount_amount - refund_amount as net_revenue",
           "43  from stg_orders", "44  join stg_refunds using (order_id)"]),
    (A, "models/stg_orders.sql"): "1  select gross_amount, discount_amount from {{ source('kafka', 'orders_v2') }}",
    (B, "metrics/revenue.py"): "\n".join([f"{n}  # filler" for n in range(1, 88)]
                                         + ["88  net_revenue = (gross_amount - discount_amount) / 1.2"]),
}


class FakeTool:
    def __init__(self, name, fn):
        self.name, self._fn, self.args = name, fn, {}

    async def ainvoke(self, args):
        return self._fn(args)


TOOLS = [
    FakeTool("sg_commit_search", lambda a: f"commit {SHA} Merge pull request #12"),
    FakeTool("sg_read_file", lambda a: FILES.get((a["repo"], a["path"]), "")),
]


class FakeAgents:
    discovery, repo_profiler, connector = "discovery", "profiler", "connector"
    tools = TOOLS

    def tracers_for(self, repo, revision):
        return {r: (r, repo) for r in ("upstream", "downstream", "storage")}


def loc(path, s, e=None):
    return Loc(path=path, start_line=s, end_line=e or s)


async def fake_run_agent(agent, text):
    if agent == "discovery":
        return DiscoveryResult(symbols=[Symbol(repo=A, path="models/fct_orders.sql", name="net_revenue"),
                                        Symbol(repo=B, path="metrics/revenue.py", name="net_revenue")])
    role, repo = agent
    if repo == A and role == "upstream":
        return TraceResult(
            edges=[Edge(source="gross_amount", target="net_revenue", relation="produces", access="write",
                        formula="gross_amount - discount_amount - refund_amount",
                        loc=loc("models/fct_orders.sql", 42))],
            new_symbols=[Symbol(repo=B, path="leak.py", name="x"),        # must be dropped
                         Symbol(repo=A, path="models/stg_orders.sql", name="gross_amount")])
    if repo == A and role == "storage":
        return TraceResult(boundaries=[
            Boundary(direction="in", channel="topic", name="kafka:orders.v2",
                     carries=["gross_amount"], loc=loc("models/stg_orders.sql", 1)),
            Boundary(direction="out", channel="table", name="analytics.fct_orders.net_revenue",
                     loc=loc("models/fct_orders.sql", 40, 44))])
    if repo == B and role == "storage":
        return TraceResult(boundaries=[
            Boundary(direction="in", channel="table", name="analytics.fct_orders.net_revenue",
                     loc=loc("metrics/revenue.py", 10))])
    return TraceResult()


async def fake_run_llm(llm, system, text):
    if llm == "connector":
        return ConnectorResult(conflicts=["finance-dashboard drops refunds and strips VAT"])
    if A in text:
        return RepoProfile(role="producer", summary="Computes net_revenue in dbt.", calculations=[
            CalculationDraft(
                formula="gross_amount - discount_amount - refund_amount",
                loc=loc("models/fct_orders.sql", 42),
                inputs=[InputDraft(name="gross_amount", origin="ingested", source="kafka:orders.v2",
                                   loc=loc("models/stg_orders.sql", 1)),
                        InputDraft(name="refund_amount", origin="unresolved")],
                output=OutputDraft(name="net_revenue", stored_in=["table:analytics.fct_orders.net_revenue"],
                                   loc=loc("models/fct_orders.sql", 40, 44)))])
    return RepoProfile(role="producer+consumer", summary="Recomputes net_revenue.", calculations=[
        CalculationDraft(
            formula="(gross_amount - discount_amount) / 1.2",
            loc=loc("metrics/revenue.py", 88),
            inputs=[InputDraft(name="net_revenue", origin="ingested",
                               source="table:analytics.fct_orders.net_revenue",
                               loc=loc("metrics/revenue.py", 10))],
            output=OutputDraft(name="dashboard_net_revenue", loc=loc("metrics/revenue.py", 88))),
        CalculationDraft(formula="bad", loc=loc("metrics/revenue.py", 0),      # invalid line -> dropped
                         output=OutputDraft(name="x"))])
