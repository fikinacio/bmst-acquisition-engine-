"""
Automation friction classifier for job board listings.

Two-stage pipeline per listing:
  1. Fast keyword scan (no LLM) — discard with no keywords immediately.
  2. LLM analysis via claude-sonnet-4-6 — nuanced scoring for keyword-matched listings.

Public API
----------
classify_friction(listing) -> dict
    Extend the listing dict with:
      friction_level        "high" | "medium" | "none"
      pain_description      str — one sentence describing the operational pain
      automation_opportunity str — one sentence on what BMST could automate
      discard               bool — True when friction_level == "none"

classify_all_listings(listings) -> list[dict]
    Run classify_friction on each listing; return only those with discard=False.
"""

import json
import re

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from agents.prospecting.tools.scraper import HIGH_FRICTION_KEYWORDS, MEDIUM_FRICTION_KEYWORDS

_MODEL = "claude-sonnet-4-6"

_CLASSIFY_SYSTEM = """\
You are a business process automation expert analysing Angolan job board listings.
Given a job listing (company, title, description), classify its automation friction level.

Return ONLY valid JSON, no markdown:
{
  "friction_level": "high" | "medium" | "none",
  "pain_description": "<one specific sentence about the operational pain, or empty string if none>",
  "automation_opportunity": "<one sentence on what BMST could automate, or empty string if none>"
}

RULES:
- "high": listing explicitly mentions manual data entry, spreadsheet work, invoice processing,
  manual reconciliation, manual payroll, physical document archiving, or similar repetitive tasks.
- "medium": operational/administrative role that implies manual work even if not explicitly stated.
- "none": technical, creative, or strategic roles with no plausible automation angle — OR
  listings where pain_description cannot be specific and credible.
- pain_description and automation_opportunity MUST be specific to this company/role.
  Generic phrases disqualify a listing to "none".
"""


def _normalise(text: str) -> str:
    """Lowercase and remove diacritics for keyword matching."""
    import unicodedata
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _keyword_scan(listing: dict) -> str:
    """Return 'high', 'medium', or 'none' from keyword matching alone."""
    searchable = _normalise(
        f"{listing.get('job_title', '')} {listing.get('description', '')}"
    )
    if any(kw in searchable for kw in HIGH_FRICTION_KEYWORDS):
        return "high"
    if any(kw in searchable for kw in MEDIUM_FRICTION_KEYWORDS):
        return "medium"
    return "none"


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON in LLM response: {text!r}")
    return json.loads(match.group())


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
def _call_llm(listing: dict) -> dict:
    llm = ChatAnthropic(model=_MODEL, temperature=0.1, max_tokens=300)
    user_msg = (
        f"Company: {listing.get('company_name', 'Unknown')}\n"
        f"Job title: {listing.get('job_title', '')}\n"
        f"Description: {listing.get('description', '')[:400]}\n\n"
        "Classify this listing."
    )
    response = llm.invoke([
        SystemMessage(content=_CLASSIFY_SYSTEM),
        HumanMessage(content=user_msg),
    ])
    return _extract_json(response.content)


def classify_friction(listing: dict) -> dict:
    """
    Score a job listing for automation friction.

    Returns a copy of `listing` extended with:
      friction_level, pain_description, automation_opportunity, discard
    """
    result = dict(listing)

    # Stage 1 — fast keyword pre-filter (no LLM cost)
    keyword_level = _keyword_scan(listing)
    if keyword_level == "none":
        logger.debug(f"Keyword scan: discard '{listing.get('job_title', '')}'")
        result.update({
            "friction_level": "none",
            "pain_description": "",
            "automation_opportunity": "",
            "discard": True,
        })
        return result

    # Stage 2 — LLM nuanced classification
    try:
        llm_result = _call_llm(listing)
        friction_level = llm_result.get("friction_level", "none")
        pain = llm_result.get("pain_description", "")
        opp = llm_result.get("automation_opportunity", "")

        # Demote to "none" if LLM couldn't produce specific descriptions
        if friction_level != "none" and (not pain or not opp):
            friction_level = "none"

        result.update({
            "friction_level": friction_level,
            "pain_description": pain,
            "automation_opportunity": opp,
            "discard": friction_level == "none",
        })
        logger.debug(
            f"Classified '{listing.get('job_title', '')}' @ "
            f"'{listing.get('company_name', '')}' → {friction_level}"
        )
    except Exception as exc:
        logger.error(f"LLM classify error: {exc} — defaulting to keyword level={keyword_level}")
        result.update({
            "friction_level": keyword_level,
            "pain_description": "Operational role with likely manual processes.",
            "automation_opportunity": "Process automation assessment required.",
            "discard": False,
        })

    return result


def classify_all_listings(listings: list[dict]) -> list[dict]:
    """Classify a batch of listings; return only those with discard=False."""
    qualified: list[dict] = []
    for listing in listings:
        result = classify_friction(listing)
        if not result.get("discard"):
            qualified.append(result)
    logger.info(f"Classifier: {len(qualified)}/{len(listings)} listings qualified")
    return qualified
