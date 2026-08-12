"""Seri Putra Homestay — booking site backend.

    uvicorn main:app --reload --port 8000

Serves the static site, exposes live availability and pricing, pushes each
booking request to Telegram for manual approval, and publishes the confirmed
stays as a subscribable .ics calendar feed.
"""

import csv
import io
import json
import os
import re
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

import config
import ics_feed
import notify
import pricing
import store

PUBLIC_DIR = Path(__file__).parent / "public"

try:
    from zoneinfo import ZoneInfo
    MY_TZ = ZoneInfo(config.TIMEZONE)
except Exception:                                    # pragma: no cover
    MY_TZ = None


def today_my() -> date:
    """Today in Malaysia, not on whatever timezone the server thinks it is."""
    return datetime.now(MY_TZ).date() if MY_TZ else date.today()


@asynccontextmanager
async def lifespan(app: FastAPI):
    store.init()

    # Say plainly why the Confirm/Reject buttons will or will not work. Getting
    # this wrong is silent otherwise: bookings still arrive, the buttons just
    # never respond, and there is nothing in the logs to explain it.
    if not notify.enabled():
        print("[telegram] DISABLED - set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS")
    elif not config.PUBLIC_BASE_URL.startswith("https://"):
        print("[telegram] WEBHOOK NOT REGISTERED")
        print(f"[telegram]   PUBLIC_BASE_URL is {config.PUBLIC_BASE_URL!r}")
        print("[telegram]   Telegram only delivers to a public https URL, so the")
        print("[telegram]   Confirm/Reject buttons will not respond. Set")
        print("[telegram]   PUBLIC_BASE_URL to your https domain and redeploy.")
    else:
        await notify.set_webhook(config.PUBLIC_BASE_URL)
    yield


app = FastAPI(title=config.HOMESTAY_NAME, lifespan=lifespan)


# --------------------------------------------------------------------------
# Light abuse protection
# --------------------------------------------------------------------------

_submissions = defaultdict(list)
# Deliberately loose. Malaysian mobile carriers put a lot of subscribers behind
# one NAT address, so a tight per-IP limit locks out real guests. The honeypot
# and the fact that you approve every booking by hand do the real work here.
RATE_LIMIT = 12          # booking requests
RATE_WINDOW = 3600       # per hour, per IP


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limited(ip: str) -> bool:
    now = time.time()
    recent = [t for t in _submissions[ip] if now - t < RATE_WINDOW]
    _submissions[ip] = recent
    if len(recent) >= RATE_LIMIT:
        return True
    _submissions[ip].append(now)
    return False


# --------------------------------------------------------------------------
# Request models
# --------------------------------------------------------------------------

class BookingRequest(BaseModel):
    check_in: date
    check_out: date
    guests: int = Field(ge=1, le=config.MAX_GUESTS)

    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=7, max_length=25)
    email: str = Field(default="", max_length=120)
    ic: str = Field(default="", max_length=30)
    city: str = Field(default="", max_length=80)
    purpose: str = Field(default="", max_length=60)
    notes: str = Field(default="", max_length=500)

    # Honeypot: real guests never see this field, bots fill everything in.
    website: str = ""

    @field_validator("phone")
    @classmethod
    def phone_looks_real(cls, v):
        digits = re.sub(r"\D", "", v)
        if not 8 <= len(digits) <= 15:
            raise ValueError("Please enter a valid phone number")
        return v.strip()

    @field_validator("email")
    @classmethod
    def email_looks_real(cls, v):
        v = v.strip()
        if v and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", v):
            raise ValueError("Please enter a valid email address")
        return v

    @field_validator("name", "city", "purpose", "notes", "ic")
    @classmethod
    def tidy(cls, v):
        return " ".join(v.split())


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

@app.get("/api/config")
async def site_config():
    """Everything the front-end needs to render itself."""
    return {
        "name": config.HOMESTAY_NAME,
        "address": config.ADDRESS,
        "maps_query": config.GOOGLE_MAPS_QUERY,
        "phone_primary": config.PHONE_PRIMARY,
        "phone_secondary": config.PHONE_SECONDARY,
        "whatsapp": config.WHATSAPP_NUMBER,
        "instagram": config.INSTAGRAM_URL,
        "instagram_label": config.INSTAGRAM_LABEL,
        "facebook": config.FACEBOOK_URL,
        "facebook_label": config.FACEBOOK_LABEL,
        "currency": config.CURRENCY,
        "base_rate": config.BASE_RATE,
        "weekend_rate": config.WEEKEND_RATE,
        "holiday_rate": config.HOLIDAY_RATE,
        "deposit": config.DEPOSIT_AMOUNT,
        "max_guests": config.MAX_GUESTS,
        "min_nights": config.MIN_NIGHTS,
        "check_in_time": config.CHECK_IN_TIME,
        "check_out_time": config.CHECK_OUT_TIME,
        "booking_window_days": config.BOOKING_WINDOW_DAYS,
        "today": today_my().isoformat(),
    }


@app.get("/api/availability")
async def availability(start: str = "", end: str = ""):
    """Blocked nights and the nightly rate for every date in the window."""
    try:
        first = date.fromisoformat(start) if start else today_my()
        last = (date.fromisoformat(end) if end
                else first + timedelta(days=config.BOOKING_WINDOW_DAYS))
    except ValueError:
        raise HTTPException(400, "Dates must be YYYY-MM-DD")

    if last < first:
        raise HTTPException(400, "end must be after start")
    if (last - first).days > 400:
        last = first + timedelta(days=400)

    return {
        "start": first.isoformat(),
        "end": last.isoformat(),
        "today": today_my().isoformat(),
        "blocked": store.blocked_dates(first, last),
        "rates": pricing.calendar_rates(first, last),
    }


@app.get("/api/quote")
async def quote(check_in: str, check_out: str):
    ci, co = _parse_stay(check_in, check_out)
    return {**pricing.quote(ci, co), "available": store.is_available(ci, co)}


def _parse_stay(check_in: str, check_out: str):
    try:
        ci = date.fromisoformat(check_in)
        co = date.fromisoformat(check_out)
    except ValueError:
        raise HTTPException(400, "Dates must be YYYY-MM-DD")

    today = today_my()
    if ci < today:
        raise HTTPException(400, "Check-in cannot be in the past")
    if co <= ci:
        raise HTTPException(400, "Check-out must be after check-in")
    if (co - ci).days < config.MIN_NIGHTS:
        raise HTTPException(400, f"Minimum stay is {config.MIN_NIGHTS} night(s)")
    if (co - ci).days > 30:
        raise HTTPException(400, "For stays over 30 nights please WhatsApp us directly")
    if (ci - today).days > config.BOOKING_WINDOW_DAYS:
        raise HTTPException(400, "That date is too far ahead — please WhatsApp us")
    return ci, co


@app.post("/api/bookings")
async def create_booking(payload: BookingRequest, request: Request):
    if payload.website:                       # honeypot tripped
        return {"reference": "SP-0000", "status": "pending"}

    ip = client_ip(request)
    if rate_limited(ip):
        raise HTTPException(429, "Too many requests. Please WhatsApp us instead.")

    ci, co = _parse_stay(payload.check_in.isoformat(), payload.check_out.isoformat())
    priced = pricing.quote(ci, co)

    record = {
        "check_in": ci.isoformat(),
        "check_out": co.isoformat(),
        "nights": priced["nights"],
        "guests": payload.guests,
        "total": priced["total"],
        "deposit": priced["deposit"],
        "breakdown": json.dumps(priced["breakdown"]),
        "guest_name": payload.name,
        "guest_phone": payload.phone,
        "guest_email": payload.email,
        "guest_ic": payload.ic,
        "guest_city": payload.city,
        "purpose": payload.purpose,
        "notes": payload.notes,
        "source_ip": ip,
    }

    try:
        booking = store.create_booking(record)
    except store.DatesTaken:
        raise HTTPException(409,
                            "Sorry, those dates were just taken. Please pick another.")

    await notify.send_booking_alert(booking, priced["breakdown"])

    return {
        "reference": booking["reference"],
        "status": "pending",
        "check_in": booking["check_in"],
        "check_out": booking["check_out"],
        "nights": booking["nights"],
        "total": booking["total"],
        "deposit": booking["deposit"],
        "whatsapp_url": _guest_followup_link(booking),
    }


def _guest_followup_link(booking: dict) -> str:
    from urllib.parse import quote as urlquote
    msg = urlquote(
        f"Hi {config.HOMESTAY_NAME}, I just submitted booking "
        f"{booking['reference']} for {booking['check_in']} to "
        f"{booking['check_out']}. Looking forward to hearing from you!"
    )
    return f"https://wa.me/{config.WHATSAPP_NUMBER}?text={msg}"


@app.get("/api/bookings/{reference}")
async def booking_status(reference: str):
    """Lets a guest check their own request without exposing anyone else's."""
    booking = store.get_booking(reference)
    if not booking:
        raise HTTPException(404, "Booking not found")
    return {
        "reference": booking["reference"],
        "status": booking["status"],
        "check_in": booking["check_in"],
        "check_out": booking["check_out"],
        "nights": booking["nights"],
        "total": booking["total"],
        "deposit": booking["deposit"],
    }


# --------------------------------------------------------------------------
# Telegram webhook
# --------------------------------------------------------------------------

async def handle_command(message: dict):
    """Slash commands typed into the family group."""
    text = (message.get("text") or "").strip()
    if not text.startswith("/"):
        return

    chat_id = message.get("chat", {}).get("id")
    if config.TELEGRAM_CHAT_IDS and str(chat_id) not in config.TELEGRAM_CHAT_IDS:
        return                                  # not our group, stay quiet

    # In a group Telegram sends "/cancel@seriputrabot SP-1234".
    parts = text.split()
    command = parts[0].split("@")[0].lower()
    argument = parts[1].upper() if len(parts) > 1 else ""

    if command in ("/help", "/start"):
        await notify.send(chat_id, notify.HELP)
        return

    if command not in ("/cancel", "/status"):
        return

    if not argument:
        await notify.send(
            chat_id,
            f"Which booking? Use <code>{command} SP-XXXX</code> — the "
            f"reference is at the top of the booking message.")
        return

    booking = store.get_booking(argument)
    if not booking:
        await notify.send(chat_id, f"No booking found with reference "
                                   f"<code>{argument}</code>.")
        return

    if command == "/status":
        await notify.send(chat_id, notify.booking_summary(booking))
        return

    # /cancel
    if booking["status"] not in ("pending", "confirmed"):
        await notify.send(
            chat_id,
            notify.booking_summary(booking) +
            f"\n\nAlready {booking['status']} — nothing to cancel.")
        return

    await notify.send(
        chat_id,
        notify.booking_summary(booking) +
        "\n\n⚠️ Cancel this booking? The dates go back on sale immediately.",
        notify.command_cancel_keyboard(booking))


@app.post("/api/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=""),
):
    if config.TELEGRAM_WEBHOOK_SECRET and \
            x_telegram_bot_api_secret_token != config.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(403, "Bad secret token")

    update = await request.json()

    if update.get("message"):
        await handle_command(update["message"])
        return {"ok": True}

    callback = update.get("callback_query")
    if not callback:
        return {"ok": True}

    data = callback.get("data", "")
    if ":" not in data:
        await notify.answer_callback(callback["id"], "")
        return {"ok": True}

    action, booking_id = data.split(":", 1)
    if action not in ("confirm", "reject", "cancel", "cancelyes", "keep"):
        await notify.answer_callback(callback["id"], "")
        return {"ok": True}

    # Authorise on the *chat* the button was pressed in, not the person who
    # pressed it. In a DM those are the same number; in a group they are not —
    # the chat is the group, the sender is a member of it. Checking the chat
    # works for both, and means group membership is what grants approval.
    origin_chat = str(callback.get("message", {}).get("chat", {}).get("id", ""))
    if config.TELEGRAM_CHAT_IDS and origin_chat not in config.TELEGRAM_CHAT_IDS:
        await notify.answer_callback(callback["id"], "Not authorised.", alert=True)
        return {"ok": True}

    # Optional second gate: restrict approval to named people inside that chat.
    sender_id = str(callback.get("from", {}).get("id", ""))
    if config.TELEGRAM_APPROVER_IDS and sender_id not in config.TELEGRAM_APPROVER_IDS:
        await notify.answer_callback(
            callback["id"], "Only the owners can confirm a booking.", alert=True)
        return {"ok": True}

    booking = store.get_booking(booking_id)
    if not booking:
        await notify.answer_callback(callback["id"], "Booking not found.", alert=True)
        return {"ok": True}

    who = callback.get("from", {}).get("first_name", "someone")
    message = callback.get("message", {})
    chat_id = message.get("chat", {}).get("id")
    message_id = message.get("message_id")

    # --- cancelling a booking that was already confirmed -------------------
    if action in ("cancel", "cancelyes", "keep"):
        if action == "cancel":
            # First tap only arms it. Cancelling releases the dates for anyone
            # else to book, so it should not happen on one stray thumb.
            await notify.replace_keyboard(
                chat_id, message_id, notify.confirm_cancel_keyboard(booking))
            await notify.answer_callback(
                callback["id"], "Cancel this booking? Tap again to confirm.")
            return {"ok": True}

        if action == "keep":
            await notify.replace_keyboard(
                chat_id, message_id,
                notify.decision_keyboard(booking, booking["status"]))
            await notify.answer_callback(callback["id"], "Kept.")
            return {"ok": True}

        if not store.cancel_booking(booking_id, who):
            await notify.answer_callback(
                callback["id"],
                f"Cannot cancel - already {booking['status']}.", alert=True)
            return {"ok": True}

        booking["status"] = "cancelled"
        await notify.replace_keyboard(
            chat_id, message_id, notify.decision_keyboard(booking, "cancelled"))
        await notify.answer_callback(callback["id"], "Cancelled - dates released.")
        await notify.broadcast_decision(booking, "cancelled", who)
        return {"ok": True}

    # --- the original confirm / reject decision ----------------------------
    status = "confirmed" if action == "confirm" else "rejected"

    if not store.set_status(booking_id, status, who):
        await notify.answer_callback(
            callback["id"],
            f"Already {booking['status']} — nothing changed.",
            alert=True,
        )
        return {"ok": True}

    booking["status"] = status
    await notify.replace_keyboard(
        chat_id, message_id, notify.decision_keyboard(booking, status))
    await notify.answer_callback(
        callback["id"],
        "Confirmed — now on the calendar." if status == "confirmed"
        else "Rejected — dates released.",
    )
    await notify.broadcast_decision(booking, status, who)
    return {"ok": True}


# --------------------------------------------------------------------------
# Calendar feed
# --------------------------------------------------------------------------

@app.get("/calendar/{token}.ics")
async def calendar_ics(token: str):
    if not config.CALENDAR_TOKEN:
        raise HTTPException(503, "Calendar feed not configured")
    if token != config.CALENDAR_TOKEN:
        raise HTTPException(404, "Not found")

    body = ics_feed.build(store.confirmed_bookings())
    return Response(
        content=body,
        media_type="text/calendar; charset=utf-8",
        headers={
            "Content-Disposition": 'inline; filename="seri-putra-bookings.ics"',
            "Cache-Control": "no-cache, max-age=0",
        },
    )


@app.get("/calendar/{token}/bookings.csv")
async def export_csv(token: str):
    """
    Every booking as a spreadsheet.

    Railway gives no way to browse a volume, so without this the only way to
    read your own bookings is the Railway CLI. Sits behind the same token as
    the calendar feed and carries the same warning: it contains guests' phone
    numbers, emails and IC numbers.
    """
    if not config.CALENDAR_TOKEN:
        raise HTTPException(503, "Export not configured")
    if token != config.CALENDAR_TOKEN:
        raise HTTPException(404, "Not found")

    columns = [
        "reference", "status", "check_in", "check_out", "nights", "guests",
        "total", "deposit", "guest_name", "guest_phone", "guest_email",
        "guest_ic", "guest_city", "purpose", "notes", "created_at",
        "decided_at", "decided_by",
    ]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for booking in store.all_bookings():
        writer.writerow([booking.get(c, "") for c in columns])

    stamp = today_my().isoformat()
    return Response(
        content=buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition":
                f'attachment; filename="seri-putra-bookings-{stamp}.csv"',
            "Cache-Control": "no-store",
        },
    )


@app.get("/health")
async def health():
    https = config.PUBLIC_BASE_URL.startswith("https://")
    db = os.path.abspath(config.DATABASE_PATH)
    return {
        "ok": True,
        "telegram": notify.enabled(),
        "calendar_feed": bool(config.CALENDAR_TOKEN),
        "today": today_my().isoformat(),
        # Deployment diagnostics. Not secret - this is the site's own public
        # address - and without it a misconfigured PUBLIC_BASE_URL is invisible
        # from outside the container.
        "public_base_url": config.PUBLIC_BASE_URL,
        "buttons_can_work": notify.enabled() and https,
        # Is the database actually on the mounted volume, or on the container
        # disk that gets wiped on every redeploy? No way to tell from outside
        # otherwise - Railway gives no file browser for volumes.
        "database_path": db,
        "database_on_volume": db.startswith("/data"),
        "database_exists": os.path.exists(config.DATABASE_PATH),
        "bookings": store.stats(),
    }


# --------------------------------------------------------------------------
# Static site
# --------------------------------------------------------------------------

@app.get("/")
async def index():
    return FileResponse(PUBLIC_DIR / "index.html")


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="static")
