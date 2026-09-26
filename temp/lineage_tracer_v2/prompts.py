"""Step 3 - What each agent is told. Search is keyword_search only (no nls_search)."""
import re

from config import MAX_SYMBOLS

GROUNDING = ("Every path and line number you return MUST be copied from a read_file result. "
             "Never guess. If you cannot confirm something, leave it out.")

SEARCH_RECIPES = """You only have keyword_search (no semantic search), so search literally:
- Each alias on its own: net_revenue, netRevenue, NET_REVENUE, net-revenue.
- Add filters to cut noise: lang:sql, lang:python, lang:java, -file:test, -file:mock, -file:fixture.
- Assignments: "net_revenue =", "AS net_revenue", "netRevenue:", "netRevenue =".
- Writes: INSERT INTO, to_sql(, .write, produce(, publish(, .save(, @Column.
- Reads: FROM, read_sql, consume(, subscribe(, requests.get, @GetMapping.
- Pair a write/read recipe with the element or table name, or restrict to a file with file:^path$.
Open promising hits with read_file before you report them."""

DISCOVERY_PROMPT = f"""You locate every place a business element appears in code, across ALL repositories.
{SEARCH_RECIPES}
Keep assignments, calculations, SQL columns/aliases, model fields and meaningful reads.
Skip tests, mocks, fixtures and vendored code.
Use the exact repository name Sourcegraph returns (e.g. github.com/acme/billing-service).
Return at most {MAX_SYMBOLS} symbols per repository. {GROUNDING}"""


def scope_rules(repo: str, revision: str) -> str:
    """Rules that fence an agent inside ONE repository at ONE revision."""
    rev_rule = ("" if revision == "HEAD" else
                f"\n- Pass revision `{revision}` to read_file, go_to_definition and find_references.")
    return f"""SCOPE: you work ONLY inside repository `{repo}`.
- Add `repo:^{re.escape(repo)}$` to every keyword_search query.{rev_rule}
- Only read files and follow symbols in this repository.
- When data ENTERS or LEAVES this repository (table/column, queue topic, API endpoint,
  file, or a package from another repo), record a Boundary with a fully qualified name
  and DO NOT follow it further.
- Every Edge and Boundary needs a loc: path, start_line, end_line from read_file.
{SEARCH_RECIPES}
- {GROUNDING}"""


UPSTREAM_PROMPT = """You find how the element is PRODUCED in this repository.
1. Open each place where it is assigned or computed (read_file; go_to_definition if you only have a usage).
2. Record edge input -> element, relation 'produces', access 'write', with the exact formula and its loc.
3. If a value simply arrives from outside the repo, record an 'in' Boundary instead.
4. Put inputs that are themselves computed in this repo into new_symbols."""

DOWNSTREAM_PROMPT = """You find where the element is USED in this repository.
1. Call find_references on its definition. Ignore references in other repositories;
   if there are some, record one 'out' Boundary with channel 'package'.
2. read_file around each in-repo reference.
3. Record edge element -> consumer, relation 'uses', access 'read', with its loc. If the consumer
   transforms the value, include the formula and add the consumer to new_symbols."""

STORAGE_PROMPT = """You find how the element and its inputs are STORED or INGESTED in this repository.
Look at SQL, dbt models, ORM models, migrations, ETL/Airflow jobs, queue producers and
consumers, API handlers, and file readers/writers.
- Writing to a table/topic/file/API -> 'out' Boundary plus a 'stored_in' edge (access 'write').
- Reading from one -> 'in' Boundary plus an 'ingested_from' edge (access 'read').
Always use fully qualified names: table:schema.table.column, kafka:topic, GET /api/path."""

REPO_PROFILER_PROMPT = """You turn ONE repository's findings into calculation records,
using ONLY the edges and boundaries given to you.
- role: producer (computes the element), consumer (only reads it), producer+consumer,
  source of inputs (supplies its inputs but never computes it), or pass-through (moves it unchanged).
- calculations: one per DISTINCT formula found in 'produces' edges. For each:
  - formula and loc: copied from the edge.
  - inputs: every variable in the formula. origin = 'ingested' if an 'in' boundary or an
    'ingested_from' edge carries it (source = that boundary name); 'computed' if another
    'produces' edge creates it (source = its name); 'constant' for literals; else 'unresolved'.
    loc = where the input is read or defined, if an edge or boundary gives it.
  - output: the variable/column the formula assigns. stored_in = names of 'out' boundaries or
    'stored_in' edges that write it; loc = where it is written.
- summary: one or two plain sentences.
Copy every loc exactly. Never add facts that are not in the input."""

CONNECTOR_PROMPT = """You connect per-repository lineage reports for one business element.
Input: each repo's role, calculations and boundaries, plus handoffs already matched by exact name.
1. extra_handoffs: add links where one repo's 'out' boundary and another repo's 'in' boundary
   clearly refer to the same table/topic/API but are named slightly differently
   (e.g. fct_orders vs analytics.fct_orders). Do not repeat exact matches. Set match='fuzzy'.
2. conflicts: where repos compute the element with DIFFERENT formulas, write one sentence
   naming the repos and the difference.
Only use what is in the input."""
