"""
Telegram Calendar Bot - AWS Lambda Single File Version
Webhook-based (not polling) for optimal Lambda compatibility
"""

import os
import json
import re
import base64
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

import boto3
from openai import OpenAI
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ──────────────────────────────────────────────────────────────────────────────
# LOGGING & CONFIG
# ──────────────────────────────────────────────────────────────────────────────

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", 0))
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GOOGLE_CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")
GOOGLE_TOKEN_JSON_B64 = os.environ.get("GOOGLE_TOKEN_JSON", "")

IST = "Asia/Kolkata"
BASE_URL = "https://api.telegram.org/bot" + TELEGRAM_TOKEN

# Color mapping
COLORS = {
    "birthday": "7", "exam": "1", "submission": "2", "lecture": "3",
    "meeting": "4", "deadline": "5", "task": "6", "other": "8"
}

# ──────────────────────────────────────────────────────────────────────────────
# GOOGLE CALENDAR
# ──────────────────────────────────────────────────────────────────────────────

def get_google_service():
    """Load Google credentials from base64 env var"""
    try:
        if not GOOGLE_TOKEN_JSON_B64:
            logger.error("GOOGLE_TOKEN_JSON not set")
            return None

        token_data = json.loads(base64.b64decode(GOOGLE_TOKEN_JSON_B64).decode())
        creds = Credentials.from_authorized_user_info(
            token_data, ["https://www.googleapis.com/auth/calendar"]
        )

        if creds.expired and creds.refresh_token:
            creds.refresh(Request())

        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        logger.error(f"Google auth failed: {e}")
        return None

def create_calendar_event(parsed: Dict) -> Optional[Dict]:
    """Create event in Google Calendar"""
    try:
        service = get_google_service()
        if not service:
            return None

        has_time = parsed.get("has_time", True)

        # Build start/end
        if has_time:
            start_dt = datetime.fromisoformat(parsed["start_datetime"])
            duration_min = int(parsed.get("duration_minutes", 60))
            end_dt = start_dt + timedelta(minutes=duration_min)
            start = {"dateTime": start_dt.isoformat(), "timeZone": IST}
            end = {"dateTime": end_dt.isoformat(), "timeZone": IST}
        else:
            start_date = parsed["start_datetime"]
            end_date = datetime.fromisoformat(start_date) + timedelta(days=1)
            start = {"date": start_date}
            end = {"date": end_date.strftime("%Y-%m-%d")}

        body = {
            "summary": parsed["title"],
            "description": parsed.get("description", ""),
            "start": start,
            "end": end,
        }

        if "color" in parsed:
            body["colorId"] = parsed["color"]

        if parsed.get("is_recurring") and parsed.get("recurrence") == "YEARLY":
            body["recurrence"] = ["RRULE:FREQ=YEARLY"]

        if has_time and parsed.get("event_type") != "task":
            body["reminders"] = {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 1440},
                    {"method": "popup", "minutes": 60},
                    {"method": "popup", "minutes": 15},
                ],
            }

        result = service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=body).execute()
        logger.info(f"Created event: {result.get('id')}")
        return result
    except Exception as e:
        logger.error(f"Failed to create event: {e}")
        return None

def list_upcoming_events(max_results: int = 10) -> list:
    """Get upcoming events"""
    try:
        service = get_google_service()
        if not service:
            return []

        now = datetime.now(timezone.utc).isoformat()
        result = service.events().list(
            calendarId=GOOGLE_CALENDAR_ID,
            timeMin=now,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        return result.get("items", [])
    except Exception as e:
        logger.error(f"Failed to list events: {e}")
        return []

def delete_event(event_id: str) -> bool:
    """Delete event"""
    try:
        service = get_google_service()
        if not service:
            return False
        service.events().delete(calendarId=GOOGLE_CALENDAR_ID, eventId=event_id).execute()
        logger.info(f"Deleted event: {event_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete: {e}")
        return False

# ──────────────────────────────────────────────────────────────────────────────
# NLP - GROK
# ──────────────────────────────────────────────────────────────────────────────

_client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
_category_colors = {}

def get_color_for_category(category: str) -> str:
    """Get consistent color for category"""
    if category not in _category_colors:
        _category_colors[category] = COLORS.get(category, "8")
    return _category_colors[category]

def parse_event(text: str) -> Optional[Dict]:
    """Parse natural language into event"""
    today = datetime.now().strftime("%A, %B %d, %Y")

    system = f"""You are a calendar parser. Today is {today}. Timezone: IST.
Extract event info and return ONLY valid JSON:
{{
  "title": "event title",
  "start_datetime": "ISO 8601 or YYYY-MM-DD",
  "duration_minutes": 60,
  "has_time": true/false,
  "event_type": "event|task|birthday",
  "category": "exam|birthday|meeting|deadline|task|other",
  "is_recurring": false,
  "recurrence": "YEARLY|null",
  "dates": [],
  "description": "details"
}}
Rules:
- If no time: has_time=false, date-only format
- Default durations: exams→180, submissions→5, lectures→60
- Birthday: is_recurring=true, recurrence="YEARLY"
- Error: {{"error": "reason"}}"""

    try:
        resp = _client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            temperature=0,
            max_tokens=512,
        )
        raw = resp.choices[0].message.content.strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        parsed = json.loads(raw)

        if "error" not in parsed:
            parsed["color"] = get_color_for_category(parsed.get("category", "other"))

        return parsed
    except Exception as e:
        logger.error(f"Parse error: {e}")
        return {"error": str(e)}

# ──────────────────────────────────────────────────────────────────────────────
# TELEGRAM RESPONSES
# ──────────────────────────────────────────────────────────────────────────────

def send_message(chat_id: int, text: str, parse_mode: str = "HTML"):
    """Send Telegram message"""
    try:
        import requests
        response = requests.post(
            f"{BASE_URL}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode},
            timeout=5,
        )
        if not response.ok:
            logger.error(f"Telegram send failed: {response.status_code} {response.text}")
    except Exception as e:
        logger.error(f"Failed to send message: {e}")

def handle_start(chat_id: int):
    """Handle /start"""
    send_message(
        chat_id,
        "<b>📅 Telegram Calendar Bot</b>\n\n"
        "Send natural language:\n"
        "• 'ML exam May 5 at 10am'\n"
        "• 'Birthday: Mom May 10'\n"
        "• 'delete exam'\n\n"
        "<b>Commands:</b>\n"
        "/events - List upcoming\n"
        "/help - Help",
    )

def handle_help(chat_id: int):
    """Handle /help"""
    send_message(
        chat_id,
        "<b>📝 How to Use</b>\n\n"
        "<b>Create Events:</b>\n"
        "• 'Team meeting Mon 2pm, 1 hour'\n"
        "• 'Math homework due Friday'\n"
        "• 'Birthday: Mom May 10'\n\n"
        "<b>Delete Events:</b>\n"
        "• 'delete exam'\n"
        "• 'remove all project events'\n\n"
        "<b>Commands:</b>\n"
        "/events - List next 10 events",
    )

def handle_events(chat_id: int):
    """Handle /events"""
    events = list_upcoming_events(10)
    if not events:
        send_message(chat_id, "📭 No upcoming events")
        return

    text = "<b>📅 Upcoming Events:</b>\n\n"
    for i, evt in enumerate(events, 1):
        title = evt.get("summary", "Untitled")
        start = evt.get("start", {})
        dt_str = start.get("dateTime", start.get("date", ""))
        text += f"{i}. <b>{title}</b>\n   {dt_str}\n"

    send_message(chat_id, text)

def handle_message(chat_id: int, text: str):
    """Handle regular message"""
    user_text = text.lower().strip()

    # Check for deletion
    deletion_keywords = ["delete", "remove", "cancel", "drop"]
    if any(user_text.startswith(kw) for kw in deletion_keywords):
        event_query = user_text
        for kw in deletion_keywords:
            if event_query.startswith(kw):
                event_query = event_query[len(kw):].strip()
                break

        events = list_upcoming_events(20)
        if not events:
            send_message(chat_id, "📭 No events found")
            return

        # Search for matches
        search_terms = [t for t in re.split(r'\s+', event_query) if len(t) > 2]
        matching = []
        for evt in events:
            title = evt.get("summary", "").lower()
            for term in search_terms:
                if term in title:
                    matching.append(evt)
                    break

        if not matching:
            send_message(chat_id, f"❌ No events matching '{event_query}'")
            return

        if len(matching) == 1:
            evt = matching[0]
            ok = delete_event(evt["id"])
            send_message(
                chat_id,
                f"✅ Deleted: <b>{evt.get('summary')}</b>" if ok else "❌ Failed"
            )
        else:
            # Delete all
            deleted = sum(1 for e in matching if delete_event(e["id"]))
            send_message(chat_id, f"✅ Deleted {deleted} events")
        return

    # Create event
    send_message(chat_id, "⏳ Parsing...")
    parsed = parse_event(text)

    if not parsed or "error" in parsed:
        send_message(
            chat_id,
            f"❌ Couldn't parse event\n\n"
            f"Try: 'ML exam May 5 at 10am, 3 hours'"
        )
        return

    event = create_calendar_event(parsed)
    if event:
        link = event.get("htmlLink", "")
        has_time = parsed.get("has_time", True)
        event_type = parsed.get("event_type", "event")

        msg = f"✅ <b>{event_type.capitalize()} Created</b>\n\n"
        msg += f"📌 <b>{parsed.get('title')}</b>\n"
        msg += f"📅 {parsed.get('start_datetime')}\n"

        if has_time:
            msg += f"⏱ {parsed.get('duration_minutes')} min\n"

        if parsed.get("is_recurring"):
            msg += f"🔄 Yearly recurring\n"

        send_message(chat_id, msg)
    else:
        send_message(chat_id, "❌ Failed to create event")

def is_authorized(user_id: int) -> bool:
    """Check if user is authorized"""
    return ALLOWED_USER_ID == 0 or user_id == ALLOWED_USER_ID

def _extract_update(event):
    """Normalize API Gateway or direct Lambda payload into a Telegram update."""
    if not isinstance(event, dict):
        return {}

    if "message" in event:
        return event

    body = event.get("body")
    if isinstance(body, dict):
        return body

    if isinstance(body, str) and body.strip():
        if event.get("isBase64Encoded"):
            try:
                body = base64.b64decode(body).decode()
            except Exception:
                pass
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

    return {}

# ──────────────────────────────────────────────────────────────────────────────
# AWS LAMBDA HANDLER
# ──────────────────────────────────────────────────────────────────────────────

def lambda_handler(event, context):
    """AWS Lambda entry point - webhook handler"""
    try:
        update = _extract_update(event)
        message = update.get("message", {})

        if not message:
            logger.info(f"No message in update. Keys={list(update.keys())} event_keys={list(event.keys()) if isinstance(event, dict) else type(event)}")
            return {"statusCode": 200, "body": json.dumps({"ok": True})}

        user_id = message.get("from", {}).get("id", 0)
        chat_id = message.get("chat", {}).get("id", 0)
        text = message.get("text", "").strip()

        if not is_authorized(user_id):
            send_message(chat_id, "❌ Unauthorized")
            return {"statusCode": 200, "body": json.dumps({"ok": True})}

        if not text:
            return {"statusCode": 200, "body": json.dumps({"ok": True})}

        # Handle commands
        if text == "/start":
            handle_start(chat_id)
        elif text == "/help":
            handle_help(chat_id)
        elif text == "/events":
            handle_events(chat_id)
        else:
            handle_message(chat_id, text)

        return {"statusCode": 200, "body": json.dumps({"ok": True})}

    except Exception as e:
        logger.error(f"Handler error: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

# ──────────────────────────────────────────────────────────────────────────────
# LOCAL TESTING
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Local webhook setup (optional)
    print("Telegram Calendar Bot - Lambda Edition")
    print("Deploy to AWS Lambda with API Gateway webhook")
