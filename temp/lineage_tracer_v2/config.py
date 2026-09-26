"""Step 1 - Configuration: endpoints, limits, and the repo ownership map."""
import os
from pathlib import Path

import yaml

MODEL = os.getenv("LINEAGE_MODEL", "anthropic:claude-sonnet-5")
SUMMARY_MODEL = os.getenv("LINEAGE_SUMMARY_MODEL", "anthropic:claude-haiku-4-5-20251001")

SG_ENDPOINT = os.getenv("SRC_ENDPOINT", "").rstrip("/")
SG_URL = SG_ENDPOINT + "/.api/mcp/all"
SG_TOKEN = os.getenv("SRC_ACCESS_TOKEN", "")
REVISION = os.getenv("LINEAGE_REVISION", "")   # pin a branch or commit; empty = auto

MAX_DEPTH = int(os.getenv("LINEAGE_MAX_DEPTH", "3"))        # trace waves per repo
MAX_SYMBOLS = int(os.getenv("LINEAGE_MAX_SYMBOLS", "8"))    # symbols per wave per repo
MAX_REPOS = int(os.getenv("LINEAGE_MAX_REPOS", "10"))       # repos traced per run
CONCURRENCY = int(os.getenv("LINEAGE_CONCURRENCY", "4"))    # parallel LLM calls
TOOL_CALL_LIMIT = int(os.getenv("LINEAGE_TOOL_CALL_LIMIT", "25"))  # per agent run


def load_repo_catalog(path: str = "repos.yaml") -> dict:
    """Return {repo_name: {"system": ..., "owner": ...}}, or {} if the file is missing."""
    p = Path(path)
    if not p.exists():
        return {}
    return yaml.safe_load(p.read_text()) or {}
