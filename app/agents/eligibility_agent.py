"""Eligibility agent: Determines whether the order qualitifies for a refund or not.

Graph
-----
check_return_window -> [router] -> expired -> END
                                -> compute_refund -> END

Entired deterministic flow - no LLM calls. Langgraph is used purely for
its conditional workflow and routing, making the branching logic testable.

Demo date is fixed at 19th August so scenario's are reproducible.
"""
from datetime import date
from typing import TypedDict

from langgraph.graph import StateGraph, END

from app.contracts import IntakeResult, EligibilityResult

DEMO_TODAY = date(2026, 8, 13)

class _EligibilityState(TypedDict):
    intake: IntakeResult
    days_since_order: int
    within_window: bool
    eligible: bool
    reason: str
    refund_amount: float

def _check_return_window(state: _EligibilityState) -> _EligibilityState:
    order_date = date.fromisoformat(state["intake"].order_date)
    days = (DEMO_TODAY - order_date).days
    within = days <= state["intake"].return_window_days
    return {**state, "within_window": within, "days_since_order": days,}

def _expired(state: _EligibilityState) -> _EligibilityState:
    intake = state["intake"]
    return {
        **state,
        "eligible": False,
        "reason": (
            f"Return window expired: order was {state['days_since_order']} days ago"
            f"(policy limit: {intake.return_window_days} days)"
        )
    }

def _compute_refund(state: _EligibilityState) -> _EligibilityState:
    intake = state["intake"]
    issue = intake.issue_type
    if issue in ("damaged_item", "missing_item","wrong_item"):
        return {
            **state,
            "eligible": True,
            "reason": (
                f"{issue.replace('_',' ').title()} confirmed within return window "
                f"- full refund of ${intake.order_value:.2f} applicable"
            ),
            "refund_amount": intake.order_value,
        }
    return {**state, "eligible": False,
            "reason": f"issue type '{issue}' doesnot qualify for automatic refund",
            "refund_amount": 0.0,}

def _window_router(state: _EligibilityState) -> _EligibilityState:
    return "compute_refund" if state["within_window"] else "expired"

def _build_graph():
    g = StateGraph(_EligibilityState)
    g.add_node("check_return_window",_check_return_window)
    g.add_node("expired", _expired)
    g.add_node("compute_refund",_compute_refund)
    g.set_entry_point("check_return_window")
    g.add_conditional_edges(
        "check_return_window",
        _window_router,
        {"compute_refund": "compute_refund", "expired": "expired"},
    )
    g.add_edge("expired", END)
    g.add_edge("compute_refund", END)
    return g.compile()

_GRAPH = None

def run_eligibility(intake: IntakeResult)->EligibilityResult:
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()

    initial: _EligibilityState = {
        "intake": intake,
        "days_since_order": 0,
        "within_window": False,
        "eligible": False,
        "reason": "",
        "refund_amount": 0.0,
    }
    final = _GRAPH.invoke(initial)
    return EligibilityResult(
        eligible=final["eligible"],
        reason=final["reason"],
        refund_amount=final["refund_amount"],
        days_since_order=final["days_since_order"],
    )

def test_eligibility():
    from app.agents.intake_agent import test_intake
    result = run_eligibility(test_intake())
    return result

if __name__ == "__main__":
    from app.agents.intake_agent import test_intake
    result = run_eligibility(test_intake())
    print(result)
