# Airtable Views — BMST Acquisition Engine

Views must be created manually in the Airtable UI (the REST API does not
support programmatic view creation). Use this document as the exact specification.

---

## Table: companies

### View 1 — Active Pipeline
**Type:** Grid  
**Purpose:** Daily working view — all records in active sales motion.

| Setting | Value |
|---------|-------|
| Filter | `state` is any of `lead`, `qualification`, `audit_scheduled`, `audit_completed`, `proposal_sent` |
| Sort | `last_activity_at` → descending |
| Fields shown | company_name (primary), state, priority, contact_name, sector, qualification_score, last_activity_at |
| Fields hidden | all others |

---

### View 2 — New Prospects
**Type:** Grid  
**Purpose:** Fresh records from the prospecting agent or landing page, not yet contacted.

| Setting | Value |
|---------|-------|
| Filter | `state` is `prospect` |
| Sort | Created time → descending |
| Fields shown | company_name, sector, source, pain_description, decision_maker_name, decision_maker_role, linkedin_url |
| Fields hidden | all others |

---

### View 3 — Nurture Queue
**Type:** Grid  
**Purpose:** Leads that did not qualify — scheduled for timed re-engagement.

| Setting | Value |
|---------|-------|
| Filter | `state` is `nurture` |
| Sort | `last_activity_at` → ascending (oldest first — highest re-engagement priority) |
| Fields shown | company_name, contact_name, sector, last_activity_at, no_response_count, notes |
| Fields hidden | all others |

---

### View 4 — Stale Contacts
**Type:** Grid  
**Purpose:** Records that have gone quiet and need manual review.

| Setting | Value |
|---------|-------|
| Filter | `state` is any of `contacted`, `lead` AND `last_activity_at` is before `7 days ago` |
| Sort | `last_activity_at` → ascending |
| Fields shown | company_name, state, contact_name, whatsapp_number, last_activity_at, notes |
| Fields hidden | all others |

---

### View 5 — Qualified Leads
**Type:** Grid  
**Purpose:** Companies that passed the scoring threshold, for audit scheduling follow-up.

| Setting | Value |
|---------|-------|
| Filter | `qualification_score` >= `70` |
| Sort | `qualification_score` → descending |
| Fields shown | company_name, sector, qualification_score, state, contact_name, whatsapp_number, last_activity_at |
| Fields hidden | all others |

---

### View 6 — Kanban by State
**Type:** Kanban  
**Purpose:** Visual pipeline overview for weekly review.

| Setting | Value |
|---------|-------|
| Stack field | `state` |
| Card title | company_name |
| Card fields | sector, contact_name, last_activity_at |
| Hidden stacks | `inactive` |

---

## Table: interactions

### View 1 — Today's Activity
**Type:** Grid  
**Purpose:** Real-time feed of all exchanges today.

| Setting | Value |
|---------|-------|
| Filter | `timestamp` is today |
| Sort | `timestamp` → descending |
| Fields shown | company (linked), type, agent, message_text, timestamp |

---

### View 2 — Bot Conversations
**Type:** Grid  
**Purpose:** All bot-handled qualification exchanges, for prompt tuning review.

| Setting | Value |
|---------|-------|
| Filter | `agent` is `bot` AND `type` is `qualification` |
| Sort | `timestamp` → descending |
| Fields shown | company, type, message_text, timestamp |

---

## Table: errors

### View 1 — Open Errors
**Type:** Grid  
**Purpose:** Unresolved workflow errors requiring action.

| Setting | Value |
|---------|-------|
| Filter | `resolved` is unchecked |
| Sort | `timestamp` → descending |
| Fields shown | workflow_name, node_name, error_message, timestamp, resolved |

---

### View 2 — All Errors
**Type:** Grid  
**Purpose:** Full error history for audit.

| Setting | Value |
|---------|-------|
| Filter | none |
| Sort | `timestamp` → descending |
| Fields shown | all |
