"""Parses a customer complain and enhances it with other data

Graph --

lookup_order -> parse_complaint -> end

lookup_order is deterministic, dict lookup
parse complaint is structured llm call

"""
from typing import Literal, TypedDict

from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from pydantic import BaseModel
from app.data import ORDERS
from app.contracts import CustomerComplaint, IntakeResult
from app.llm_helper import LLMHelper

class _ParsedIssue(BaseModel):
    issue_type: Literal["damaged_item", "missing_item", "wrong_item", "other"]
    severity: Literal["low", "medium", "high"]
    damage_summary:str #one factual sentence descriing the problem

class _IntakeState(TypedDict):
    complaint: CustomerComplaint
    order_data: dict | None
    _parsed: _ParsedIssue | None
    result: IntakeResult | None

def _lookup_order(state:_IntakeState):
    order_id = state["complaint"].order_id
    order = ORDERS.get(order_id)

    if order is None:
        raise ValueError(f"Order {order_id} not found")

    return {
        **state,
        "order_data": order,
    }

def _parse_complaint(state:_IntakeState):
    order = state["order_data"]
    complaint = state["complaint"]
    llm = LLMHelper().get_llm()
    structured = llm.with_structured_output(_ParsedIssue,method="function_calling")
    messages = [
        SystemMessage(content = "You are a customer support intake specialist."
                                "Classify the customer complaint into the correct issue_type and "
                                "severity."
                                "Write a single factual sentence for damage_summary"),
        HumanMessage(content=(
            f"Item ordered {order['item_name']} (${order['order_value']:.2f})\n"
            f"Customer complaint: {complaint.complaint_text}"
        ))
    ]
    parsed: _ParsedIssue = structured.invoke(input=messages)
    print(f"Parsed: {parsed}")

    result = IntakeResult(
        order_id=complaint.order_id,
        customer_name=order["customer_name"],
        item_name=order["item_name"],
        order_value=order["order_value"],
        order_date=order["order_date"],
        return_window_days=order["return_window_days"],
        issue_type=parsed.issue_type,
        severity=parsed.severity,
        damage_summary=parsed.damage_summary,
    )
    return {
        **state,
        "parsed": parsed,
        "result": result,
    }

def _build_graph():
    g = StateGraph(_IntakeState)
    g.add_node("lookup_order",_lookup_order)
    g.add_node("parse_complaint",_parse_complaint)
    g.add_edge("lookup_order", "parse_complaint")
    g.add_edge("parse_complaint", END)
    g.set_entry_point("lookup_order")
    return g.compile()

_GRAPH = None

def run_intake(complaint: CustomerComplaint) -> IntakeResult:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    final = _GRAPH.invoke({
        "complaint": complaint,
        "order_data": None,
        "parsed": None,
        "result": None,
    })
    return final["result"]

def test_intake():
    result = run_intake(complaint=CustomerComplaint(order_id='ORDER-SMALL-001', complaint_text='The stand doesnot have one leg not able to use it at all.'))
    return result

if __name__ == "__main__":
    result = run_intake(complaint=CustomerComplaint(order_id='ORDER-SMALL-001', complaint_text='The stand doesnot have one leg not able to use it at all.'))
    print(result)