"""Step 4 - Connect Sourcegraph MCP and build the agents with the create_agent harness."""
import asyncio

from langchain.agents import create_agent
from langchain.agents.middleware import (ModelRetryMiddleware, SummarizationMiddleware,
                                         ToolCallLimitMiddleware, ToolRetryMiddleware)
from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient

from config import CONCURRENCY, MODEL, SG_TOKEN, SG_URL, SUMMARY_MODEL, TOOL_CALL_LIMIT
from models import ConnectorResult, DiscoveryResult, RepoProfile, TraceResult
from prompts import (DISCOVERY_PROMPT, DOWNSTREAM_PROMPT, STORAGE_PROMPT,
                     UPSTREAM_PROMPT, scope_rules)

_limit = asyncio.Semaphore(CONCURRENCY)


async def load_sourcegraph_tools():
    client = MultiServerMCPClient({
        "sourcegraph": {
            "transport": "streamable_http",
            "url": SG_URL,
            "headers": {"Authorization": f"token {SG_TOKEN}"},
        }
    })
    return await client.get_tools()


def pick(tools, *names):
    """Give an agent only the Sourcegraph tools it needs (matched by substring)."""
    return [t for t in tools if any(n in t.name for n in names)]


def tool_named(tools, name):
    return next((t for t in tools if name in t.name), None)


def harness():
    """Middleware for every tool-using agent: retries, a cost cap, context compression."""
    return [
        ModelRetryMiddleware(max_retries=3),
        ToolRetryMiddleware(max_retries=2),
        ToolCallLimitMiddleware(run_limit=TOOL_CALL_LIMIT, exit_behavior="end"),
        SummarizationMiddleware(model=SUMMARY_MODEL, trigger=("tokens", 80000),
                                keep=("messages", 12)),
    ]


class Agents:
    def __init__(self, tools):
        self.tools = tools
        llm = init_chat_model(MODEL)

        self.discovery = create_agent(
            MODEL, tools=pick(tools, "keyword_search", "read_file"),
            system_prompt=DISCOVERY_PROMPT, response_format=DiscoveryResult,
            middleware=harness())

        # No tools: they only reason over what the tracers found.
        self.repo_profiler = llm.with_structured_output(RepoProfile)
        self.connector = llm.with_structured_output(ConnectorResult)

    def tracers_for(self, repo: str, revision: str) -> dict:
        """Three tracer agents fenced inside one repository at one revision."""
        rules = scope_rules(repo, revision)
        specs = {
            "upstream": (UPSTREAM_PROMPT, ("go_to_definition", "read_file", "keyword_search")),
            "downstream": (DOWNSTREAM_PROMPT, ("find_references", "read_file", "keyword_search")),
            "storage": (STORAGE_PROMPT, ("keyword_search", "read_file")),
        }
        return {
            role: create_agent(MODEL, tools=pick(self.tools, *tool_names),
                               system_prompt=f"{prompt}\n\n{rules}",
                               response_format=TraceResult, middleware=harness())
            for role, (prompt, tool_names) in specs.items()
        }


async def run_agent(agent, text: str):
    """Run a tool-using agent and return its structured answer."""
    async with _limit:
        out = await agent.ainvoke({"messages": [{"role": "user", "content": text}]},
                                  config={"recursion_limit": 60})
    return out["structured_response"]


async def run_llm(structured_llm, system: str, text: str):
    """Run a no-tools reasoning step and return its structured answer."""
    async with _limit:
        return await structured_llm.ainvoke([{"role": "system", "content": system},
                                             {"role": "user", "content": text}])
