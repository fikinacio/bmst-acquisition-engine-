"""
Idempotent Airtable schema creator for the BMST Acquisition Engine.

Uses the Airtable Metadata REST API directly (not pyairtable, which is for
record CRUD). Safe to run multiple times — skips existing tables and fields.

Tables created:
  companies      Central CRM — one record per B2B prospect company
  interactions   Log of every WhatsApp exchange and agent action
  errors         n8n workflow error log (Phase 10)

Run:
    python airtable/create_schema.py
"""

import os
import sys
import requests
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

API_KEY = os.environ["AIRTABLE_API_KEY"]
BASE_ID = os.environ["AIRTABLE_BASE_ID"]

TABLES_URL = f"https://api.airtable.com/v0/meta/bases/{BASE_ID}/tables"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# ── Schema definition ─────────────────────────────────────────────────────────
# Link fields (multipleRecordLinks) are added in a second pass once all table
# IDs are known. They are listed in LINK_FIELDS_DEFERRED below.

SCHEMA: dict[str, dict] = {
    "companies": {
        "description": "Central CRM table — one record per B2B prospect company.",
        "fields": [
            # Primary field is auto-created by Airtable as "Name" (singleLineText).
            # We use it as company_name; the script renames it on first run.
            {"name": "sector", "type": "singleSelect", "options": {"choices": [
                {"name": "Petróleo e Gás"},
                {"name": "Construção e Imobiliário"},
                {"name": "Logística e Transportes"},
                {"name": "Telecomunicações"},
                {"name": "Retalho e Comércio"},
                {"name": "Saúde"},
                {"name": "Educação"},
                {"name": "Hotelaria e Turismo"},
                {"name": "Banca e Seguros"},
                {"name": "Outro"},
            ]}},
            {"name": "state", "type": "singleSelect", "options": {"choices": [
                {"name": "prospect"},
                {"name": "contacted"},
                {"name": "lead"},
                {"name": "qualification"},
                {"name": "nurture"},
                {"name": "audit_scheduled"},
                {"name": "audit_completed"},
                {"name": "proposal_sent"},
                {"name": "inactive"},
            ]}},
            {"name": "priority", "type": "singleSelect", "options": {"choices": [
                {"name": "high"},
                {"name": "medium"},
                {"name": "low"},
            ]}},
            {"name": "whatsapp_number", "type": "singleLineText"},
            {"name": "contact_name", "type": "singleLineText"},
            {"name": "decision_maker_name", "type": "singleLineText"},
            {"name": "decision_maker_role", "type": "singleLineText"},
            {"name": "linkedin_url", "type": "url"},
            {"name": "pain_description", "type": "multilineText"},
            {"name": "automation_opportunity", "type": "multilineText"},
            {"name": "qualification_score", "type": "number", "options": {"precision": 0}},
            {"name": "source", "type": "singleSelect", "options": {"choices": [
                {"name": "landing_page"},
                {"name": "prospecting_agent"},
                {"name": "referral"},
                {"name": "manual"},
            ]}},
            {"name": "last_activity_at", "type": "dateTime", "options": {
                "dateFormat": {"name": "iso"},
                "timeFormat": {"name": "24hour"},
                "timeZone": "Africa/Luanda",
            }},
            {"name": "no_response_count", "type": "number", "options": {"precision": 0}},
            {"name": "notes", "type": "multilineText"},
        ],
    },
    "interactions": {
        "description": "Log of every WhatsApp exchange and agent action.",
        "fields": [
            {"name": "type", "type": "singleSelect", "options": {"choices": [
                {"name": "inbound"},
                {"name": "outbound"},
                {"name": "qualification"},
                {"name": "nurture"},
                {"name": "audit"},
                {"name": "content"},
            ]}},
            {"name": "agent", "type": "singleSelect", "options": {"choices": [
                {"name": "bot"},
                {"name": "fidel"},
            ]}},
            {"name": "message_text", "type": "multilineText"},
            {"name": "timestamp", "type": "dateTime", "options": {
                "dateFormat": {"name": "iso"},
                "timeFormat": {"name": "24hour"},
                "timeZone": "Africa/Luanda",
            }},
            {"name": "whatsapp_message_id", "type": "singleLineText"},
        ],
    },
    "errors": {
        "description": "n8n workflow error log. Populated by Workflow 05.",
        "fields": [
            {"name": "workflow_name", "type": "singleLineText"},
            {"name": "node_name", "type": "singleLineText"},
            {"name": "error_message", "type": "multilineText"},
            {"name": "timestamp", "type": "dateTime", "options": {
                "dateFormat": {"name": "iso"},
                "timeFormat": {"name": "24hour"},
                "timeZone": "Africa/Luanda",
            }},
            {"name": "resolved", "type": "checkbox", "options": {
                "icon": "check",
                "color": "greenBright",
            }},
        ],
    },
}

# Added in a second pass once all table IDs are known.
LINK_FIELDS_DEFERRED = [
    {
        "table": "interactions",
        "field": {"name": "company", "type": "multipleRecordLinks"},
        "linked_table_name": "companies",
    },
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_existing_tables() -> dict[str, dict]:
    """Return {table_name: table_metadata_dict} for all tables in the base."""
    resp = requests.get(TABLES_URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return {t["name"]: t for t in resp.json().get("tables", [])}


def create_table(name: str, description: str) -> dict:
    """Cria uma nova tabela com o campo primário obrigatório."""
    payload = {
        "name": name,
        "description": description,
        "fields": [
            # O Airtable exige pelo menos um campo inicial para criar a tabela
            {"name": "Name", "type": "singleLineText"} 
        ]
    }
    resp = requests.post(TABLES_URL, headers=HEADERS, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def create_field(table_id: str, field: dict) -> dict:
    """Add a field to an existing table. Return created field metadata."""
    url = f"{TABLES_URL}/{table_id}/fields"
    resp = requests.post(url, headers=HEADERS, json=field, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ── Main ──────────────────────────────────────────────────────────────────────

def ensure_schema() -> None:
    existing = get_existing_tables()
    created_table_ids: dict[str, str] = {n: t["id"] for n, t in existing.items()}

    # Pass 1 — tables and non-link fields
    for table_name, table_def in SCHEMA.items():
        if table_name not in existing:
            logger.info(f"Creating table: {table_name}")
            new_table = create_table(table_name, table_def["description"])
            created_table_ids[table_name] = new_table["id"]
            existing_field_names: set[str] = {"Name"}
            logger.success(f"✓ Table created: {table_name}")
        else:
            created_table_ids[table_name] = existing[table_name]["id"]
            existing_field_names = {f["name"] for f in existing[table_name].get("fields", [])}
            logger.info(f"↷ Table exists: {table_name} — checking fields")

        for field in table_def["fields"]:
            if field["name"] in existing_field_names:
                logger.debug(f"  ↷ Field exists: {field['name']}")
                continue
            create_field(created_table_ids[table_name], field)
            logger.success(f"  + Field created: {field['name']} ({field['type']})")

    # Pass 2 — link fields (require linked table ID)
    existing = get_existing_tables()  # refresh after pass 1
    for link in LINK_FIELDS_DEFERRED:
        table_name = link["table"]
        table_id = created_table_ids[table_name]
        field_def = dict(link["field"])
        linked_id = created_table_ids.get(link["linked_table_name"])
        if not linked_id:
            logger.warning(f"  ✗ Linked table not found: {link['linked_table_name']} — skipping link field")
            continue

        existing_field_names = {f["name"] for f in existing.get(table_name, {}).get("fields", [])}
        if field_def["name"] in existing_field_names:
            logger.debug(f"  ↷ Link field exists: {field_def['name']} on {table_name}")
            continue

        field_def["options"] = {"linkedTableId": linked_id}
        create_field(table_id, field_def)
        logger.success(f"  + Link field created: {field_def['name']} ({table_name} → {link['linked_table_name']})")


if __name__ == "__main__":
    logger.info("Starting Airtable schema sync…")
    try:
        ensure_schema()
        logger.success("Schema sync complete.")
    except requests.HTTPError as exc:
        logger.error(f"Airtable API error: {exc.response.status_code} — {exc.response.text}")
        sys.exit(1)
