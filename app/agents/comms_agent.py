"""Communication agent: drafts the customer-facing response using an LLM
Graph

draft_response -> END
Single LLM call that writes a warm, consice message tailored to the outcome.
The model is given facts only - no policy reasoning
   """
from typing import TypedDict

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from app.contracts import IntakeResult, RefundStatus
from app.llm_helper import LLMHelper

class _CommState(TypedDict):
    intake: IntakeResult
    status: RefundStatus
    refund_id: str
    notes: str
    message: str

def _draft_response(state: _CommState) -> _CommState:
    llm = LLMHelper().get_llm()
    intake = state['intake']
    context_lines = [
        f"Customer name: {intake.customer_name}",
        f"Item: {intake.item_name}",
        f"Outcome: {state['status'].value}",
    ]
    if state['refund_id']:
        context_lines.append(f"Refund reference number: {state['refund_id']}")
    if state['notes']:
        context_lines.append(f"Additional context: {state['notes']}")

    response = llm.invoke(
        input = [
            SystemMessage(content=(
                "You are a helpful, empathetic customer support agent."
                "Write a brief, professional message to the customer (2-3 sentences)."
                "Be warm and clear. Do not invent details not provided below"
            )),
            HumanMessage(content="\n".join(context_lines)),
        ]
    )
    return {
        **state,
        'message': response.content
    }

def _build_graph():
    g = StateGraph(_CommState)
    g.add_node("draft_response", _draft_response)
    g.add_edge("draft_response",END)
    g.set_entry_point("draft_response")
    return g.compile()

_GRAPH = None

def draft_customer_message(intake: IntakeResult,
                           status: RefundStatus,
                           refund_id: str = "",
                           notes: str = "",) -> str:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    initial:_CommState = {
        "intake": intake,
        "status": status,
        "refund_id": refund_id,
        "notes": notes,
        "message": ""
    }
    final = _GRAPH.invoke(initial)
    return final['message']

if __name__ == "__main__":
    from app.agents.intake_agent import test_intake
    from app.agents.eligibility_agent import test_eligibility
    result = draft_customer_message(intake=test_intake(),status=RefundStatus.AUTO_APPROVED,
                                    refund_id="abc",notes="This is the refund message")
    print(result)
