"""
agents/qualification_bot/
LangGraph-powered WhatsApp qualification bot.

Guides prospects through a 4-question conversation to determine fit, then either
books a free process-audit slot via Google Calendar or moves the lead to the
nurture sequence. State is persisted to Airtable after every exchange.

Entry point : graph.py  →  build_graph() returns the compiled LangGraph StateGraph
FastAPI route: api/main.py  →  POST /qualify
"""
