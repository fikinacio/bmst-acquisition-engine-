"""
LinkedIn decision-maker resolver via the Apify API.

Actor: apify/linkedin-jobs-scraper
Reads APIFY_API_TOKEN from environment.

Confidence score (0–100) is computed from three signals:
  - Role match (0–40)   job title contains Director/Manager/CEO/COO/Operations keywords
  - Company match (0–40) actor result company name approximates listing company name
  - Profile completeness (0–20) result has name, headline/role, and URL

Rules:
  - Returns decision_maker_identified=False if confidence_score < 70
  - NEVER fabricates a name — all name/role fields return None if confidence is low

Public API
----------
find_decision_maker(company_name) -> dict
    {
      "decision_maker_name":       str | None,
      "decision_maker_role":       str | None,
      "linkedin_url":              str | None,
      "confidence_score":          int,
      "decision_maker_identified": bool
    }

find_decision_makers_batch(companies) -> list[dict]
    Run find_decision_maker for each company dict; merge results in-place.
"""

import os
import unicodedata
from functools import lru_cache

from apify_client import ApifyClient
from dotenv import load_dotenv
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

_ACTOR_ID = "apify/linkedin-jobs-scraper"
_CONFIDENCE_THRESHOLD = 70

# Titles that strongly indicate decision-making authority
_DECISION_TITLES = [
    "ceo", "chief executive", "presidente", "director geral", "managing director",
    "coo", "chief operating", "director de operacoes", "director operacional",
    "cfo", "chief financial", "director financeiro",
    "director", "directora", "diretor", "diretora",
    "gerente geral", "general manager",
    "head of", "head of operations", "head of finance",
    "vp ", "vice president", "vice-president",
]

_SENIOR_TITLES = [
    "manager", "gestor", "gestora", "gerente",
    "supervisor", "coordenador", "coordenadora",
    "responsavel", "responsável",
]


def _normalise(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _token_overlap(a: str, b: str) -> float:
    """Return fraction of tokens in `a` that also appear in `b`."""
    tokens_a = set(_normalise(a).split())
    tokens_b = set(_normalise(b).split())
    if not tokens_a:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a)


def _score_result(result: dict, target_company: str) -> int:
    """Compute confidence score (0–100) for a LinkedIn search result."""
    score = 0

    # ── Role match (0–40) ─────────────────────────────────────────────────────
    title_raw = (
        result.get("jobTitle") or
        result.get("title") or
        result.get("position") or
        ""
    )
    title = _normalise(title_raw)
    if any(kw in title for kw in _DECISION_TITLES):
        score += 40
    elif any(kw in title for kw in _SENIOR_TITLES):
        score += 20

    # ── Company match (0–40) ──────────────────────────────────────────────────
    result_company = (
        result.get("companyName") or
        result.get("company") or
        result.get("employer") or
        ""
    )
    overlap = _token_overlap(target_company, result_company)
    if overlap >= 0.9:
        score += 40
    elif overlap >= 0.5:
        score += 25
    elif overlap > 0.0:
        score += 10

    # ── Profile completeness (0–20) ───────────────────────────────────────────
    has_name = bool(
        result.get("fullName") or
        result.get("name") or
        result.get("hiringTeamMember", {}).get("name")
    )
    has_link = bool(
        result.get("linkedinUrl") or
        result.get("profileUrl") or
        result.get("link") or
        result.get("url")
    )
    if has_name:
        score += 10
    if has_link:
        score += 10

    return min(100, score)


def _extract_fields(result: dict) -> dict:
    """Pull name, role, and LinkedIn URL from a raw Apify result dict."""
    name = (
        result.get("fullName") or
        result.get("name") or
        (result.get("hiringTeamMember") or {}).get("name") or
        None
    )
    role = (
        result.get("jobTitle") or
        result.get("title") or
        result.get("position") or
        None
    )
    url = (
        result.get("linkedinUrl") or
        result.get("profileUrl") or
        result.get("link") or
        result.get("url") or
        None
    )
    return {"name": name, "role": role, "url": url}


@lru_cache(maxsize=1)
def _client() -> ApifyClient:
    token = os.environ["APIFY_API_TOKEN"]
    return ApifyClient(token)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
def find_decision_maker(company_name: str) -> dict:
    """
    Resolve decision-maker for a company via Apify LinkedIn scraper.

    Returns a dict with decision_maker_name, decision_maker_role,
    linkedin_url, confidence_score, decision_maker_identified.
    All name fields are None when confidence_score < CONFIDENCE_THRESHOLD.
    """
    _null_result = {
        "decision_maker_name": None,
        "decision_maker_role": None,
        "linkedin_url": None,
        "confidence_score": 0,
        "decision_maker_identified": False,
    }

    if not company_name or not company_name.strip():
        return _null_result

    logger.info(f"Apify lookup: {company_name}")
    try:
        run_input = {
            "searchKeywords": company_name,
            "location": "Angola",
            "maxItems": 10,
        }
        run = _client().actor(_ACTOR_ID).call(run_input=run_input)
        items = list(
            _client().dataset(run["defaultDatasetId"]).iterate_items()
        )
    except Exception as exc:
        logger.warning(f"Apify call failed for '{company_name}': {exc}")
        return _null_result

    if not items:
        logger.debug(f"No Apify results for '{company_name}'")
        return _null_result

    # Score each result and pick the best
    best_result = None
    best_score = 0
    for item in items:
        score = _score_result(item, company_name)
        if score > best_score:
            best_score = score
            best_result = item

    if best_score < _CONFIDENCE_THRESHOLD or best_result is None:
        logger.debug(
            f"Low confidence ({best_score}) for '{company_name}' — not identifying"
        )
        return {**_null_result, "confidence_score": best_score}

    fields = _extract_fields(best_result)

    # Final guard: do not return a result if we have no name
    if not fields["name"]:
        return {**_null_result, "confidence_score": best_score}

    logger.info(
        f"Found: {fields['name']} ({fields['role']}) "
        f"at '{company_name}' — score={best_score}"
    )
    return {
        "decision_maker_name": fields["name"],
        "decision_maker_role": fields["role"],
        "linkedin_url": fields["url"],
        "confidence_score": best_score,
        "decision_maker_identified": True,
    }


def find_decision_makers_batch(companies: list[dict]) -> list[dict]:
    """
    Resolve decision-makers for a list of company dicts.

    Each input dict must have a 'company_name' key.
    Returns the same list with decision-maker fields merged in.
    """
    results: list[dict] = []
    seen: dict[str, dict] = {}  # cache within the batch run

    for company in companies:
        name = company.get("company_name", "")
        if name in seen:
            dm = seen[name]
        else:
            dm = find_decision_maker(name)
            seen[name] = dm
        results.append({**company, **dm})

    identified = sum(1 for r in results if r.get("decision_maker_identified"))
    logger.info(
        f"Decision-maker lookup: {identified}/{len(results)} identified"
    )
    return results
