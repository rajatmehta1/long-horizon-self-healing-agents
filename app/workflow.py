"""
Temporal Workflow - orchestrate the customer support refund case end to end

Four patterns demostrated here (with Temporal UI evidence for each)
1. Durable execution - the workflow survives worker crashes at any await point.
   Temporal replaces from the event log; no step is lost

2. Transient retry - process_refund fails twice before succeeding.
   RetryPolicy handles backoff automatically

3. Human in the loop - refunds above the Auto approve threshold pause here and wait for an external
   human approval signal. Workflow.wait_condition is durable - the wait survives restarts

4. Policy Gate - refunds above policy max ($2000) hit a hard stop. No agent can route around this,
   the branch has no forward path.
Workflow code must be deterministic ; no I?O no datetime now no randowmness
All non deterministic work (LLM calls / api calls) lives in teh activities.
"""
import logging
from datetime import timedelta
from temporalio import workflow
from temporalio.common import RetryPolicy
import asyncio

with workflow.unsafe.imports_passed_through():
    from app.contracts import (
        AUTO_APPROVE_THRESHOLD,
        HUMAN_APPROVAL_TIMEOUT_SECONDS,
        POLICY_MAX_REFUND,
        CustomerComplaint,
        EligibilityResult,
        IntakeResult,
        PolicyRejectInput,
        ProcessRefundInput,
        RefundStatus,
        SendResponseInput,
        WorkflowResult, HumanApprovalSignal
)
    from app.activities import (
        assess_eligibility,
        ingest_complaint,
        notify_policy_rejection,
        process_refund,
        send_customer_response
    )

logger = logging.getLogger(__name__)

_STD_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
)

_REFUND_RETRY = RetryPolicy(
    maximum_attempts=5,
    initial_interval=timedelta(seconds=4),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
)

@workflow.defn
class CustomerSupportWorkflow:

    def __init__(self):
        self._approval: HumanApprovalSignal | None = None

    @workflow.signal
    def human_approval(self, signal:HumanApprovalSignal) -> None:
        """Receive a human approve/reject decision for a high value refund
           Signals are recorded in the temporal even log - the reviewer identifty and
           timestam are premanently auditable"""
        self._approval = signal

    @workflow.query
    def approval_status(self)->str:
        """Read the current approval status without modifying the workflow"""
        if self._approval is None:
            return "AWAITING_HUMAN_REVIEW"
        return "APPROVED" if self._approval.approved else "REJECTED"

    @workflow.run
    async def run(self, complaint: CustomerComplaint) -> WorkflowResult:
        order_id = complaint.order_id
        workflow.logger.info(f"=== CustomerSupportWorkflow started for {order_id} ===")

        #Step 1: Intake
        intake:IntakeResult = await workflow.execute_activity(
            ingest_complaint,
            complaint,
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=_STD_RETRY,
        )

        #Step 2: Eligibility
        eligibility:EligibilityResult = await workflow.execute_activity(
            assess_eligibility,
            intake,
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=_STD_RETRY,
        )

        if not eligibility.eligible:
            message = await workflow.execute_activity(
                send_customer_response,
                SendResponseInput(
                    intake=intake,
                    status=RefundStatus.NOT_ELIGIBLE.value,
                    notes=eligibility.reason
                ),
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=_STD_RETRY,
            )
            return WorkflowResult(
                order_id=order_id,
                status=RefundStatus.NOT_ELIGIBLE,
                customer_message=message,
                notes=eligibility.reason,
            )

        #3. Step 3: Policy Gate (deterministic  - never delegated to the agent) -
        # the gate reads constants from contracts.py, not from any LLM output.
        # Agents propose the refund amount; the gate authorizes or blocks it
        amount = eligibility.refund_amount

        if amount > POLICY_MAX_REFUND:
            # Hard Stop - there is not path forward for this
            workflow.logger.warning(
                f"[PolicyGate] Blocked - ${amount:.2f} exceeds policy max ${POLICY_MAX_REFUND:.2f}"
            )
            message = await workflow.execute_activity(
                notify_policy_rejection,
                PolicyRejectInput(
                    intake=intake,
                    policy_max=POLICY_MAX_REFUND,
                    refund_amount=amount,
                ),
                start_to_close_timeout=timedelta(minutes=3),
                retry_policy=_STD_RETRY,
            )
            return WorkflowResult(
                order_id=order_id,
                status=RefundStatus.POLICY_BLOCKED,
                customer_message=message,
                notes=f"Refund ${amount:.2f} exceeds policy max ${POLICY_MAX_REFUND:.2f}",
            )

        if amount > AUTO_APPROVE_THRESHOLD:
            # Human in the loop should be invoked
            workflow.logger.info(
                f"[HumanReview] Refund ${amount:.2f} requires human approval - waiting for signal"
            )
            try:
                await workflow.wait_condition(
                    lambda: self._approval is not None,
                    timeout=timedelta(seconds=HUMAN_APPROVAL_TIMEOUT_SECONDS),
                )
            except asyncio.TimeoutError:
                message = await workflow.execute_activity(
                    send_customer_response,
                    SendResponseInput(
                        intake=intake,
                        status=RefundStatus.TIMED_OUT_ESCALATED.value,
                        notes="No reviewer response within the review window - case escalated to specialist team"
                    ),
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=_STD_RETRY,
                )
                return WorkflowResult(
                    order_id=order_id,
                    status=RefundStatus.TIMED_OUT_ESCALATED,
                    customer_message=message,
                    notes="Human approval timed out - case escalated to specialist team",
                )

            if not self._approval.approved:
                message = await workflow.execute_activity(
                    send_customer_response,
                    SendResponseInput(
                        intake=intake,
                        status=RefundStatus.HUMAN_REJECTED.value,
                        notes=self._approval.notes
                    ),
                    start_to_close_timeout=timedelta(minutes=3),
                    retry_policy=_STD_RETRY,
                )
                return WorkflowResult(
                    order_id=order_id,
                    status=RefundStatus.HUMAN_REJECTED,
                    customer_message=message,
                    notes=f"Rejected by {self._approval.reviewer_id}: {self._approval.notes}",
                )

            refund_status = RefundStatus.HUMAN_APPROVED
            approval_notes = f"Approved by {self._approval.reviewer_id}"
        else:
            # auto approve
            refund_status = RefundStatus.AUTO_APPROVED
            approval_notes = f"Auto-Approved - ${amount:.2f} within ${AUTO_APPROVE_THRESHOLD:.2f} threshold"

        #Step4 Process Refund
        # This activity simulates a transient failure on the first two atenmpts
        # Watch the UI the activity will show the two failed attempts
        refund_id:str = await workflow.execute_activity(
            process_refund,
            ProcessRefundInput(order_id=order_id,amount=amount),
            start_to_close_timeout=timedelta(minutes=5),
            retry_policy=_REFUND_RETRY,
        )

        #Step 5 - Customer Confirmation
        message = await workflow.execute_activity(
            send_customer_response,
            SendResponseInput(intake=intake,status=RefundStatus.COMPLETED.value,
                              refund_id=refund_id,notes=approval_notes),
            start_to_close_timeout=timedelta(minutes=3),
            retry_policy=_STD_RETRY,
        )
        workflow.logger.info(f"=== Workflow Completed - refund id={refund_id} ===")
        return WorkflowResult(
            order_id=order_id,
            status=RefundStatus.COMPLETED,
            refund_id=refund_id,
            customer_message=message,
            notes=approval_notes
        )


