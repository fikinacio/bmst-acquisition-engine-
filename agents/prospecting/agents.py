"""
crewAI Agent definitions for the prospecting crew (PRD Section 7).

Three agents run sequentially:
  scraper_agent      scrapes job boards for raw listings
  classifier_agent   scores each listing for automation friction
  decision_finder_agent  resolves decision-maker contacts via LinkedIn/Apify

All agents use claude-sonnet-4-6 via langchain-anthropic.
System backstories are imported from prompts.py (PRD 12.1, 12.2, 12.3).
"""

import json
from typing import Type

from crewai import Agent
from crewai.tools import BaseTool
from langchain_anthropic import ChatAnthropic
from loguru import logger
from pydantic import BaseModel, Field

from agents.prospecting import prompts
from agents.prospecting.tools.classifier import classify_all_listings
from agents.prospecting.tools.decision_finder import find_decision_makers_batch
from agents.prospecting.tools.scraper import scrape_all_sources

_MODEL = "claude-sonnet-4-6"


def _llm() -> ChatAnthropic:
    return ChatAnthropic(model=_MODEL, temperature=0.2, max_tokens=4096)


# ── Tool schemas ───────────────────────────────────────────────────────────────

class _EmptyInput(BaseModel):
    query: str = Field(default="", description="Not used — scrapes all configured sources")


class _ListingsInput(BaseModel):
    listings_json: str = Field(
        ...,
        description="JSON string of raw listing dicts to classify",
    )


class _CompaniesInput(BaseModel):
    companies_json: str = Field(
        ...,
        description="JSON string of qualified listing dicts (must have company_name key)",
    )


# ── crewAI tool classes ────────────────────────────────────────────────────────

class ScrapeJobBoardsTool(BaseTool):
    name: str = "scrape_all_job_board_sources"
    description: str = (
        "Scrapes all configured Angolan job board sources "
        "(emprego.co.ao, jobartis.com, angoemprego.co.ao) "
        "and returns a JSON string containing a list of raw job listing dicts. "
        "Each dict has: company_name, job_title, description, url, source. "
        "Call this tool once to retrieve all raw listings."
    )
    args_schema: Type[BaseModel] = _EmptyInput

    def _run(self, query: str = "") -> str:
        listings = scrape_all_sources()
        logger.info(f"ScrapeJobBoardsTool: {len(listings)} listings")
        return json.dumps(listings, ensure_ascii=False)


class ClassifyListingsTool(BaseTool):
    name: str = "classify_all_listings"
    description: str = (
        "Classifies all raw job listings for automation friction. "
        "Input: JSON string of listing dicts (from scrape_all_job_board_sources). "
        "Output: JSON string of qualified listings (friction_level='high' or 'medium') "
        "enriched with: friction_level, pain_description, automation_opportunity, discard. "
        "Listings with discard=True are excluded from the output. "
        "Call this tool once with the full listings JSON."
    )
    args_schema: Type[BaseModel] = _ListingsInput

    def _run(self, listings_json: str) -> str:
        try:
            listings = json.loads(listings_json)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid JSON input: {exc}"})
        qualified = classify_all_listings(listings)
        logger.info(f"ClassifyListingsTool: {len(qualified)} qualified")
        return json.dumps(qualified, ensure_ascii=False)


class FindDecisionMakersTool(BaseTool):
    name: str = "find_decision_makers_for_companies"
    description: str = (
        "Resolves LinkedIn decision-maker contacts for a list of qualified companies. "
        "Input: JSON string of company dicts (each must have a 'company_name' key). "
        "Output: JSON string of the same dicts enriched with: "
        "decision_maker_name, decision_maker_role, linkedin_url, "
        "confidence_score, decision_maker_identified. "
        "Returns null for name fields when confidence_score < 70. "
        "NEVER fabricates names — low-confidence results are returned as-is. "
        "Call this tool once with the full qualified companies JSON."
    )
    args_schema: Type[BaseModel] = _CompaniesInput

    def _run(self, companies_json: str) -> str:
        try:
            companies = json.loads(companies_json)
        except json.JSONDecodeError as exc:
            return json.dumps({"error": f"Invalid JSON input: {exc}"})
        results = find_decision_makers_batch(companies)
        logger.info(f"FindDecisionMakersTool: {len(results)} companies processed")
        return json.dumps(results, ensure_ascii=False)


# ── Agent factory functions ────────────────────────────────────────────────────

def build_scraper_agent() -> Agent:
    """Construct and return the job-board scraper crewAI agent."""
    return Agent(
        role="Angolan Job Board Scraper",
        goal=(
            "Discover companies posting roles that signal manual or operational pain "
            "by scraping all configured Angolan job board sources and returning the "
            "complete list of raw job listings."
        ),
        backstory=prompts.SCRAPER_SYSTEM_PROMPT,
        llm=_llm(),
        tools=[ScrapeJobBoardsTool()],
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )


def build_classifier_agent() -> Agent:
    """Construct and return the friction classifier crewAI agent."""
    return Agent(
        role="Automation Friction Classifier",
        goal=(
            "Analyse every raw job listing and identify companies with genuine automation "
            "pain. Produce specific, credible pain_description and automation_opportunity "
            "for each qualified listing. Discard listings with no plausible automation angle."
        ),
        backstory=prompts.CLASSIFIER_SYSTEM_PROMPT,
        llm=_llm(),
        tools=[ClassifyListingsTool()],
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )


def build_decision_finder_agent() -> Agent:
    """Construct and return the decision-maker resolver crewAI agent."""
    return Agent(
        role="Decision-Maker Resolver",
        goal=(
            "Find the right person to contact at each qualified company — "
            "the decision-maker who controls operational processes and could authorise "
            "an automation project. Never fabricate names or roles."
        ),
        backstory=prompts.DECISION_FINDER_SYSTEM_PROMPT,
        llm=_llm(),
        tools=[FindDecisionMakersTool()],
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )
