"""Temporal activities - thin wrappers that call langgraph agents or performa action
every non deterministic operation (LLM call, external api) lives here.
Temporal records each activity's input and output in its event log.
On workflow replace after a crash, recorded results are replayed - the code
below is NOT rexecuted. This is what makes LLM calls crash-safe

Activities are synchronous functions. Temporal's asyncio worker runs them in a thread pool
automatically"""
import logging
import uuid
from temporalio.exceptions import ApplicationError

from app.agents.comms_agent import draft_customer_message
from app.agents.eligibility_agent import run_eligibility
from app.agents.intake_agent import run_intake
from app.contracts import CustomerComplaint, IntakeResult, EligibilityResult, ProcessRefundInput, PolicyRejectInput, \
    RefundStatus, SendResponseInput
from temporalio import activity
logger = logging.getLogger(__name__)

@activity.defn
def ingest_complaint(complaint:CustomerComplaint) -> IntakeResult:
    logger.info(f'[Intake] processing complaint for order {complaint.order_id}')
    result = run_intake(complaint=complaint)
    logger.info(
        f"[Intake] Done - issue_type: {result.issue_type},"
        f"severity={result.severity}: {result.damage_summary}"
    )
    return result

@activity.defn
def assess_eligibility(intake: IntakeResult) -> EligibilityResult:
    """Run the eligibility langgraph agent: deterministic date + rule check."""
    logger.info(f"[Eligibility] Assessing order {intake.order_id}")
    result = run_eligibility(intake=intake)
    logger.info(
        f"[Eligibility] eligible: {result.eligible},"
        f"amount={result.refund_amount:.2f} : {result.reason}"
    )
    return result

@activity.defn
def process_refund(inp: ProcessRefundInput) -> str:
    """Call the simulated Refund API
    Fails transiently on the first two attems to demonstate Temporals
    automatic retry with backoff - visible in the Temporal UI as
    failed activity attemds before final success"""
    attempt = activity.info().attempt #1-indexed
    logger.info(f"[Refund] Attempt {attempt} - order={inp.order_id}, amount={inp.amount:.2f}")

    if attempt <= 2:
        raise ApplicationError(
            f"Refund gateway temporarily unavailable. Retry in few seconds.",
            non_retryable=False,
        )
    refund_id = f"REF-{inp.order_id}-{uuid.uuid4().hex[:8].upper()}"
    logger.info(f"[Refund] success, Refund ID: {refund_id}")
    return refund_id

@activity.defn
def notify_policy_rejection(inp: PolicyRejectInput) -> str:
    """Draft and log the policy-blocked customer message.
       Called when the refund amount exceeds POLICY_MAX_REFUND. The workflow
       routes here as a hard stop - there is no path forward for the agent."""
    logger.warning(f"[PolicyGate] BLOCKED - order {inp.intake.order_id}, "
                   f"amount=${inp.refund_amount:.2f} exceeds max=${inp.policy_max:.2f}")
    message = draft_customer_message(
        intake=inp.intake,
        status=RefundStatus.POLICY_BLOCKED,
        notes=(
            f"Your request of ${inp.intake.order_value:.2f} exceeds the automated "
            f"refund limit of ${inp.policy_max:.2f}. A specialist will contact you within 2 business days."
        )
    )
    logger.info(f"[PolicyGate] Customer notified: {message[:100]}")
    return message

@activity.defn
def send_customer_response(inp: SendResponseInput) -> str:
    """Run the communication LangGraph agent: draft a customer-facing message"""
    status_enum = RefundStatus(inp.status)
    logger.info(f"[Comms] Drafting response - customer={inp.intake.customer_name}, status={inp.status}")
    message = draft_customer_message(
        intake=inp.intake,
        status=status_enum,
        refund_id=inp.refund_id,
        notes=inp.notes,
    )
    logger.info(f"[Comms] Message: {message}")
    return message