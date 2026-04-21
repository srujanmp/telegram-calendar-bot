import os
import json
import base64
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

# Persistent path — mount a Railway Volume here if you want token refresh to survive restarts
TOKEN_PATH = Path(os.environ.get("TOKEN_PATH", "/data/token.json"))
CREDS_PATH = Path("credentials.json")  # only needed for first local auth


def _load_creds() -> Credentials | None:
    """
    Priority:
    1. GOOGLE_TOKEN_JSON env var (base64-encoded token.json) — used on Railway
    2. File at TOKEN_PATH                                    — used with a Volume
    3. Local credentials.json + OAuth flow                   — local dev only
    """
    creds = None

    # 1. env var (Railway)
    token_b64 = os.environ.get("GOOGLE_TOKEN_JSON", "")
    if token_b64:
        try:
            token_data = json.loads(base64.b64decode(token_b64).decode())
            creds = Credentials.from_authorized_user_info(token_data, SCOPES)
            logger.info("Loaded credentials from GOOGLE_TOKEN_JSON env var")
        except Exception as e:
            logger.warning(f"Failed to parse GOOGLE_TOKEN_JSON: {e}")

    # 2. token file (volume / local)
    if creds is None and TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        logger.info(f"Loaded credentials from {TOKEN_PATH}")

    return creds


def _save_creds(creds: Credentials):
    """Persist refreshed credentials so the container doesn't re-auth on restart."""
    try:
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_PATH.write_text(creds.to_json())
        logger.info(f"Token saved to {TOKEN_PATH}")
    except Exception as e:
        logger.warning(f"Could not save token to {TOKEN_PATH}: {e}")


def _get_service():
    creds = _load_creds()

    if creds and creds.expired and creds.refresh_token:
        logger.info("Access token expired — refreshing…")
        creds.refresh(Request())
        _save_creds(creds)

    if not creds or not creds.valid:
        if not CREDS_PATH.exists():
            raise RuntimeError(
                "No valid credentials found and credentials.json is missing. "
                "Run auth locally first (see README) and set GOOGLE_TOKEN_JSON."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
        creds = flow.run_local_server(port=0)
        _save_creds(creds)

    return build("calendar", "v3", credentials=creds)


class CalendarService:
    def __init__(self):
        self._svc = _get_service()

    # ── Create ────────────────────────────────────────────────────────────────

    def create_event(self, parsed: dict) -> dict | None:
        """
        Create event/task with support for:
        - All-day events (has_time=false)
        - Multiple dates
        - Recurring events (birthdays)
        - Tasks (event_type="task")
        - Color assignment
        """
        try:
            has_time = parsed.get("has_time", True)
            event_type = parsed.get("event_type", "event")

            # Build start/end times
            if has_time:
                start_dt = datetime.fromisoformat(parsed["start_datetime"])
                duration_minutes = int(parsed.get("duration_minutes", 60))
                end_dt = start_dt + timedelta(minutes=duration_minutes)

                start = {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Kolkata"}
                end = {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Kolkata"}
            else:
                # All-day event (date-only format)
                start_date = parsed["start_datetime"]
                end_dt_obj = datetime.fromisoformat(parsed.get("end_datetime", start_date))
                end_date = (end_dt_obj + timedelta(days=1)).strftime("%Y-%m-%d")

                start = {"date": start_date}
                end = {"date": end_date}

            # Base event body
            body = {
                "summary": parsed["title"],
                "description": parsed.get("description", ""),
                "start": start,
                "end": end,
            }

            # Add color if specified
            if "color" in parsed:
                body["colorId"] = parsed["color"]

            # Add recurrence for birthdays
            if parsed.get("is_recurring") and parsed.get("recurrence") == "YEARLY":
                body["recurrence"] = ["RRULE:FREQ=YEARLY"]

            # Add reminders (skip for all-day events and tasks)
            if has_time and event_type != "task":
                body["reminders"] = {
                    "useDefault": False,
                    "overrides": [
                        {"method": "popup", "minutes": 60 * 24},   # 1 day
                        {"method": "popup", "minutes": 60},         # 1 hour
                        {"method": "popup", "minutes": 15},         # 15 min
                    ],
                }

            result = self._svc.events().insert(calendarId=CALENDAR_ID, body=body).execute()
            logger.info(f"Created {event_type}: {result.get('id')}")

            # Handle multiple dates - create additional events if dates list provided
            created_events = [result]
            dates_list = parsed.get("dates", [])
            if dates_list and len(dates_list) > 1:
                # Skip first date as we already created it
                for date_str in dates_list[1:]:
                    if has_time:
                        # Shift time to new date
                        orig_time = start_dt.strftime("%H:%M:%S")
                        new_start_dt = datetime.fromisoformat(f"{date_str}T{orig_time}+05:30")
                        new_end_dt = new_start_dt + timedelta(minutes=duration_minutes)

                        body["start"] = {"dateTime": new_start_dt.isoformat(), "timeZone": "Asia/Kolkata"}
                        body["end"] = {"dateTime": new_end_dt.isoformat(), "timeZone": "Asia/Kolkata"}
                    else:
                        # All-day event
                        next_date = (datetime.fromisoformat(date_str) + timedelta(days=1)).strftime("%Y-%m-%d")
                        body["start"] = {"date": date_str}
                        body["end"] = {"date": next_date}

                    extra_event = self._svc.events().insert(calendarId=CALENDAR_ID, body=body).execute()
                    created_events.append(extra_event)
                    logger.info(f"Created additional event for {date_str}: {extra_event.get('id')}")

            return result  # Return first event

        except HttpError as e:
            logger.error(f"create_event HttpError: {e}")
            return None
        except Exception as e:
            logger.error(f"create_event error: {e}")
            return None

    # ── List ──────────────────────────────────────────────────────────────────

    def list_upcoming(self, max_results: int = 10) -> list:
        try:
            now = datetime.now(timezone.utc).isoformat()
            result = self._svc.events().list(
                calendarId=CALENDAR_ID,
                timeMin=now,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime",
            ).execute()
            return result.get("items", [])
        except Exception as e:
            logger.error(f"list_upcoming error: {e}")
            return []

    # ── Get ───────────────────────────────────────────────────────────────────

    def get_event(self, event_id: str) -> dict | None:
        try:
            return self._svc.events().get(calendarId=CALENDAR_ID, eventId=event_id).execute()
        except Exception as e:
            logger.error(f"get_event error: {e}")
            return None

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete_event(self, event_id: str) -> bool:
        try:
            self._svc.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
            logger.info(f"Deleted event: {event_id}")
            return True
        except Exception as e:
            logger.error(f"delete_event error: {e}")
            return False

    # ── Update ────────────────────────────────────────────────────────────────

    def update_event(self, event_id: str, patch: dict) -> bool:
        try:
            current = self.get_event(event_id)
            if not current:
                return False
            current.update(patch)
            self._svc.events().update(
                calendarId=CALENDAR_ID, eventId=event_id, body=current
            ).execute()
            logger.info(f"Updated event: {event_id}")
            return True
        except Exception as e:
            logger.error(f"update_event error: {e}")
            return False
