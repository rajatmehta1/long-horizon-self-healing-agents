from linking import link_calculations, match_boundaries, norm, trace_chain


def calc(cid, out, inputs):
    return {"id": cid, "formula": "f", "citation": {}, "feeds": [],
            "inputs": [{"name": n, "origin": "computed", "computed_by": []} for n in inputs],
            "output": {"name": out, "stored_in": []}}


def test_aliases_normalise():
    assert norm("net_revenue") == norm("netRevenue") == norm("NET-REVENUE")


def test_exact_boundary_match_creates_handoff():
    reports = [
        {"repo": "A", "boundaries": [{"direction": "out", "channel": "table", "name": "x.t.c"}]},
        {"repo": "B", "boundaries": [{"direction": "in", "channel": "table", "name": "X.T.C"}]},
    ]
    assert match_boundaries(reports) == [
        {"from_repo": "A", "to_repo": "B", "via": "table:x.t.c", "carries": [], "match": "exact"}]


def test_links_up_and_down_within_and_across_repos():
    reports = [
        {"repo": "A", "calculations": [calc("a1", "gross", []), calc("a2", "net_revenue", ["gross"])]},
        {"repo": "B", "calculations": [calc("b1", "margin", ["netRevenue"])]},
    ]
    linked = link_calculations(reports, [{"from_repo": "A", "to_repo": "B"}])
    assert trace_chain(linked, "b1", "up") == ["a2", "a1"]
    assert trace_chain(linked, "a1", "down") == ["a2", "b1"]


def test_no_cross_repo_link_without_a_handoff():
    reports = [
        {"repo": "A", "calculations": [calc("a1", "net_revenue", [])]},
        {"repo": "B", "calculations": [calc("b1", "margin", ["net_revenue"])]},
    ]
    linked = link_calculations(reports, [])
    assert linked[1]["calculations"][0]["inputs"][0]["computed_by"] == []
