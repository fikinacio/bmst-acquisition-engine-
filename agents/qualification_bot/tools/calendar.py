"""
Google Calendar integration for the qualification bot.

Auth: service account JSON file at path GOOGLE_SERVICE_ACCOUNT_JSON.
Timezone: Africa/Luanda (WAT = UTC+1).

Public API
----------
get_available_slots(days_ahead=7) -> list[str]
    Returns up to two ISO 8601 datetime strings for free 30-min slots.
    Constraints: 09:00–17:00 WAT, Mon–Fri, minimum 48 h from now.

book_slot(slot_iso, company_name, contact_name, whatsapp_number) -> str
    Creates a Google Calendar event and returns the event_id.

All external calls wrapped with @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8)).
"""

import json
import os
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

WAT = timezone(timedelta(hours=1))
_SCOPES = ["https://www.googleapis.com/auth/calendar"]
_SLOT_DURATION_MINUTES = 30
_WORK_START_HOUR = 9
_WORK_END_HOUR = 17
_MIN_LEAD_HOURS = 48


def _get_service():
    import base64
    raw = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
    if os.path.isfile(raw):
        with open(raw) as f:
            creds_dict = json.load(f)
    elif raw.startswith("{"):
        creds_dict = json.loads(raw)
    else:
        creds_dict = json.loads(base64.b64decode(raw).decode())
    creds = service_account.Credentials.from_service_account_info(
        creds_dict, scopes=_SCOPES
    )
    return build("calendar", "v3", credentials=creds)


def _format_slot_for_display(iso: str) -> str:
    """Return a human-friendly PT-PT date string for WhatsApp messages."""
    dt = datetime.fromisoformat(iso)
    weekdays = ["Segunda-feira", "Terça-feira", "Quarta-feira",
                "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    months = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
              "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    return (
        f"{weekdays[dt.weekday()]}, {dt.day} de {months[dt.month - 1]} às {dt.strftime('%H:%M')}"
    )


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
def get_available_slots(days_ahead: int = 7) -> list[str]:
    """Return up to two available 30-min audit slot ISO strings."""
    service = _get_service()
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

    now = datetime.now(WAT)
    earliest_start = now + timedelta(hours=_MIN_LEAD_HOURS)

    slots: list[str] = []
    current_day = earliest_start.date()
    end_date = (now + timedelta(days=days_ahead)).date()

    while current_day <= end_date and len(slots) < 2:
        # Skip weekends
        if current_day.weekday() >= 5:
            current_day += timedelta(days=1)
            continue

        day_start = datetime(
            current_day.year, current_day.month, current_day.day,
            _WORK_START_HOUR, 0, tzinfo=WAT,
        )
        day_end = datetime(
            current_day.year, current_day.month, current_day.day,
            _WORK_END_HOUR, 0, tzinfo=WAT,
        )

        # Advance day_start past the minimum lead time if needed
        if day_start < earliest_start:
            minutes_past = int((earliest_start - day_start).total_seconds() // 60)
            # Ceil to next 30-minute boundary
            slots_to_skip = (minutes_past + _SLOT_DURATION_MINUTES - 1) // _SLOT_DURATION_MINUTES
            day_start = day_start + timedelta(minutes=slots_to_skip * _SLOT_DURATION_MINUTES)

        if day_start >= day_end:
            current_day += timedelta(days=1)
            continue

        # Query Google Calendar freebusy for this day
        freebusy_body = {
            "timeMin": day_start.isoformat(),
            "timeMax": day_end.isoformat(),
            "items": [{"id": calendar_id}],
        }
        result = service.freebusy().query(body=freebusy_body).execute()
        busy_periods = result["calendars"][calendar_id]["busy"]

        busy: list[tuple[datetime, datetime]] = [
            (
                datetime.fromisoformat(b["start"]).astimezone(WAT),
                datetime.fromisoformat(b["end"]).astimezone(WAT),
            )
            for b in busy_periods
        ]

        # Walk through 30-min slots and collect free ones
        cursor = day_start
        while cursor + timedelta(minutes=_SLOT_DURATION_MINUTES) <= day_end and len(slots) < 2:
            slot_end = cursor + timedelta(minutes=_SLOT_DURATION_MINUTES)
            is_busy = any(b_start < slot_end and b_end > cursor for b_start, b_end in busy)
            if not is_busy:
                slots.append(cursor.isoformat())
                logger.debug(f"Free slot found: {cursor.isoformat()}")
            cursor += timedelta(minutes=_SLOT_DURATION_MINUTES)

        current_day += timedelta(days=1)

    logger.info(f"get_available_slots: found {len(slots)} slot(s)")
    return slots


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=8))
def book_slot(
    slot_iso: str,
    company_name: str,
    contact_name: str,
    whatsapp_number: str,
) -> str:
    """Create Google Calendar event for a 30-min audit. Return event_id."""
    service = _get_service()
    calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

    start = datetime.fromisoformat(slot_iso)
    end = start + timedelta(minutes=_SLOT_DURATION_MINUTES)

    event_body = {
        "summary": f"Auditoria BMST — {company_name}",
        "description": (
            f"Contacto: {contact_name}\n"
            f"WhatsApp: +{whatsapp_number}\n\n"
            "Auditoria de processos gratuita de 30 minutos.\n"
            "Agendado automaticamente pelo qualification bot."
        ),
        "start": {"dateTime": start.isoformat(), "timeZone": "Africa/Luanda"},
        "end": {"dateTime": end.isoformat(), "timeZone": "Africa/Luanda"},
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "email", "minutes": 60},
                {"method": "popup", "minutes": 15},
            ],
        },
    }

    created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
    event_id = created["id"]
    logger.info(f"Booked: {slot_iso} for {company_name} — event_id={event_id}")
    return event_id
