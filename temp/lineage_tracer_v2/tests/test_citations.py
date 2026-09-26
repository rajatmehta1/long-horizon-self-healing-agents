from citations import build_url, finalize_calculation, make_citation, numbered_lines, supports


def test_url_is_pinned_to_commit():
    url = build_url("github.com/acme/x", "abc123", "models/a b.sql", 40, 44)
    assert url.endswith("/github.com/acme/x@abc123/-/blob/models/a%20b.sql?L40-44")


def test_url_without_pin_uses_default_branch():
    url = build_url("github.com/acme/x", "HEAD", "a.sql", 1, 1)
    assert "/github.com/acme/x/-/blob/a.sql?L1-1" in url


def test_bad_line_numbers_are_rejected():
    assert make_citation("r", "HEAD", {"path": "a.py", "start_line": 0, "end_line": 3}) is None
    assert make_citation("r", "HEAD", {"path": "a.py", "start_line": 9, "end_line": 3}) is None
    assert make_citation("r", "HEAD", None) is None


def test_calculation_without_valid_citation_is_dropped():
    draft = {"formula": "a+b", "loc": {"path": "x.py", "start_line": -1, "end_line": 2},
             "output": {"name": "c"}}
    assert finalize_calculation("github.com/acme/x", "HEAD", draft) is None


def test_numbered_and_plain_file_output_both_parse():
    assert numbered_lines("1  a\n2  b = c")[2] == "b = c"
    assert numbered_lines("a\nb = c")[2] == "b = c"


def test_supports_checks_the_cited_window():
    lines = {i: "" for i in range(1, 60)}
    lines[42] = "gross - disc as net_revenue"
    assert supports(lines, 42, 42, ["net_revenue"])
    assert supports(lines, 40, 40, ["net_revenue"])       # within slack
    assert not supports(lines, 10, 12, ["net_revenue"])   # wrong place
