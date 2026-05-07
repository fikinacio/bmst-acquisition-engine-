"""
ConversationState — the single shared object threaded through every node of the
qualification bot's LangGraph graph.

Imported by: graph.py, nodes.py, tools/calendar.py, tools/airtable.py
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConversationState:
    # ── Identity ──────────────────────────────────────────────────────────────
    company_id: str = ""
    company_name: str = ""
    contact_name: str = ""
    whatsapp_number: str = ""
    sector: str = ""

    # ── Conversation flow ─────────────────────────────────────────────────────
    # Stages: greeting | Q1 | Q2 | Q3 | Q4 | booking | disqualified | nurture
    current_stage: str = "greeting"
    current_node: str = "router"
    messages: list = field(default_factory=list)   # full message history
    incoming_message: str = ""

    # ── Qualification answers ─────────────────────────────────────────────────
    team_size: Optional[str] = None
    main_challenge: Optional[str] = None
    priority_process: Optional[str] = None
    urgency_level: Optional[str] = None
    qualification_score: int = 0
    disqualification_reason: Optional[str] = None

    # ── Output produced by each node ──────────────────────────────────────────
    reply_text: str = ""
    new_state: str = ""        # Airtable state field value after this exchange
    new_stage: str = ""        # next conversation stage
    airtable_updates: dict = field(default_factory=dict)

    # ── Booking ───────────────────────────────────────────────────────────────
    available_slot_1: Optional[str] = None
    available_slot_2: Optional[str] = None

    # ── Meta ──────────────────────────────────────────────────────────────────
    error: Optional[str] = None
    retry_count: int = 0
