"""End-to-end run of the real graphs with fake agents and tools."""
import asyncio
import json

import main_graph
import repo_graph
from tests import fakes


def run(tmp_path, monkeypatch, verify=True):
    for mod in (main_graph, repo_graph):
        monkeypatch.setattr(mod, "run_agent", fakes.fake_run_agent)
        monkeypatch.setattr(mod, "run_llm", fakes.fake_run_llm)
    catalog = {fakes.A: {"system": "Analytics warehouse", "owner": "@data-eng"}}
    graph = main_graph.build_main_graph(fakes.FakeAgents(), catalog, str(tmp_path))
    asyncio.run(graph.ainvoke({"element": "net_revenue", "aliases": ["net_revenue"], "verify": verify,
                               "by_repo": {}, "repo_reports": [], "handoffs": [], "conflicts": []}))
    return json.loads((tmp_path / "report.json").read_text())


def test_results_are_segregated_by_repo(tmp_path, monkeypatch):
    report = run(tmp_path, monkeypatch)
    repos = [r["repo"] for r in report["repositories"]]
    assert repos == sorted([fakes.A, fakes.B])
    for r in report["repositories"]:
        for c in r["calculations"]:
            assert c["citation"]["repo"] == r["repo"]


def test_calculation_has_pinned_citation_inputs_and_output(tmp_path, monkeypatch):
    report = run(tmp_path, monkeypatch)
    a = next(r for r in report["repositories"] if r["repo"] == fakes.A)
    (c,) = a["calculations"]
    assert c["citation"]["commit"] == fakes.SHA
    assert f"@{fakes.SHA}/-/blob/models/fct_orders.sql?L42-42" in c["citation"]["url"]
    assert c["citation"]["verified"] is True
    gross = next(i for i in c["inputs"] if i["name"] == "gross_amount")
    assert gross["origin"] == "ingested" and gross["source"] == "kafka:orders.v2"
    assert gross["citation"]["verified"] is True
    assert c["output"]["stored_in"] == ["table:analytics.fct_orders.net_revenue"]


def test_invalid_citations_are_dropped(tmp_path, monkeypatch):
    report = run(tmp_path, monkeypatch)
    b = next(r for r in report["repositories"] if r["repo"] == fakes.B)
    assert [c["formula"] for c in b["calculations"]] == ["(gross_amount - discount_amount) / 1.2"]


def test_repos_are_linked_by_handoff_and_calculations(tmp_path, monkeypatch):
    report = run(tmp_path, monkeypatch)
    assert {(h["from_repo"], h["to_repo"]) for h in report["handoffs"]} == {(fakes.A, fakes.B)}
    b = next(r for r in report["repositories"] if r["repo"] == fakes.B)
    assert b["calculations"][0]["inputs"][0]["computed_by"] == [
        "calc:data-pipeline:models/fct_orders.sql:42"]
    assert report["conflicts"]


def test_all_output_files_are_written(tmp_path, monkeypatch):
    run(tmp_path, monkeypatch, verify=False)
    for name in ("report.json", "report.md", "systems.mmd", "calculations.mmd"):
        assert (tmp_path / name).stat().st_size > 0
