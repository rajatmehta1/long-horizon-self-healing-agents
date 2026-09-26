from pydantic import BaseModel
from enum import Enum

AUTO_APPROVE_THRESHOLD: float = 500.0 #refund at or below -> auto approved
POLICY_MAX_REFUND: float = 2000.0 #guardrail - refund above this is hard stop by policy gate
HUMAN_APPROVAL_TIMEOUT_SECONDS: int = 90 #short for demo/test purpose

TEMPORAL_HOST = "localhost:7233"
TEMPORAL_TASK_QUEUE = "customer-support-demo"

class RefundStatus(str, Enum):
    AUTO_APPROVED = "AUTO_APPROVED"
    PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    HUMAN_REJECTED = "HUMAN_REJECTED"
    TIMED_OUT_ESCALATED = "TIMED_OUT_ESCALATED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    COMPLETED = "COMPLETED"

class CustomerComplaint(BaseModel):
    order_id: str
    complaint_text: str

class IntakeResult(BaseModel):
    order_id: str
    customer_name: str
    item_name: str
    order_value:float
    order_date: str      # "YYYY-MM-DD"
    return_window_days: int
    issue_type: str # damaged_item | missing_item | wrong_item | other
    severity: str   # low | medium | high
    damage_summary: str # 1 sentence LLM-generated summary description

class EligibilityResult(BaseModel):
    eligible: bool
    reason: str
    refund_amount: float
    days_since_order: int

class HumanApprovalSignal(BaseModel):
    approved: bool
    reviewer_id: str
    notes: str = ""

class WorkflowResult(BaseModel):
    order_id: str
    status: RefundStatus
    refund_id: str = ""
    customer_message: str = ""
    notes: str = ""

# --- Activity input wrappers -----------------------------
# Temporal reliably serializes a single pydantic model per activity
# passing multiple positional args via args = [...] i activity breaks enum deserialization
class SendResponseInput(BaseModel):
    intake: IntakeResult
    status: str # Refundstatus.value - plain string avoids enum deserialization issue
    refund_id: str = ""
    notes: str = ""

class PolicyRejectInput(BaseModel):
    intake: IntakeResult
    policy_max: float
    refund_amount: float

class ProcessRefundInput(BaseModel):
    order_id: str
    amount: float
