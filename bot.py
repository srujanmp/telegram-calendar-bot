import os
import ssl
import logging
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes, ConversationHandler,
)
from telegram.request import HTTPXRequest
from dotenv import load_dotenv
from calendar_service import CalendarService
from grok_service import GrokService

load_dotenv()
logging.basicConfig(
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
ALLOWED_USER_ID = int(os.environ.get("ALLOWED_USER_ID", 0))

calendar_svc = CalendarService()
grok_svc = GrokService()

# ConversationHandler states
SELECT_DELETE = 1
SELECT_UPDATE = 2
ENTER_UPDATE = 3


# ─── Helpers ──────────────────────────────────────────────────────────────────

def format_dt(dt_str: str) -> str:
    if not dt_str:
        return "Unknown"
    try:
        if "T" in str(dt_str):
            dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
            return dt.strftime("%b %d, %Y  %I:%M %p")
        return dt_str
    except Exception:
        return str(dt_str)


def is_authorized(update: Update) -> bool:
    if ALLOWED_USER_ID == 0:
        return True
    return update.effective_user.id == ALLOWED_USER_ID


def build_events_keyboard(events: list, prefix: str) -> InlineKeyboardMarkup:
    keyboard = []
    for e in events:
        start = e["start"].get("dateTime", e["start"].get("date", ""))
        label = f"{e.get('summary', 'Untitled')}  ·  {format_dt(start)}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"{prefix}{e['id']}")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
    return InlineKeyboardMarkup(keyboard)


# ─── Commands ─────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📅 *CalBot* — smart calendar via Telegram\n\n"
        "Just send a plain message:\n"
        "• _ML exam on May 5 at 10am_\n"
        "• _DSA submission this Friday 11:59pm_\n"
        "• _Physics lab next Monday 2pm, 2 hours_\n\n"
        "*Commands*\n"
        "/events — list upcoming events\n"
        "/delete — delete an event\n"
        "/update — update an event\n"
        "/help — show this message",
        parse_mode="Markdown",
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def list_events(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return
    events = calendar_svc.list_upcoming(max_results=10)
    if not events:
        await update.message.reply_text("No upcoming events found.")
        return

    lines = ["📅 *Upcoming Events*\n"]
    for i, e in enumerate(events, 1):
        start = e["start"].get("dateTime", e["start"].get("date", ""))
        desc = e.get("description", "")
        desc_line = f"\n   📝 _{desc[:60]}{'…' if len(desc) > 60 else ''}_" if desc else ""
        lines.append(f"{i}. *{e.get('summary', 'Untitled')}*\n   🕐 {format_dt(start)}{desc_line}\n")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ─── Delete flow ──────────────────────────────────────────────────────────────

async def delete_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    events = calendar_svc.list_upcoming(max_results=10)
    if not events:
        await update.message.reply_text("No upcoming events to delete.")
        return ConversationHandler.END

    await update.message.reply_text(
        "Select the event to delete:",
        reply_markup=build_events_keyboard(events, "del_"),
    )
    return SELECT_DELETE


async def delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    event_id = query.data[4:]  # strip "del_"
    ok = calendar_svc.delete_event(event_id)
    await query.edit_message_text("✅ Event deleted." if ok else "❌ Failed to delete event.")
    return ConversationHandler.END


# ─── Update flow ──────────────────────────────────────────────────────────────

async def update_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        return ConversationHandler.END
    events = calendar_svc.list_upcoming(max_results=10)
    if not events:
        await update.message.reply_text("No upcoming events to update.")
        return ConversationHandler.END

    await update.message.reply_text(
        "Select the event to update:",
        reply_markup=build_events_keyboard(events, "upd_"),
    )
    return SELECT_UPDATE


async def update_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel":
        await query.edit_message_text("Cancelled.")
        return ConversationHandler.END

    context.user_data["update_event_id"] = query.data[4:]  # strip "upd_"
    await query.edit_message_text(
        "Describe the update:\n"
        "• _Change time to 3pm_\n"
        "• _Rename to DSA Final Exam_\n"
        "• _Change date to May 10, extend to 3 hours_",
        parse_mode="Markdown",
    )
    return ENTER_UPDATE


async def update_details_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    event_id = context.user_data.get("update_event_id")
    if not event_id:
        await update.message.reply_text("Session expired. Try /update again.")
        return ConversationHandler.END

    current = calendar_svc.get_event(event_id)
    if not current:
        await update.message.reply_text("Event not found.")
        return ConversationHandler.END

    patch = grok_svc.parse_update(update.message.text, current)
    if not patch or "error" in patch:
        await update.message.reply_text("❌ Couldn't parse update. Try again with /update.")
        return ConversationHandler.END

    ok = calendar_svc.update_event(event_id, patch)
    await update.message.reply_text("✅ Event updated!" if ok else "❌ Failed to update event.")
    return ConversationHandler.END


# ─── Plain message handler (create event) ─────────────────────────────────────

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("Unauthorized.")
        return

    user_text = update.message.text.lower().strip()

    # Check for deletion intents (natural language deletion)
    deletion_keywords = ["delete", "remove", "cancel", "drop"]
    if any(user_text.startswith(kw) for kw in deletion_keywords):
        # Extract the event name/description to delete
        event_query = user_text
        for kw in deletion_keywords:
            if event_query.startswith(kw):
                event_query = event_query[len(kw):].strip()
                break

        # Get upcoming events to search for matches
        events = calendar_svc.list_upcoming(max_results=20)

        if not events:
            await update.message.reply_text("📭 No upcoming events found.")
            return

        # Extract search terms from query (split by common words)
        import re
        search_terms = re.split(r'\s+', event_query)
        search_terms = [t for t in search_terms if len(t) > 2]  # Filter out short words

        # Check if user wants ALL matching events
        show_all = "all" in event_query

        # Find events matching the query (flexible matching)
        matching_events = []
        for evt in events:
            evt_title = evt.get("summary", "").lower()
            # Match if any search term appears in event title
            if search_terms:
                for term in search_terms:
                    if term in evt_title:
                        matching_events.append(evt)
                        break
            else:
                # No search terms (e.g., "delete all") - return all events
                matching_events = events
                break

        if not matching_events:
            await update.message.reply_text(
                f"❌ No events matching *'{event_query}'* found.\n\n"
                "Use `/delete` to see all upcoming events or try a different search term.",
                parse_mode="Markdown",
            )
            return

        if len(matching_events) == 1 or (len(matching_events) > 1 and not show_all):
            if len(matching_events) == 1:
                # Only one match, delete it directly
                evt = matching_events[0]
                ok = calendar_svc.delete_event(evt["id"])
                if ok:
                    await update.message.reply_text(
                        f"✅ Deleted: *{evt.get('summary')}*",
                        parse_mode="Markdown",
                    )
                else:
                    await update.message.reply_text("❌ Failed to delete event.")
                return
            else:
                # Multiple matches - show buttons to choose which to delete
                buttons = []
                for evt in matching_events[:5]:  # Max 5 options
                    buttons.append(
                        [InlineKeyboardButton(
                            evt.get("summary", "Untitled")[:30],
                            callback_data=f"del_{evt['id']}"
                        )]
                    )

                await update.message.reply_text(
                    f"Found {len(matching_events)} matching events. Which one(s)?\n",
                    reply_markup=InlineKeyboardMarkup(buttons),
                )
                return

        # Multiple matches + "all" flag = delete all matching events
        if len(matching_events) > 1 and show_all:
            deleted_count = 0
            deleted_names = []
            for evt in matching_events:
                if calendar_svc.delete_event(evt["id"]):
                    deleted_count += 1
                    deleted_names.append(evt.get("summary", "Untitled"))

            if deleted_count > 0:
                await update.message.reply_text(
                    f"✅ Deleted {deleted_count} events:\n" + "\n".join([f"• {name}" for name in deleted_names]),
                    parse_mode="Markdown",
                )
            else:
                await update.message.reply_text("❌ Failed to delete events.")
            return

        return

    msg = await update.message.reply_text("⏳ Parsing…")
    parsed = grok_svc.parse_event(update.message.text)

    if not parsed or "error" in parsed:
        reason = parsed.get("error", "unknown") if parsed else "unknown"
        await msg.edit_text(
            f"❌ Couldn't extract event details.\n_Reason: {reason}_\n\n"
            "Try being more specific, e.g.:\n"
            "_'ML exam on May 5 at 10am, 3 hours'_\n"
            "_'Birthday: Mom's birthday May 10'_\n"
            "_'Math homework due Friday'_",
            parse_mode="Markdown",
        )
        return

    event = calendar_svc.create_event(parsed)
    if event:
        link = event.get("htmlLink", "")

        # Format event details based on type
        has_time = parsed.get("has_time", True)
        event_type = parsed.get("event_type", "event")
        is_recurring = parsed.get("is_recurring", False)
        dates_list = parsed.get("dates", [])
        duration = parsed.get("duration_minutes", 60)

        # Build details string
        details = f"📌 *{parsed.get('title')}*\n"

        if is_recurring:
            details += f"🔄 _Recurring Yearly_\n"

        if dates_list and len(dates_list) > 1:
            details += f"📅 _Multiple dates: {', '.join(dates_list)}_\n"
        else:
            details += f"📅 {format_dt(parsed.get('start_datetime', ''))}\n"

        if has_time and duration > 0:
            details += f"⏱ {duration} min\n"
        elif not has_time:
            details += f"📍 All-day\n"

        if event_type == "birthday":
            details += f"🎂 Birthday\n"
        elif event_type == "task":
            details += f"✓ Task\n"

        if parsed.get("description"):
            details += f"__{parsed.get('description')}__\n"

        await msg.edit_text(
            f"✅ *{event_type.capitalize()} Created*\n\n{details}\n[Open in Google Calendar]({link})",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    else:
        await msg.edit_text("❌ Failed to create calendar event.")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    # SSL verification: disable for development/college networks, enable for production
    environment = os.environ.get("ENVIRONMENT", "development")

    if environment == "production":
        # Production (Railway): normal SSL verification
        request = HTTPXRequest(http_version="1.1")
    else:
        # Development: disable SSL verification for networks with SSL inspection
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        request = HTTPXRequest(http_version="1.1", httpx_kwargs={"verify": False})

    app = Application.builder().token(TELEGRAM_TOKEN).request(request).build()

    delete_conv = ConversationHandler(
        entry_points=[CommandHandler("delete", delete_cmd)],
        states={SELECT_DELETE: [CallbackQueryHandler(delete_callback)]},
        fallbacks=[],
    )

    update_conv = ConversationHandler(
        entry_points=[CommandHandler("update", update_cmd)],
        states={
            SELECT_UPDATE: [CallbackQueryHandler(update_select_callback)],
            ENTER_UPDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, update_details_handler)],
        },
        fallbacks=[],
    )

    # Global callback handler for natural language deletion
    async def nl_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        if query.data.startswith("del_"):
            event_id = query.data[4:]
            ok = calendar_svc.delete_event(event_id)
            await query.edit_message_text("✅ Event deleted." if ok else "❌ Failed to delete event.")

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("events", list_events))
    app.add_handler(delete_conv)
    app.add_handler(update_conv)
    app.add_handler(CallbackQueryHandler(nl_delete_callback, pattern="^del_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    import asyncio
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()