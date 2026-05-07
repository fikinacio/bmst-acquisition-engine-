"""
Node implementations for the qualification bot LangGraph.

Every node signature: (state: ConversationState) -> ConversationState

Protocol for each node:
  1. Load the relevant prompt template from prompts.py
  2. Inject ConversationState fields into the template
  3. Call claude-sonnet-4-6 via langchain-anthropic (with retry wrapper)
  4. Parse the structured JSON response
  5. Set state.reply_text, state.new_stage, state.airtable_updates
  6. Return the updated state

Retry decorator applied to every LLM call:
  @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))

All logging via loguru.
"""

import json
import re
from dataclasses import replace

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from agents.qualification_bot import prompts
from agents.qualification_bot.state import ConversationState
from agents.qualification_bot.tools import calendar as cal
from agents.qualification_bot.tools import airtable as at

_MODEL = "claude-sonnet-4-6"
QUALIFY_THRESHOLD = 70


# ── LLM helpers ───────────────────────────────────────────────────────────────

def _llm() -> ChatAnthropic:
    return ChatAnthropic(model=_MODEL, temperature=0.3, max_tokens=800)


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON object found in LLM response: {text!r}")
    return json.loads(match.group())


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
def _call_llm(system: str, user: str) -> dict:
    response = _llm().invoke([
        SystemMessage(content=system),
        HumanMessage(content=user),
    ])
    return _extract_json(response.content)


# ── Router ────────────────────────────────────────────────────────────────────

def router(state: ConversationState) -> ConversationState:
    """No-op node — routing is handled entirely by conditional edges in graph.py."""
    return state


# ── Greeting ──────────────────────────────────────────────────────────────────

def greeting(state: ConversationState) -> ConversationState:
    """Send welcome message and ask first qualifying question. Sets new_stage = 'Q1'."""
    logger.info(f"greeting | company={state.company_name}")
    user_prompt = prompts.GREETING_PROMPT.format(
        contact_name=state.contact_name or "Cliente",
        company_name=state.company_name or "a sua empresa",
        sector=state.sector or "não especificado",
    )
    try:
        result = _call_llm(prompts.SYSTEM_PROMPT, user_prompt)
        new_stage = result.get("new_stage", "Q1")
        return replace(
            state,
            reply_text=result["reply_text"],
            new_stage=new_stage,
            new_state="contacted",
            airtable_updates={"state": "contacted", "conversation_stage": new_stage},
            error=None,
        )
    except Exception as exc:
        logger.error(f"greeting error: {exc}")
        return replace(state, error=str(exc))


# ── Q1: Team size ─────────────────────────────────────────────────────────────

def q1_team_size(state: ConversationState) -> ConversationState:
    """Interpret team-size reply. Disqualifies if < 5 FTEs (new_stage = 'disqualified')."""
    logger.info(f"q1_team_size | company={state.company_name} | msg={state.incoming_message!r}")
    user_prompt = prompts.Q1_TEAM_SIZE_PROMPT.format(
        contact_name=state.contact_name or "Cliente",
        company_name=state.company_name or "a sua empresa",
        sector=state.sector or "não especificado",
        incoming_message=state.incoming_message,
    )
    try:
        result = _call_llm(prompts.SYSTEM_PROMPT, user_prompt)
        extracted = result.get("extracted", {})
        team_size = str(extracted.get("team_size", state.incoming_message))
        new_stage = result.get("new_stage", "Q2")
        disqualified = new_stage == "disqualified"

        return replace(
            state,
            team_size=team_size,
            reply_text=result["reply_text"],
            new_stage=new_stage,
            new_state="nurture" if disqualified else "qualification",
            disqualification_reason="team_size_below_threshold" if disqualified else None,
            airtable_updates={
                "team_size": team_size,
                "state": "nurture" if disqualified else "qualification",
                "conversation_stage": new_stage,
            },
            error=None,
        )
    except Exception as exc:
        logger.error(f"q1_team_size error: {exc}")
        return replace(state, error=str(exc))


# ── Q2: Main challenge ────────────────────────────────────────────────────────

def q2_challenge(state: ConversationState) -> ConversationState:
    """Capture main operational challenge and advance to Q3."""
    logger.info(f"q2_challenge | company={state.company_name}")
    user_prompt = prompts.Q2_CHALLENGE_PROMPT.format(
        contact_name=state.contact_name or "Cliente",
        company_name=state.company_name or "a sua empresa",
        sector=state.sector or "não especificado",
        team_size=state.team_size or "desconhecido",
        incoming_message=state.incoming_message,
    )
    try:
        result = _call_llm(prompts.SYSTEM_PROMPT, user_prompt)
        extracted = result.get("extracted", {})
        main_challenge = extracted.get("main_challenge") or state.incoming_message
        new_stage = result.get("new_stage", "Q3")

        return replace(
            state,
            main_challenge=main_challenge,
            reply_text=result["reply_text"],
            new_stage=new_stage,
            new_state="qualification",
            airtable_updates={
                "main_challenge": main_challenge,
                "conversation_stage": new_stage,
            },
            error=None,
        )
    except Exception as exc:
        logger.error(f"q2_challenge error: {exc}")
        return replace(state, error=str(exc))


# ── Q3: Priority process ──────────────────────────────────────────────────────

def q3_process(state: ConversationState) -> ConversationState:
    """Capture the highest-cost bottleneck process and advance to Q4."""
    logger.info(f"q3_process | company={state.company_name}")
    user_prompt = prompts.Q3_PROCESS_PROMPT.format(
        contact_name=state.contact_name or "Cliente",
        company_name=state.company_name or "a sua empresa",
        sector=state.sector or "não especificado",
        team_size=state.team_size or "desconhecido",
        main_challenge=state.main_challenge or "não especificado",
        incoming_message=state.incoming_message,
    )
    try:
        result = _call_llm(prompts.SYSTEM_PROMPT, user_prompt)
        extracted = result.get("extracted", {})
        priority_process = extracted.get("priority_process") or state.incoming_message
        new_stage = result.get("new_stage", "Q4")

        return replace(
            state,
            priority_process=priority_process,
            reply_text=result["reply_text"],
            new_stage=new_stage,
            new_state="qualification",
            airtable_updates={
                "priority_process": priority_process,
                "conversation_stage": new_stage,
            },
            error=None,
        )
    except Exception as exc:
        logger.error(f"q3_process error: {exc}")
        return replace(state, error=str(exc))


# ── Q4: Urgency + scoring ─────────────────────────────────────────────────────

def q4_urgency(state: ConversationState) -> ConversationState:
    """Assess urgency and budget readiness; compute qualification_score (0-100)."""
    logger.info(f"q4_urgency | company={state.company_name}")
    user_prompt = prompts.Q4_URGENCY_PROMPT.format(
        contact_name=state.contact_name or "Cliente",
        company_name=state.company_name or "a sua empresa",
        sector=state.sector or "não especificado",
        team_size=state.team_size or "desconhecido",
        main_challenge=state.main_challenge or "não especificado",
        priority_process=state.priority_process or "não especificado",
        incoming_message=state.incoming_message,
    )
    try:
        result = _call_llm(prompts.SYSTEM_PROMPT, user_prompt)
        extracted = result.get("extracted", {})
        urgency_level = extracted.get("urgency_level", "low")
        score = max(0, min(100, int(extracted.get("qualification_score", 0))))

        return replace(
            state,
            urgency_level=urgency_level,
            qualification_score=score,
            reply_text=result["reply_text"],
            new_stage=result.get("new_stage", "Q4"),
            new_state="qualification",
            airtable_updates={
                "urgency_level": urgency_level,
                "qualification_score": score,
                "conversation_stage": result.get("new_stage", "Q4"),
            },
            error=None,
        )
    except Exception as exc:
        logger.error(f"q4_urgency error: {exc}")
        return replace(state, error=str(exc))


# ── Qualify pass ──────────────────────────────────────────────────────────────

def qualify_pass(state: ConversationState) -> ConversationState:
    """Score >= threshold — celebrate and transition to booking."""
    logger.info(f"qualify_pass | company={state.company_name} | score={state.qualification_score}")
    user_prompt = prompts.QUALIFY_PASS_PROMPT.format(
        contact_name=state.contact_name or "Cliente",
        company_name=state.company_name or "a sua empresa",
        qualification_score=state.qualification_score,
    )
    try:
        result = _call_llm(prompts.SYSTEM_PROMPT, user_prompt)
        return replace(
            state,
            reply_text=result["reply_text"],
            new_stage="booking",
            new_state="lead",
            airtable_updates={
                "state": "lead",
                "conversation_stage": "booking",
                "qualification_score": state.qualification_score,
            },
            error=None,
        )
    except Exception as exc:
        logger.error(f"qualify_pass error: {exc}")
        return replace(state, error=str(exc))


# ── Qualify fail ──────────────────────────────────────────────────────────────

def qualify_fail(state: ConversationState) -> ConversationState:
    """Score < threshold — empathetic closing and move to nurture state."""
    logger.info(f"qualify_fail | company={state.company_name} | score={state.qualification_score}")
    user_prompt = prompts.QUALIFY_FAIL_PROMPT.format(
        contact_name=state.contact_name or "Cliente",
        company_name=state.company_name or "a sua empresa",
        qualification_score=state.qualification_score,
    )
    try:
        result = _call_llm(prompts.SYSTEM_PROMPT, user_prompt)
        return replace(
            state,
            reply_text=result["reply_text"],
            new_stage="nurture",
            new_state="nurture",
            airtable_updates={
                "state": "nurture",
                "conversation_stage": "nurture",
                "qualification_score": state.qualification_score,
            },
            error=None,
        )
    except Exception as exc:
        logger.error(f"qualify_fail error: {exc}")
        return replace(state, error=str(exc))


# ── Book slot ─────────────────────────────────────────────────────────────────

def _present_slots(state: ConversationState) -> ConversationState:
    """Fetch Calendar slots and present two options. First entry into 'booking' stage."""
    slots = cal.get_available_slots(days_ahead=7)

    if not slots:
        fallback = (
            f"Oi {state.contact_name or 'Cliente'}, vou verificar a disponibilidade "
            "da nossa equipa e entro em contacto em breve para marcar a auditoria. "
            "Obrigado pela paciência!"
        )
        return replace(
            state,
            reply_text=fallback,
            new_stage="booking",
            new_state="lead",
            airtable_updates={"state": "lead", "conversation_stage": "booking"},
            error=None,
        )

    slot_1 = slots[0]
    slot_2 = slots[1] if len(slots) > 1 else slots[0]

    user_prompt = prompts.SLOT_OPTION_PROMPT.format(
        contact_name=state.contact_name or "Cliente",
        company_name=state.company_name or "a sua empresa",
        slot_1=slot_1,
        slot_2=slot_2,
    )
    result = _call_llm(prompts.SYSTEM_PROMPT, user_prompt)

    return replace(
        state,
        reply_text=result["reply_text"],
        new_stage="booking",
        new_state="lead",
        available_slot_1=slot_1,
        available_slot_2=slot_2,
        airtable_updates={
            "state": "lead",
            "conversation_stage": "booking",
            "available_slot_1": slot_1,
            "available_slot_2": slot_2,
        },
        error=None,
    )


def _confirm_booking(state: ConversationState) -> ConversationState:
    """Parse the user's slot choice, book it in Calendar, and confirm."""
    slot_1 = state.available_slot_1
    slot_2 = state.available_slot_2

    # Interpret the user's reply
    choice_prompt = prompts.SLOT_CHOICE_PROMPT.format(
        contact_name=state.contact_name or "Cliente",
        company_name=state.company_name or "a sua empresa",
        slot_1=slot_1,
        slot_2=slot_2,
        incoming_message=state.incoming_message,
    )
    try:
        choice_result = _call_llm(prompts.SYSTEM_PROMPT, choice_prompt)
        chosen = choice_result.get("extracted", {}).get("chosen_slot", "unclear")
    except Exception as exc:
        logger.warning(f"_confirm_booking: slot choice parse failed ({exc}), re-presenting")
        chosen = "unclear"

    if chosen == "unclear":
        # Re-present the same options without fetching new ones
        re_prompt = prompts.SLOT_OPTION_PROMPT.format(
            contact_name=state.contact_name or "Cliente",
            company_name=state.company_name or "a sua empresa",
            slot_1=slot_1,
            slot_2=slot_2,
        )
        result = _call_llm(prompts.SYSTEM_PROMPT, re_prompt)
        return replace(
            state,
            reply_text=result["reply_text"],
            new_stage="booking",
            new_state="lead",
            airtable_updates={"state": "lead", "conversation_stage": "booking"},
            error=None,
        )

    confirmed_slot = slot_1 if chosen == "1" else slot_2
    logger.info(f"_confirm_booking | chosen={chosen} | slot={confirmed_slot}")

    event_id = cal.book_slot(
        confirmed_slot,
        state.company_name or "Empresa",
        state.contact_name or "Cliente",
        state.whatsapp_number,
    )

    confirm_prompt = prompts.BOOKING_CONFIRM_PROMPT.format(
        contact_name=state.contact_name or "Cliente",
        company_name=state.company_name or "a sua empresa",
        confirmed_slot=confirmed_slot,
        event_id=event_id,
    )
    result = _call_llm(prompts.SYSTEM_PROMPT, confirm_prompt)

    return replace(
        state,
        reply_text=result["reply_text"],
        new_stage="audit_scheduled",
        new_state="audit_scheduled",
        airtable_updates={
            "state": "audit_scheduled",
            "conversation_stage": "audit_scheduled",
            "available_slot_1": None,
            "available_slot_2": None,
            "booked_slot": confirmed_slot,
            "calendar_event_id": event_id,
        },
        error=None,
    )


def book_slot(state: ConversationState) -> ConversationState:
    """Present slot options (first pass) or confirm booking (user replied with choice)."""
    logger.info(f"book_slot | company={state.company_name} | has_slots={bool(state.available_slot_1)}")
    try:
        if state.available_slot_1 and state.incoming_message:
            return _confirm_booking(state)
        return _present_slots(state)
    except Exception as exc:
        logger.error(f"book_slot error: {exc}")
        return replace(state, error=str(exc))


# ── Nurture sequence nodes ────────────────────────────────────────────────────

# Sentinel value WF06 sends as incoming_message when requesting an outbound touch.
# Any other value means WF03 is routing an inbound lead reply.
_OUTBOUND_PREFIX = "nurture_touch_"
_REQUALIFY_TOKEN = "requalify"


def nurture_touch_1(state: ConversationState) -> ConversationState:
    """Day-14 content share. Generates an outbound nurture message; no reply expected."""
    logger.info(f"nurture_touch_1 | company={state.company_name}")
    user_prompt = prompts.NURTURE_TOUCH_1_PROMPT.format(
        contact_name=state.contact_name or "Cliente",
        company_name=state.company_name or "a sua empresa",
        sector=state.sector or "não especificado",
    )
    try:
        result = _call_llm(prompts.SYSTEM_PROMPT, user_prompt)
        return replace(
            state,
            reply_text=result["reply_text"],
            new_stage="nurture",
            new_state="nurture",
            airtable_updates={"conversation_stage": "nurture"},
            error=None,
        )
    except Exception as exc:
        logger.error(f"nurture_touch_1 error: {exc}")
        return replace(state, error=str(exc))


def nurture_touch_2(state: ConversationState) -> ConversationState:
    """Day-30 soft re-qualification. References original challenge."""
    logger.info(f"nurture_touch_2 | company={state.company_name}")
    user_prompt = prompts.NURTURE_TOUCH_2_PROMPT.format(
        contact_name=state.contact_name or "Cliente",
        company_name=state.company_name or "a sua empresa",
        sector=state.sector or "não especificado",
        main_challenge=state.main_challenge or "processos manuais",
    )
    try:
        result = _call_llm(prompts.SYSTEM_PROMPT, user_prompt)
        return replace(
            state,
            reply_text=result["reply_text"],
            new_stage="nurture",
            new_state="nurture",
            airtable_updates={"conversation_stage": "nurture"},
            error=None,
        )
    except Exception as exc:
        logger.error(f"nurture_touch_2 error: {exc}")
        return replace(state, error=str(exc))


def nurture_touch_3(state: ConversationState) -> ConversationState:
    """Day-60 new-angle content share. References priority process."""
    logger.info(f"nurture_touch_3 | company={state.company_name}")
    user_prompt = prompts.NURTURE_TOUCH_3_PROMPT.format(
        contact_name=state.contact_name or "Cliente",
        company_name=state.company_name or "a sua empresa",
        sector=state.sector or "não especificado",
        priority_process=state.priority_process or "processos operacionais",
    )
    try:
        result = _call_llm(prompts.SYSTEM_PROMPT, user_prompt)
        return replace(
            state,
            reply_text=result["reply_text"],
            new_stage="nurture",
            new_state="nurture",
            airtable_updates={"conversation_stage": "nurture"},
            error=None,
        )
    except Exception as exc:
        logger.error(f"nurture_touch_3 error: {exc}")
        return replace(state, error=str(exc))


def requalify(state: ConversationState) -> ConversationState:
    """
    Dual-purpose node for Day-75 re-qualification:

    - incoming_message == 'requalify' (WF06 outbound): generate the re-qualification
      message and set conversation_stage='requalify' so WF03 routes the reply back here.
    - Any other incoming_message (WF03 inbound reply): interpret the lead's reply and
      transition to Q2 (positive) or stay in nurture (negative/neutral).
    """
    if state.incoming_message.strip() == _REQUALIFY_TOKEN:
        logger.info(f"requalify outbound | company={state.company_name}")
        user_prompt = prompts.REQUALIFY_PROMPT.format(
            contact_name=state.contact_name or "Cliente",
            company_name=state.company_name or "a sua empresa",
            sector=state.sector or "não especificado",
            main_challenge=state.main_challenge or "processos manuais",
            priority_process=state.priority_process or "processos operacionais",
        )
        try:
            result = _call_llm(prompts.SYSTEM_PROMPT, user_prompt)
            return replace(
                state,
                reply_text=result["reply_text"],
                new_stage="requalify",
                new_state="nurture",
                airtable_updates={"conversation_stage": "requalify"},
                error=None,
            )
        except Exception as exc:
            logger.error(f"requalify outbound error: {exc}")
            return replace(state, error=str(exc))
    else:
        logger.info(
            f"requalify reply | company={state.company_name} | msg={state.incoming_message!r}"
        )
        user_prompt = prompts.REQUALIFY_REPLY_PROMPT.format(
            contact_name=state.contact_name or "Cliente",
            company_name=state.company_name or "a sua empresa",
            sector=state.sector or "não especificado",
            main_challenge=state.main_challenge or "processos manuais",
            priority_process=state.priority_process or "processos operacionais",
            incoming_message=state.incoming_message,
        )
        try:
            result = _call_llm(prompts.SYSTEM_PROMPT, user_prompt)
            new_stage = result.get("new_stage", "nurture")
            positive = new_stage == "Q2"
            new_state = "qualification" if positive else "nurture"
            return replace(
                state,
                reply_text=result["reply_text"],
                new_stage=new_stage,
                new_state=new_state,
                airtable_updates={
                    "state": new_state,
                    "conversation_stage": new_stage,
                },
                error=None,
            )
        except Exception as exc:
            logger.error(f"requalify reply error: {exc}")
            return replace(state, error=str(exc))


# ── Error handler ─────────────────────────────────────────────────────────────

def error_handler(state: ConversationState) -> ConversationState:
    """Catch node failures. Retry up to 3 times, then send apology and halt."""
    new_retry = state.retry_count + 1
    logger.error(f"error_handler | attempt={new_retry}/3 | error={state.error}")

    if new_retry >= 3:
        apology = (
            f"Desculpe {state.contact_name or 'Cliente'}, estamos a ter uma "
            "dificuldade técnica. A nossa equipa vai entrar em contacto consigo "
            "em breve. Obrigado pela paciencia! "
        )
        return replace(
            state,
            reply_text=apology,
            retry_count=new_retry,
            new_stage=state.current_stage,
            new_state=state.new_state or "contacted",
            airtable_updates={
                "notes": f"Bot error after {new_retry} retries: {state.error}"
            },
        )

    retry_msg = (
        f"Desculpe {state.contact_name or 'Cliente'}, tive um problema a processar "
        "a sua mensagem. Pode repetir a sua resposta, por favor?"
    )
    return replace(
        state,
        reply_text=retry_msg,
        retry_count=new_retry,
        new_stage=state.current_stage,
        airtable_updates={},
    )
