"""Telegram notifications and the Confirm/Reject callback handling."""

import html
import re
from datetime import date, datetime
from urllib.parse import quote

import httpx

import config

API = "https://api.telegram.org/bot{token}/{method}"

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def enabled() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_IDS)


async def _call(method: str, payload: dict):
    if not config.TELEGRAM_BOT_TOKEN:
        return None
    url = API.format(token=config.TELEGRAM_BOT_TOKEN, method=method)
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, json=payload)
    if resp.status_code >= 400:
        # Never let a Telegram outage lose a booking - it is already in SQLite.
        print(f"[telegram] {method} failed {resp.status_code}: {resp.text}")
        return None
    return resp.json()


# --------------------------------------------------------------------------
# Formatting
# --------------------------------------------------------------------------

def wa_number(raw: str) -> str:
    """Malaysian local format -> wa.me digits. 011-1241 2110 -> 601112412110."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("60"):
        return digits
    if digits.startswith("0"):
        return "60" + digits[1:]
    return digits


def pretty_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{DAY_NAMES[d.weekday()]} {d.day} {d.strftime('%b %Y')}"


def _e(value) -> str:
    return html.escape(str(value or ""), quote=False)


def booking_message(b: dict, breakdown: list) -> str:
    """The alert you actually read on your phone. Everything, in reading order."""
    cur = config.CURRENCY
    lines = [
        f"<b>🏡 NEW BOOKING REQUEST</b>  <code>{_e(b['reference'])}</code>",
        "",
        "<b>━━ STAY ━━</b>",
        f"📅 Check-in:  <b>{_e(pretty_date(b['check_in']))}</b>  ({config.CHECK_IN_TIME})",
        f"📅 Check-out: <b>{_e(pretty_date(b['check_out']))}</b>  ({config.CHECK_OUT_TIME})",
        f"🌙 {b['nights']} night(s)   👥 {b['guests']} guest(s)",
        "",
        "<b>━━ GUEST ━━</b>",
        f"👤 <b>{_e(b['guest_name'])}</b>",
        f"📱 <a href=\"tel:{_e(b['guest_phone'])}\">{_e(b['guest_phone'])}</a>",
    ]

    if b.get("guest_email"):
        lines.append(f"✉️ <a href=\"mailto:{_e(b['guest_email'])}\">{_e(b['guest_email'])}</a>")
    if b.get("guest_ic"):
        lines.append(f"🪪 IC / Passport: <code>{_e(b['guest_ic'])}</code>")
    if b.get("guest_city"):
        lines.append(f"📍 Coming from: {_e(b['guest_city'])}")
    if b.get("purpose"):
        lines.append(f"🎯 Purpose: {_e(b['purpose'])}")
    if b.get("notes"):
        lines.append(f"💬 Notes: <i>{_e(b['notes'])}</i>")

    lines += ["", "<b>━━ PRICE ━━</b>"]
    for night in breakdown:
        tag = ""
        if night["kind"] == "holiday":
            tag = f"  🎉 {night['label']}" if night["label"] else "  🎉 holiday"
        elif night["kind"] == "weekend":
            tag = "  ⭐ weekend"
        lines.append(
            f"  {_e(pretty_date(night['date']))}  —  {cur}{night['rate']}{_e(tag)}"
        )

    lines += [
        "",
        f"💰 <b>TOTAL: {cur}{b['total']}</b>",
        f"🔒 Deposit to collect: <b>{cur}{b['deposit']}</b>",
        f"⏳ Balance on arrival: {cur}{b['total'] - b['deposit']}",
        "",
        f"🕐 Requested {_e(submitted_at(b['created_at']))}",
        f"⏱ Dates held for {config.PENDING_HOLD_HOURS}h — decide before then.",
    ]
    return "\n".join(lines)


def submitted_at(iso: str) -> str:
    """UTC timestamp -> readable Malaysia time."""
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return iso
    try:
        from zoneinfo import ZoneInfo
        dt = dt.astimezone(ZoneInfo(config.TIMEZONE))
    except Exception:
        pass
    return dt.strftime("%d %b %Y, %I:%M %p")


def booking_keyboard(b: dict) -> dict:
    wa = wa_number(b["guest_phone"])
    greeting = quote(
        f"Assalamualaikum {b['guest_name']}, this is {config.HOMESTAY_NAME}. "
        f"We received your booking {b['reference']} for "
        f"{pretty_date(b['check_in'])} to {pretty_date(b['check_out'])}. "
        f"To confirm, kindly pay the {config.CURRENCY}{b['deposit']} deposit. "
        f"Thank you!"
    )
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Confirm", "callback_data": f"confirm:{b['id']}"},
                {"text": "❌ Reject", "callback_data": f"reject:{b['id']}"},
            ],
            [
                {"text": "💬 WhatsApp guest", "url": f"https://wa.me/{wa}?text={greeting}"},
                {"text": "📞 Call", "url": f"tel:{wa_number(b['guest_phone'])}"},
            ],
        ]
    }


# --------------------------------------------------------------------------
# Sending
# --------------------------------------------------------------------------

async def send_booking_alert(b: dict, breakdown: list):
    """Fan the request out to everyone in TELEGRAM_CHAT_IDS."""
    text = booking_message(b, breakdown)
    keyboard = booking_keyboard(b)
    for chat_id in config.TELEGRAM_CHAT_IDS:
        await _call("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
            "disable_web_page_preview": True,
        })


async def broadcast_decision(b: dict, status: str, decided_by: str):
    """Tell the other family members what was decided, so nobody double-handles."""
    icon = "✅ CONFIRMED" if status == "confirmed" else "❌ REJECTED"
    text = (
        f"<b>{icon}</b>  <code>{_e(b['reference'])}</code>\n"
        f"{_e(b['guest_name'])} · {_e(pretty_date(b['check_in']))} → "
        f"{_e(pretty_date(b['check_out']))}\n"
        f"Handled by {_e(decided_by)}"
    )
    if status == "confirmed":
        text += (
            f"\n\n📆 Now on the shared calendar."
            f"\n💰 Collect {config.CURRENCY}{b['deposit']} deposit from "
            f"{_e(b['guest_phone'])}"
        )
    for chat_id in config.TELEGRAM_CHAT_IDS:
        await _call("sendMessage", {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        })


async def answer_callback(callback_id: str, text: str, alert: bool = False):
    await _call("answerCallbackQuery", {
        "callback_query_id": callback_id,
        "text": text,
        "show_alert": alert,
    })


async def strike_through_buttons(chat_id, message_id, status: str):
    """Replace the Confirm/Reject row once a decision is made."""
    label = "✅ Confirmed" if status == "confirmed" else "❌ Rejected"
    await _call("editMessageReplyMarkup", {
        "chat_id": chat_id,
        "message_id": message_id,
        "reply_markup": {"inline_keyboard": [[{"text": label,
                                               "callback_data": "noop"}]]},
    })


async def set_webhook(base_url: str):
    """Point Telegram at us. Called once on startup."""
    if not config.TELEGRAM_BOT_TOKEN:
        return
    payload = {
        "url": f"{base_url}/api/telegram/webhook",
        "allowed_updates": ["callback_query", "message"],
    }
    if config.TELEGRAM_WEBHOOK_SECRET:
        payload["secret_token"] = config.TELEGRAM_WEBHOOK_SECRET
    result = await _call("setWebhook", payload)
    if result and result.get("ok"):
        print(f"[telegram] webhook -> {payload['url']}")
