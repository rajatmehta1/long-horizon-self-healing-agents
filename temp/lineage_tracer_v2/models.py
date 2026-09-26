"""Step 2 - Data shapes. Agents fill these in; code turns them into cited records."""
from typing import Literal, Optional

from pydantic import BaseModel, Field


class Symbol(BaseModel):
    repo: str = Field(description="Exact Sourcegraph repo name, e.g. github.com/acme/billing-service")
    path: str
    name: str
    line: Optional[int] = None

    @property
    def id(self) -> str:
        return f"{self.repo}:{self.path}:{self.name}"


class DiscoveryResult(BaseModel):
    symbols: list[Symbol] = []


class Loc(BaseModel):
    """Where something was seen. Line numbers must be copied from read_file output."""
    path: str
    start_line: int
    end_line: int


class Edge(BaseModel):
    source: str
    target: str
    relation: Literal["produces", "uses", "stored_in", "ingested_from"]
    access: Literal["write", "read"]
    formula: Optional[str] = Field(None, description="Exact calculation, if any")
    loc: Loc


class Boundary(BaseModel):
    """A point where data enters or leaves the repository."""
    direction: Literal["in", "out"]
    channel: Literal["table", "topic", "api", "file", "package"]
    name: str = Field(description="Fully qualified: table:schema.table.column, kafka:topic, GET /api/path")
    carries: list[str] = Field(default_factory=list, description="Fields that cross this boundary")
    loc: Loc


class TraceResult(BaseModel):
    edges: list[Edge] = []
    boundaries: list[Boundary] = []
    new_symbols: list[Symbol] = Field(default_factory=list,
                                      description="Symbols in THIS repo that still need tracing")


class InputDraft(BaseModel):
    name: str
    origin: Literal["ingested", "computed", "constant", "unresolved"]
    source: Optional[str] = Field(None, description="ingested: the boundary name; computed: the variable it is computed as")
    loc: Optional[Loc] = Field(None, description="Where this input is read or defined")


class OutputDraft(BaseModel):
    name: str
    stored_in: list[str] = Field(default_factory=list, description="Boundary names the result is written to")
    loc: Optional[Loc] = Field(None, description="Where the result is written or returned")


class CalculationDraft(BaseModel):
    formula: str
    loc: Loc = Field(description="The lines where the calculation happens")
    inputs: list[InputDraft] = []
    output: OutputDraft


class RepoProfile(BaseModel):
    role: Literal["producer", "consumer", "producer+consumer", "source of inputs", "pass-through"]
    summary: str
    calculations: list[CalculationDraft] = []


class Handoff(BaseModel):
    from_repo: str
    to_repo: str
    via: str
    carries: list[str] = []
    match: Literal["exact", "fuzzy"] = "fuzzy"


class ConnectorResult(BaseModel):
    extra_handoffs: list[Handoff] = []
    conflicts: list[str] = []
