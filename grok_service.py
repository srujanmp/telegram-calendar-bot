import os
import json
import logging
import random
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# NEW
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
_client = OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")

_IST = "Asia/Kolkata"

# Color mapping: category → Google Calendar colorId (1-11)
COLORS = {
    "birthday": "7",      # cyan
    "exam": "1",          # blue
    "submission": "2",    # sage
    "lecture": "3",       # flamingo
    "meeting": "4",       # tangerine
    "deadline": "5",      # banana
    "task": "6",          # blueberry
    "other": "8",         # graphite
}

def _today() -> str:
    return datetime.now().strftime("%A, %B %d, %Y")


CREATE_SYSTEM = """You are a calendar event parser. Today is {today}. Timezone: IST (Asia/Kolkata, +05:30).

Extract event info from the user message and return ONLY a valid JSON object — no markdown, no explanation.

Schema:
{{
  "title": "concise event title",
  "start_datetime": "ISO 8601 with offset (e.g. 2025-05-05T10:00:00+05:30) OR date-only (e.g. 2025-05-05) for all-day",
  "end_datetime": "ISO 8601 with offset OR date-only (only if different from start, for multi-day events)",
  "duration_minutes": 60,
  "has_time": true/false,
  "is_recurring": false,
  "recurrence": "YEARLY" (only if birthday/anniversary),
  "event_type": "event|task|birthday",
  "category": "birthday|exam|submission|lecture|meeting|deadline|task|other",
  "dates": ["2025-05-05", "2025-05-06"] (if multiple dates specified),
  "description": "optional extra details"
}}

Rules:
- Resolve relative dates ("next Monday", "this Friday") from today.
- If NO TIME specified: has_time=false, start_datetime as date-only (YYYY-MM-DD), return duration_minutes=-1
- If TIME specified: has_time=true, include time in ISO format with +05:30
- Default duration when time given: exams → 180 min, submissions → 5 min, lectures → 60 min, meetings → 60 min
- Multiple dates: list all in "dates" array, use first as start_datetime
- Birthday: set event_type="birthday", is_recurring=true, recurrence="YEARLY"
- Task: simple reminders/todos without specific duration
- Use +05:30 for all datetimes unless user specifies another timezone.
- If you cannot parse a valid event, return: {{"error": "reason"}}
"""

UPDATE_PROMPT = """Today is {today}. Timezone: IST (+05:30).

Current event (raw Google Calendar object):
{current}

User wants to update it: "{instruction}"

Return ONLY valid JSON with the fields that should change.
Only include keys that actually change. Valid keys:
  summary, description,
  start (object with dateTime and timeZone),
  end   (object with dateTime and timeZone)

Example if user says "change time to 3pm":
{{
  "start": {{"dateTime": "2025-05-05T15:00:00+05:30", "timeZone": "Asia/Kolkata"}},
  "end":   {{"dateTime": "2025-05-05T18:00:00+05:30", "timeZone": "Asia/Kolkata"}}
}}

If you cannot parse the instruction, return: {{"error": "reason"}}
"""


# Cache for consistent color assignment across sessions
_category_colors = {}


def get_color_for_category(category: str) -> str:
    """Get consistent color for event category. Randomized on first use per session."""
    if category not in _category_colors:
        # Assign color from predefined mapping, with randomization fallback
        _category_colors[category] = COLORS.get(category, random.choice(list(COLORS.values())))
    return _category_colors[category]


def _call(messages: list, label: str) -> dict | None:
    try:
        resp = _client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0,
            max_tokens=512,
        )
        raw = resp.choices[0].message.content.strip()
        # strip accidental markdown fences
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"[{label}] JSON decode error: {e}")
        return {"error": f"json_parse: {e}"}
    except Exception as e:
        logger.error(f"[{label}] API error: {e}")
        return {"error": str(e)}


class GrokService:
    def parse_event(self, text: str) -> dict | None:
        """Parse a natural-language message into structured event data."""
        system = CREATE_SYSTEM.format(today=_today())
        parsed = _call(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            label="parse_event",
        )

        if parsed and "error" not in parsed:
            # Assign color based on category
            category = parsed.get("category", "other")
            parsed["color"] = get_color_for_category(category)

        return parsed

    def parse_update(self, instruction: str, current_event: dict) -> dict | None:
        """Given an update instruction and the current GCal event, return a patch dict."""
        prompt = UPDATE_PROMPT.format(
            today=_today(),
            current=json.dumps(current_event, indent=2),
            instruction=instruction,
        )
        return _call(
            [{"role": "user", "content": prompt}],
            label="parse_update",
        )
