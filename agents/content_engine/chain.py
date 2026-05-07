"""
LangChain content generation pipeline (PRD Section 9).

Pipeline steps:
  1. Generate LinkedIn and Instagram drafts using prompts from prompts.py
  2. Validate each draft through validators in templates.py
  3. If validation fails: regenerate once, appending violation list to prompt
  4. Return final JSON output

Input dict:
  {
    "company_name":    str,   # used internally only — never appears in output
    "sector":          str,
    "pain_description": str,
    "audit_notes":     str,
    "market":          str    # e.g. "Angola"
  }

Output dict:
  {
    "linkedin_body":   str,   # 150-250 words, no company names, no forbidden phrases
    "instagram_body":  str,   # < 100 words, ends with audit.biscaplus.com
    "suggested_visual": str   # description of an image/graphic that fits the post
  }

Usage:
    from agents.content_engine.chain import run_content_chain
    result = run_content_chain(payload)
"""

import os

from langchain_anthropic import ChatAnthropic
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from loguru import logger

from agents.content_engine.prompts import INSTAGRAM_POST_PROMPT, LINKEDIN_POST_PROMPT
from agents.content_engine.templates import (
    validate_instagram_post,
    validate_linkedin_post,
)

_MODEL = "claude-sonnet-4-6"
_MAX_RETRIES = 1  # one regeneration attempt after initial failure


def _build_llm() -> ChatAnthropic:
    return ChatAnthropic(
        model=_MODEL,
        temperature=0.7,
        max_tokens=1024,
        api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )


def _generate_linkedin(llm: ChatAnthropic, context: dict, validation_issues: str = "") -> dict:
    """Call LLM to produce linkedin_body + suggested_visual. Returns parsed dict."""
    prompt = ChatPromptTemplate.from_template(LINKEDIN_POST_PROMPT)
    chain = prompt | llm | JsonOutputParser()
    return chain.invoke({
        "sector": context["sector"],
        "pain_description": context["pain_description"],
        "audit_notes": context["audit_notes"],
        "market": context["market"],
        "validation_issues": validation_issues or "None.",
    })


def _generate_instagram(llm: ChatAnthropic, context: dict, validation_issues: str = "") -> dict:
    """Call LLM to produce instagram_body. Returns parsed dict."""
    prompt = ChatPromptTemplate.from_template(INSTAGRAM_POST_PROMPT)
    chain = prompt | llm | JsonOutputParser()
    return chain.invoke({
        "sector": context["sector"],
        "pain_description": context["pain_description"],
        "audit_notes": context["audit_notes"],
        "market": context["market"],
        "validation_issues": validation_issues or "None.",
    })


def run_content_chain(payload: dict) -> dict:
    """
    Run the content generation pipeline.

    Returns {"linkedin_body": str, "instagram_body": str, "suggested_visual": str}.
    Raises ValueError if validation still fails after the single retry.
    """
    context = {
        "sector": payload.get("sector", ""),
        "pain_description": payload.get("pain_description", ""),
        "audit_notes": payload.get("audit_notes", ""),
        "market": payload.get("market", "Angola"),
    }

    llm = _build_llm()

    # ── LinkedIn ──────────────────────────────────────────────────────────────
    logger.info("content_engine | generating LinkedIn post")
    li_result = _generate_linkedin(llm, context)
    linkedin_body: str = li_result.get("linkedin_body", "")
    suggested_visual: str = li_result.get("suggested_visual", "")

    li_valid, li_violations = validate_linkedin_post(linkedin_body)
    if not li_valid:
        issues_str = "\n".join(f"- {v}" for v in li_violations)
        logger.warning(f"LinkedIn validation failed ({len(li_violations)} issue(s)) — retrying:\n{issues_str}")
        li_result = _generate_linkedin(llm, context, validation_issues=issues_str)
        linkedin_body = li_result.get("linkedin_body", "")
        suggested_visual = li_result.get("suggested_visual", suggested_visual)
        li_valid, li_violations = validate_linkedin_post(linkedin_body)
        if not li_valid:
            raise ValueError(f"LinkedIn post failed validation after retry: {li_violations}")

    # ── Instagram ─────────────────────────────────────────────────────────────
    logger.info("content_engine | generating Instagram caption")
    ig_result = _generate_instagram(llm, context)
    instagram_body: str = ig_result.get("instagram_body", "")

    ig_valid, ig_violations = validate_instagram_post(instagram_body)
    if not ig_valid:
        issues_str = "\n".join(f"- {v}" for v in ig_violations)
        logger.warning(f"Instagram validation failed ({len(ig_violations)} issue(s)) — retrying:\n{issues_str}")
        ig_result = _generate_instagram(llm, context, validation_issues=issues_str)
        instagram_body = ig_result.get("instagram_body", "")
        ig_valid, ig_violations = validate_instagram_post(instagram_body)
        if not ig_valid:
            raise ValueError(f"Instagram post failed validation after retry: {ig_violations}")

    logger.info("content_engine | both posts generated and validated")
    return {
        "linkedin_body": linkedin_body,
        "instagram_body": instagram_body,
        "suggested_visual": suggested_visual,
    }
