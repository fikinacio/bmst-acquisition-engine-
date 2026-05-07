"""
crewAI Crew assembly and execution entry point for the prospecting pipeline.

run_crew()
  1. Builds the three agents (agents.py) and three tasks (tasks.py)
  2. Assembles a sequential Crew
  3. Executes the crew; parses the resolve_task JSON output
  4. POSTs the prospect list to N8N_WEBHOOK_BASE_URL + N8N_PROSPECTING_WEBHOOK_PATH
  5. Returns the list of prospect dicts

Usage:
  from agents.prospecting.crew import run_crew
  prospects = run_crew()
"""

import json
import os
import re

import requests
from crewai import Crew, Process
from dotenv import load_dotenv
from loguru import logger

from agents.prospecting.agents import (
    build_classifier_agent,
    build_decision_finder_agent,
    build_scraper_agent,
)
from agents.prospecting.tasks import (
    build_classify_task,
    build_resolve_task,
    build_scrape_task,
)

load_dotenv()

_WEBHOOK_TIMEOUT = 30


def _parse_crew_output(raw: object) -> list[dict]:
    """
    Extract a list of prospect dicts from the crew's final task output.

    crewAI may return a string, a CrewOutput object, or already-parsed data.
    We try JSON extraction from whatever we receive.
    """
    # CrewOutput wrapper (crewAI >= 0.28)
    if hasattr(raw, "raw"):
        raw = raw.raw

    text = str(raw) if not isinstance(raw, str) else raw

    # Look for a JSON array inside the output
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Try the whole string as JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict) and "prospects" in parsed:
            return parsed["prospects"]
    except json.JSONDecodeError:
        pass

    logger.warning("Could not parse crew output as JSON — returning empty list")
    return []


def _post_to_n8n(prospects: list[dict]) -> None:
    base = os.environ.get("N8N_WEBHOOK_BASE_URL", "").rstrip("/")
    path = os.environ.get("N8N_PROSPECTING_WEBHOOK_PATH", "/webhook/prospecting").lstrip("/")

    if not base:
        logger.warning("N8N_WEBHOOK_BASE_URL not set — skipping webhook POST")
        return

    url = f"{base}/{path}"
    try:
        response = requests.post(url, json=prospects, timeout=_WEBHOOK_TIMEOUT)
        response.raise_for_status()
        logger.info(f"Posted {len(prospects)} prospects to n8n: {url} → {response.status_code}")
    except requests.RequestException as exc:
        logger.error(f"Failed to POST prospects to n8n ({url}): {exc}")


def run_crew() -> list[dict]:
    """Assemble and run the prospecting crew. POST results to n8n. Return prospects."""
    logger.info("Prospecting crew: starting run")

    scraper_agent = build_scraper_agent()
    classifier_agent = build_classifier_agent()
    decision_finder_agent = build_decision_finder_agent()

    scrape_task = build_scrape_task(scraper_agent)
    classify_task = build_classify_task(classifier_agent, scrape_task)
    resolve_task = build_resolve_task(decision_finder_agent, classify_task)

    crew = Crew(
        agents=[scraper_agent, classifier_agent, decision_finder_agent],
        tasks=[scrape_task, classify_task, resolve_task],
        process=Process.sequential,
        verbose=True,
    )

    raw_output = crew.kickoff()
    prospects = _parse_crew_output(raw_output)

    logger.info(f"Prospecting crew: {len(prospects)} final prospects")
    _post_to_n8n(prospects)
    return prospects
