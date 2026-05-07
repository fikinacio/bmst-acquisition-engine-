"""
agents/content_engine/
LangChain pipeline that generates anonymised LinkedIn and Instagram posts
from completed audit notes.

Anonymisation rules (PRD Section 19): company names, employee counts, and any
identifying details must not appear in output. Only facts present in audit_notes
may be referenced — no statistics are fabricated.

Entry point : chain.py  →  run_content_chain(payload)
FastAPI route: api/main.py  →  POST /generate-content
"""
