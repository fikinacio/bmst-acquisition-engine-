"""
FastAPI service — exposes the three agent subsystems as HTTP endpoints.

Routes
------
GET  /health
    Returns { "status": "ok" }

POST /qualify
    Body:    { "company_record": dict, "incoming_message": str }
    Returns: { "reply_text": str, "new_state": str, "new_stage": str, "updates": dict }
    Agent:   agents/qualification_bot

POST /run-prospecting
    Body:    {} (no payload required)
    Returns: { "status": "ok", "prospects_found": int }
    Agent:   agents/prospecting

POST /generate-content
    Body:    { "company_name": str, "sector": str, "pain_description": str,
               "audit_notes": str, "market": str }
    Returns: { "linkedin_body": str, "instagram_body": str, "suggested_visual": str }
    Agent:   agents/content_engine

Run:
    uvicorn api.main:app --host $API_HOST --port $API_PORT
"""

from fastapi import FastAPI, HTTPException
from loguru import logger
from pydantic import BaseModel

from agents.qualification_bot.graph import build_graph
from agents.qualification_bot.state import ConversationState

app = FastAPI(title="BMST Acquisition Engine", version="1.0.0")

# Build graph once at startup — reused across all /qualify requests
_qualify_graph = build_graph()


# ── Request models ────────────────────────────────────────────────────────────

class QualifyRequest(BaseModel):
    company_record: dict
    incoming_message: str


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/qualify")
def qualify(payload: QualifyRequest):
    """
    Run one qualification bot turn for the given company record and incoming message.

    company_record is the raw Airtable record dict: { "id": "recXXX", "fields": {...} }
    The 'fields' dict may use the Airtable field names from the companies table.
    """
    record = payload.company_record
    # Support both raw pyairtable format ({ id, fields }) and flat dict
    fields: dict = record.get("fields", record)

    state = ConversationState(
        company_id=record.get("id", ""),
        company_name=fields.get("Name", fields.get("company_name", "")),
        contact_name=fields.get("contact_name", ""),
        whatsapp_number=str(fields.get("whatsapp_number", "")),
        sector=fields.get("sector", ""),
        current_stage=fields.get("conversation_stage", "greeting"),
        team_size=fields.get("team_size"),
        main_challenge=fields.get("main_challenge"),
        priority_process=fields.get("priority_process"),
        urgency_level=fields.get("urgency_level"),
        qualification_score=int(fields.get("qualification_score") or 0),
        available_slot_1=fields.get("available_slot_1"),
        available_slot_2=fields.get("available_slot_2"),
        incoming_message=payload.incoming_message,
    )

    logger.info(
        f"qualify | company={state.company_name} | "
        f"stage={state.current_stage} | msg={state.incoming_message!r}"
    )

    try:
        result = _qualify_graph.invoke(state)
    except Exception as exc:
        logger.error(f"Graph invocation failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

    # LangGraph may return a dict or the state object depending on version
    if isinstance(result, dict):
        reply_text = result.get("reply_text", "")
        error = result.get("error")
        if error and not reply_text:
            logger.error(f"qualify | bot node error with no reply | {error!r}")
            raise HTTPException(status_code=500, detail=f"Bot node error: {error}")
        return {
            "reply_text": reply_text,
            "new_state": result.get("new_state", ""),
            "new_stage": result.get("new_stage", ""),
            "updates": result.get("airtable_updates", {}),
        }

    if result.error and not result.reply_text:
        logger.error(f"qualify | bot node error with no reply | {result.error!r}")
        raise HTTPException(status_code=500, detail=f"Bot node error: {result.error}")

    return {
        "reply_text": result.reply_text,
        "new_state": result.new_state,
        "new_stage": result.new_stage,
        "updates": result.airtable_updates,
    }


@app.post("/run-prospecting")
def run_prospecting():
    """Trigger the crewAI prospecting pipeline and return the prospect count."""
    from agents.prospecting.crew import run_crew
    try:
        prospects = run_crew()
    except Exception as exc:
        logger.error(f"Prospecting crew failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    return {"status": "ok", "prospects_found": len(prospects)}


class GenerateContentRequest(BaseModel):
    company_name: str
    sector: str
    pain_description: str
    audit_notes: str
    market: str = "Angola"


@app.post("/generate-content")
def generate_content(payload: GenerateContentRequest):
    """Generate anonymised LinkedIn and Instagram posts from audit data."""
    from agents.content_engine.chain import run_content_chain
    try:
        result = run_content_chain(payload.model_dump())
    except ValueError as exc:
        logger.warning(f"Content validation failed: {exc}")
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error(f"Content engine failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
    return result
