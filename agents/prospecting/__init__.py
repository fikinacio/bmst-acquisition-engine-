"""
agents/prospecting/
crewAI crew that discovers qualified B2B prospects from Angolan job boards.

Three agents run in sequence:
  1. ScraperAgent         scrapes job listings from configured sources
  2. ClassifierAgent      scores each listing for automation friction
  3. DecisionFinderAgent  resolves the right decision-maker via Apify/LinkedIn

Output: JSON list of qualified prospect dicts → POSTed to N8N_PROSPECTING_WEBHOOK_PATH.

Entry point : crew.py  →  run_crew()
FastAPI route: api/main.py  →  POST /run-prospecting
"""
