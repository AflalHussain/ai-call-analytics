"""Pydantic models mirroring DATA_CONTRACT.md v0.1.

The enums here are the contract. Anything outside them is rejected at ingest
rather than silently polluting the intent-distribution chart.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Intent(str, Enum):
    bill_inquiry = "bill_inquiry"
    bill_payment = "bill_payment"
    reload_topup = "reload_topup"
    data_package = "data_package"
    data_balance = "data_balance"
    broadband_fault = "broadband_fault"
    broadband_speed = "broadband_speed"
    router_wifi = "router_wifi"
    mobile_coverage = "mobile_coverage"
    sim_services = "sim_services"
    roaming = "roaming"
    peo_tv = "peo_tv"
    new_connection = "new_connection"
    package_change = "package_change"
    disconnection = "disconnection"
    complaint_followup = "complaint_followup"
    general_info = "general_info"
    other = "other"


INTENT_LABELS: dict[str, str] = {
    "bill_inquiry": "Bill inquiry",
    "bill_payment": "Bill payment",
    "reload_topup": "Reload / top-up",
    "data_package": "Data package",
    "data_balance": "Data balance",
    "broadband_fault": "Broadband fault",
    "broadband_speed": "Broadband speed",
    "router_wifi": "Router / WiFi",
    "mobile_coverage": "Mobile coverage",
    "sim_services": "SIM services",
    "roaming": "Roaming",
    "peo_tv": "PEO TV",
    "new_connection": "New connection",
    "package_change": "Package change",
    "disconnection": "Disconnection",
    "complaint_followup": "Complaint follow-up",
    "general_info": "General info",
    "other": "Other",
}


class EscalationReason(str, Enum):
    caller_requested_human = "caller_requested_human"
    intent_not_supported = "intent_not_supported"
    authentication_failed = "authentication_failed"
    repeated_misunderstanding = "repeated_misunderstanding"
    high_frustration = "high_frustration"
    system_error = "system_error"
    policy_required_human = "policy_required_human"


ESCALATION_LABELS: dict[str, str] = {
    "caller_requested_human": "Caller requested human",
    "intent_not_supported": "Intent not supported",
    "authentication_failed": "Authentication failed",
    "repeated_misunderstanding": "Repeated misunderstanding",
    "high_frustration": "High frustration",
    "system_error": "System error",
    "policy_required_human": "Policy requires human",
}


class HandledBy(str, Enum):
    ai = "ai"
    escalated = "escalated"
    abandoned = "abandoned"
    transferred_ivr = "transferred_ivr"


class Language(str, Enum):
    si = "si"
    ta = "ta"
    en = "en"


LANGUAGE_LABELS: dict[str, str] = {"si": "Sinhala", "ta": "Tamil", "en": "English"}


class CustomerSegment(str, Enum):
    prepaid = "prepaid"
    postpaid = "postpaid"
    fixed = "fixed"
    enterprise = "enterprise"
    unknown = "unknown"


DISTRICTS: list[str] = [
    "Colombo", "Gampaha", "Kalutara", "Kandy", "Matale", "Nuwara Eliya",
    "Galle", "Matara", "Hambantota", "Jaffna", "Kilinochchi", "Mannar",
    "Vavuniya", "Mullaitivu", "Batticaloa", "Ampara", "Trincomalee",
    "Kurunegala", "Puttalam", "Anuradhapura", "Polonnaruwa", "Badulla",
    "Monaragala", "Ratnapura", "Kegalle", "unknown",
]


class Action(BaseModel):
    action: str
    status: str
    ref: str | None = None


class CallRecord(BaseModel):
    """One enriched call. See DATA_CONTRACT.md §1."""

    call_id: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_sec: int
    ai_handling_sec: int | None = None
    queue_wait_sec: int | None = None

    caller_hash: str | None = None
    district: str | None = None
    customer_segment: CustomerSegment | None = None
    channel: str | None = "voice_inbound"

    intent: Intent
    sub_intent: str | None = None
    topics: list[str] = Field(default_factory=list)
    language_primary: Language
    language_mix: list[Language] = Field(default_factory=list)

    handled_by: HandledBy
    resolved: bool
    escalation_reason: EscalationReason | None = None
    actions_taken: list[Action] = Field(default_factory=list)

    sentiment_start: float | None = None
    sentiment_end: float | None = None
    csat_predicted: int | None = None
    interruptions: int | None = None
    silence_ratio: float | None = None

    churn_risk: bool = False
    churn_signals: list[str] = Field(default_factory=list)
    upsell_opportunity: str | None = None
    unanswered_questions: list[str] = Field(default_factory=list)

    summary: str | None = None
    enrichment_model: str | None = None
    enrichment_confidence: float | None = None
    schema_version: str = "0.1"


class CallBatch(BaseModel):
    calls: list[CallRecord]


class ConfigPatch(BaseModel):
    """Partial update of the ROI inputs. All fields optional."""

    human_baseline_aht_sec: int | None = None
    agent_cost_per_hour_lkr: float | None = None
    baseline_containment_pct: float | None = None
    baseline_abandon_pct: float | None = None
    baseline_csat: float | None = None
    figures_are_client_supplied: bool | None = None
