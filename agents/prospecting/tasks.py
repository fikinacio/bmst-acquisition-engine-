"""
crewAI Task definitions for the prospecting crew.

Execution order (sequential):
  scrape_task    → assigned to scraper_agent
  classify_task  → assigned to classifier_agent, depends on scrape_task
  resolve_task   → assigned to decision_finder_agent, depends on classify_task

Output contract (one dict per final prospect):
  {
    "company_name":              str,
    "sector":                    str,
    "source_url":                str,
    "friction_level":            "high" | "medium",
    "pain_description":          str,
    "automation_opportunity":    str,
    "decision_maker_name":       str | null,
    "decision_maker_role":       str | null,
    "linkedin_url":              str | null,
    "confidence_score":          int,
    "decision_maker_identified": bool
  }
"""

from crewai import Task
from loguru import logger


def build_scrape_task(agent) -> Task:
    """Scrape all configured Angolan job board sources."""
    return Task(
        description=(
            "Use the scrape_all_job_board_sources tool to retrieve all job listings "
            "from the three configured Angolan job boards: emprego.co.ao, jobartis.com, "
            "and angoemprego.co.ao.\n\n"
            "Call the tool ONCE. Do not filter, modify, or summarise the results.\n\n"
            "Your final answer must be the raw JSON string returned by the tool, "
            "containing the complete list of listing dicts."
        ),
        expected_output=(
            "A valid JSON array of raw listing dicts, each containing: "
            "company_name, job_title, description, url, source. "
            "Example: [{\"company_name\": \"Empresa X\", \"job_title\": \"Assistente Administrativo\", "
            "\"description\": \"...\", \"url\": \"https://...\", \"source\": \"emprego.co.ao\"}]"
        ),
        agent=agent,
    )


def build_classify_task(agent, scrape_task: Task) -> Task:
    """Score each listing for automation friction; discard friction_level='none'."""
    return Task(
        description=(
            "You will receive the output of the scraping task as context — "
            "a JSON array of raw job listings.\n\n"
            "Use the classify_all_listings tool ONCE, passing the complete listings JSON "
            "from context as the listings_json argument.\n\n"
            "The tool returns only qualified listings (friction_level 'high' or 'medium'). "
            "Do not add, remove, or modify any listings — return the tool output exactly.\n\n"
            "Your final answer must be the JSON string returned by the tool."
        ),
        expected_output=(
            "A valid JSON array of qualified listing dicts enriched with: "
            "friction_level ('high' or 'medium'), pain_description (one specific sentence), "
            "automation_opportunity (one specific sentence), discard (false for all entries). "
            "Listings with friction_level='none' must not appear in the output."
        ),
        agent=agent,
        context=[scrape_task],
    )


def build_resolve_task(agent, classify_task: Task) -> Task:
    """Resolve decision-maker for each qualified company. Never fabricate names."""
    return Task(
        description=(
            "You will receive the output of the classify task as context — "
            "a JSON array of qualified company listings.\n\n"
            "Use the find_decision_makers_for_companies tool ONCE, passing the complete "
            "qualified listings JSON from context as the companies_json argument.\n\n"
            "The tool adds decision-maker fields to each company dict. "
            "Do not modify, merge, or reorder records. Return the tool output exactly.\n\n"
            "IMPORTANT: decision_maker_identified=false is a valid and acceptable result "
            "for some companies. Do not fabricate names or omit these companies.\n\n"
            "Your final answer must be the JSON string returned by the tool — "
            "this is the final prospect list that will be posted to the CRM."
        ),
        expected_output=(
            "A valid JSON array of prospect dicts matching the output schema exactly: "
            "company_name, sector, source_url, friction_level, pain_description, "
            "automation_opportunity, decision_maker_name (str or null), "
            "decision_maker_role (str or null), linkedin_url (str or null), "
            "confidence_score (0-100), decision_maker_identified (bool). "
            "All qualified companies from the classify task must appear in this output."
        ),
        agent=agent,
        context=[classify_task],
        output_file="prospecting_output.json",
    )
