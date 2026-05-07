"""
Airtable CRM helpers for the qualification bot.

Reads AIRTABLE_API_KEY and AIRTABLE_BASE_ID from environment via python-dotenv.
All external calls wrapped with @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8)).

Public API
----------
get_company_by_whatsapp(number) -> dict | None
    Look up a company record by whatsapp_number. Returns the full Airtable record
    dict (including 'id' and 'fields') or None if not found.

update_company_state(company_id, updates) -> bool
    Patch any set of fields on a company record. Returns True on success.

log_interaction(company_id, interaction) -> str
    Create a record in the interactions table linked to the given company.
    Returns the new record_id.
"""

import os

from dotenv import load_dotenv
from loguru import logger
from pyairtable import Api
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

_TABLE_COMPANIES = "companies"
_TABLE_INTERACTIONS = "interactions"


def _api() -> Api:
    return Api(os.environ["AIRTABLE_API_KEY"])


def _companies():
    return _api().table(os.environ["AIRTABLE_BASE_ID"], _TABLE_COMPANIES)


def _interactions():
    return _api().table(os.environ["AIRTABLE_BASE_ID"], _TABLE_INTERACTIONS)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
def get_company_by_whatsapp(number: str) -> dict | None:
    """Return the Airtable company record for this WhatsApp number, or None."""
    logger.debug(f"Airtable lookup by WhatsApp: {number}")
    formula = f"{{whatsapp_number}}='{number}'"
    records = _companies().all(formula=formula)
    if records:
        logger.debug(f"Found company: {records[0]['id']}")
        return records[0]
    logger.debug("No company found for this number")
    return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
def update_company_state(company_id: str, updates: dict) -> bool:
    """Patch company fields. Return True on success."""
    logger.debug(f"Updating company {company_id}: {list(updates.keys())}")
    _companies().update(company_id, updates)
    return True


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
def log_interaction(company_id: str, interaction: dict) -> str:
    """Create an interactions record linked to company_id. Return record_id."""
    logger.debug(f"Logging interaction for company {company_id}: type={interaction.get('type')}")
    payload = {"company": [company_id], **interaction}
    record = _interactions().create(payload)
    return record["id"]
