"""Demo cli - start workflow, send signals and query status

Commands:
 python -m app.trigger start <order_id> "<complaint text>" [--wait]
 python -m app.trigger approve <workflow_id> <reviewer_id> [notes]
 python -m app.trigger reject  <workflow_id> <reviewer_id> [notes]
 python -m app.trigger status  <order_id>
 python -m app.trigger demo # fires all 4 scenarios once

Workflow ID =  customer-support-<order_id>
"""
import argparse
import asyncio
import sys

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from app.contracts import (
    TEMPORAL_HOST,
    TEMPORAL_TASK_QUEUE,
    CustomerComplaint,
    HumanApprovalSignal,
    WorkflowResult,
)
from app.data import ORDERS
from app.workflow import CustomerSupportWorkflow

TEMPORAL_UI = "http://localhost:3001"

def _wf_id(order_id:str) -> str:
    return f"customer-support-{order_id}"

async def _connect() -> Client:
    # pydantic converter must match the worker's, or payloads won't round-trip
    return await Client.connect(TEMPORAL_HOST, data_converter=pydantic_data_converter)

async def cmd_start(order_id:str, complaint_text:str) -> None:
    client = await _connect()
    wf_id = _wf_id(order_id)
    handle = await client.start_workflow(
        CustomerSupportWorkflow.run,
        CustomerComplaint(order_id=order_id, complaint_text=complaint_text),
        id=wf_id,
        task_queue=TEMPORAL_TASK_QUEUE,
    )
    print(f'\n Workflow started')
    print(f'    Order ID: {order_id}')
    print(f'    Workflow ID: {wf_id}')
    print(f'    Run ID: {handle.result_run_id}')
    print(f'    Temporal UI: http://localhost:3001/namespaces/default/workflows/{wf_id}\n')


async def cmd_approve(workflow_id:str,reviewer_id:str, notes:str = "") -> None:
    client = await _connect()
    handle = client.get_workflow_handle(workflow_id)
    await handle.signal(
        CustomerSupportWorkflow.human_approval,
        HumanApprovalSignal(approved=True,reviewer_id=reviewer_id,notes=notes),
    )
    print(f'    Approval signal sent | reviewer : {reviewer_id}')

async def cmd_reject(workflow_id:str,reviewer_id:str, notes:str = "") -> None:
    client = await _connect()
    handle = client.get_workflow_handle(workflow_id)
    await handle.signal(
        CustomerSupportWorkflow.human_approval,
        HumanApprovalSignal(approved=False,reviewer_id=reviewer_id,notes=notes),
    )
    print(f'    Rejection signal sent | reviewer : {reviewer_id}')

async def cmd_status(workflow_id:str) -> None:
    client = await _connect()
    handle = client.get_workflow_handle(workflow_id)
    status = await handle.query(CustomerSupportWorkflow.approval_status)
    print(f'    Workflow ID   : {workflow_id}')
    print(f'    Approval Status   : {status}')

async def cmd_demo() -> None:
    scenarios = [
        (
            "ORD-SMALL-001",
            "My USB-C laptop stand arrived with the packaging completely crushed."
            "The stand itself is bend and wobbles - it is unusable"
        ),
        (
            "ORD-MID-002",
            "I received my ProBook laptop but the screen has a large crack across the middle."
            "It must have been damaged during shipping."
        ),
        (
            "ORD-LARGE-003",
            "The developer workstation was delivered but the metal case is heavily dented"
            " and the system will not power on at all."
        ),
        (
            "ORD-EXPIRED-004",
            "My wireless keyboard stopped registering keystrokes after a month of light"
            " use."
        ),
    ]
    for order_id, complaint_text in scenarios:
        print(f"\nScenario order id: {order_id}")
        await cmd_start(order_id, complaint_text)

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Customer Support Demo - Temporal workflow CLI"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("start", help="Start a support workflow")
    p.add_argument("order_id", help="e.g. ORD-SMALL-001")
    p.add_argument("complaint", help="Customer complaint text (quote it)")

    p = sub.add_parser("approve", help="Send human approval signal")
    p.add_argument("workflow_id", help="e.g. customer-support-ORD-MID-002")
    p.add_argument("reviewer_id", help="Reviewer name or ID")
    p.add_argument("notes", nargs="?",default="", help="Optional notes")

    p = sub.add_parser("reject", help="Send human rejection signal")
    p.add_argument("workflow_id")
    p.add_argument("reviewer_id")
    p.add_argument("notes", nargs="?", default="")

    p = sub.add_parser("status", help="Query current approval status")
    p.add_argument("workflow_id")

    sub.add_parser("demo", help="Start all four scenarios at once")

    args = parser.parse_args()

    dispatch = {
        "start": lambda: cmd_start(args.order_id, args.complaint),
        "approve": lambda: cmd_approve(args.workflow_id, args.reviewer_id, args.notes),
        "reject": lambda: cmd_reject(args.workflow_id, args.reviewer_id, args.notes),
        "status": lambda: cmd_status(args.workflow_id),
        "demo": lambda: cmd_demo(),
    }

    asyncio.run(dispatch[args.cmd]())


if __name__ == "__main__":
    main()