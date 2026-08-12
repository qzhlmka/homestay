"""Every value you are likely to want to change lives here.

Secrets (Telegram token, chat IDs, feed token) come from the environment so they
never end up in git. Everything else is plain Python you can edit directly.
"""

import os

from dotenv import load_dotenv

# override=True so editing .env actually takes effect. Without it python-dotenv
# leaves any variable already in the environment alone, and uvicorn --reload
# keeps the old value alive - you edit .env, the server restarts, and nothing
# changes. On Railway there is no .env file, so the real env vars still win.
load_dotenv(override=True)


# --------------------------------------------------------------------------
# The property
# --------------------------------------------------------------------------

HOMESTAY_NAME = "Seri Putra Homestay"
ADDRESS = "35, Jalan Megah 10, Taman Megah, 83000 Batu Pahat, Johor"
GOOGLE_MAPS_QUERY = "35 Jalan Megah 10, Taman Megah, 83000 Batu Pahat, Johor"

# Shown on the site and used to build the wa.me links.
PHONE_PRIMARY = "+60 11-1241 2110"
PHONE_SECONDARY = "+60 12-730 4478"
WHATSAPP_NUMBER = "601112412110"      # digits only, country code, no +

INSTAGRAM_URL = os.getenv(
    "INSTAGRAM_URL", "https://www.instagram.com/reel/DLUBPx7ICDl/?hl=en")
FACEBOOK_URL = os.getenv(
    "FACEBOOK_URL", "https://www.facebook.com/watch/?v=24293846236874579")

# What the contact cards actually say. Kept separate from the URLs because a
# post or reel link has no readable handle in it - deriving one gives you
# "@reel" or worse. Set these to your @handle and page name once you have the
# profile links.
INSTAGRAM_LABEL = os.getenv("INSTAGRAM_LABEL", "Watch our reel")
FACEBOOK_LABEL = os.getenv("FACEBOOK_LABEL", "Watch our video")

MAX_GUESTS = 12
CHECK_IN_TIME = "3:00 PM"
CHECK_OUT_TIME = "12:00 PM"
MIN_NIGHTS = 1

# How far ahead guests may book.
BOOKING_WINDOW_DAYS = 365


# --------------------------------------------------------------------------
# Pricing (RM per night, whole house)
# --------------------------------------------------------------------------

BASE_RATE = 250          # Sun - Thu
WEEKEND_RATE = 300       # nights falling on WEEKEND_DAYS
HOLIDAY_RATE = 350       # public holidays and their eves

# Monday=0 ... Sunday=6. Friday and Saturday nights.
WEEKEND_DAYS = {4, 5}

# Treat the night before a public holiday as a holiday night too - that is the
# night people actually travel.
PRICE_HOLIDAY_EVE = True

DEPOSIT_AMOUNT = 100     # RM, collected to confirm a booking
CURRENCY = "RM"


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

# Where booking alerts are delivered. Either a single family group (one
# negative id like -1001234567890) or several personal chats, comma separated.
#   group  -> python get_chat_id.py
#   direct -> message @userinfobot on Telegram
TELEGRAM_CHAT_IDS = [
    c.strip() for c in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if c.strip()
]

# Optional extra lock. Leave empty and anyone in the group above can approve a
# booking, which is usually what you want for a private family group. Set it to
# specific personal user ids to restrict approval to just those people even
# though the whole group can see the request.
TELEGRAM_APPROVER_IDS = [
    c.strip() for c in os.getenv("TELEGRAM_APPROVER_IDS", "").split(",") if c.strip()
]

# Shared secret Telegram echoes back on every webhook call, so nobody else can
# POST fake callbacks at your endpoint.
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")


# --------------------------------------------------------------------------
# Calendar feed
# --------------------------------------------------------------------------

# The .ics URL is unguessable rather than password protected, so this needs to
# be long and random: python -c "import secrets; print(secrets.token_urlsafe(32))"
CALENDAR_TOKEN = os.getenv("CALENDAR_TOKEN", "")

# Public origin of the deployed site, e.g. https://seriputra.up.railway.app
# Used to build absolute links in Telegram messages and the calendar feed.
#
# A bare domain is accepted and assumed to be https. Railway's own
# RAILWAY_PUBLIC_DOMAIN is a bare domain, so pasting it here - or setting
# PUBLIC_BASE_URL=${{RAILWAY_PUBLIC_DOMAIN}} - would otherwise leave the
# Telegram webhook unregistered and the Confirm/Reject buttons dead.
_base = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").strip().rstrip("/")
if _base and "://" not in _base:
    _base = "https://" + _base
PUBLIC_BASE_URL = _base

TIMEZONE = "Asia/Kuala_Lumpur"


# --------------------------------------------------------------------------
# Storage
# --------------------------------------------------------------------------

# On Railway, point this at a mounted volume (e.g. /data/bookings.db) or the
# database is wiped on every redeploy.
DATABASE_PATH = os.getenv("DATABASE_PATH", "bookings.db")

# A pending booking that is never confirmed stops blocking the calendar after
# this many hours, so no-shows do not sit on your dates forever.
PENDING_HOLD_HOURS = 24
