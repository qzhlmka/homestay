"""Seri Putra Homestay — booking site backend.

    uvicorn main:app --reload --port 8000

Serves the static site, exposes live availability and pricing, pushes each
booking request to Telegram for manual approval, and publishes the confirmed
stays as a subscribable .ics calendar feed.
"""

import json
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
    if notify.enabled() and config.PUBLIC_BASE_URL.startswith("https://"):
        await notify.set_webhook(config.PUBLIC_BASE_URL)
    elif not notify.enabled():
        print("[telegram] disabled — set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS")
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
        "facebook": config.FACEBOOK_URL,
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

@app.post("/api/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str = Header(default=""),
):
    if config.TELEGRAM_WEBHOOK_SECRET and \
            x_telegram_bot_api_secret_token != config.TELEGRAM_WEBHOOK_SECRET:
        raise HTTPException(403, "Bad secret token")

    update = await request.json()
    callback = update.get("callback_query")
    if not callback:
        return {"ok": True}

    data = callback.get("data", "")
    if ":" not in data:
        await notify.answer_callback(callback["id"], "")
        return {"ok": True}

    action, booking_id = data.split(":", 1)
    if action not in ("confirm", "reject"):
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
    status = "confirmed" if action == "confirm" else "rejected"

    if not store.set_status(booking_id, status, who):
        await notify.answer_callback(
            callback["id"],
            f"Already {booking['status']} — nothing changed.",
            alert=True,
        )
        return {"ok": True}

    booking["status"] = status
    message = callback.get("message", {})
    await notify.strike_through_buttons(
        message.get("chat", {}).get("id"), message.get("message_id"), status)
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


@app.get("/health")
async def health():
    return {
        "ok": True,
        "telegram": notify.enabled(),
        "calendar_feed": bool(config.CALENDAR_TOKEN),
        "today": today_my().isoformat(),
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
