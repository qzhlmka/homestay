"""Every value you are likely to want to change lives here.

Secrets (Telegram token, chat IDs, feed token) come from the environment so they
never end up in git. Everything else is plain Python you can edit directly.
"""

import os

from dotenv import load_dotenv

load_dotenv()


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

INSTAGRAM_URL = os.getenv("INSTAGRAM_URL", "https://instagram.com/seriputrahomestay")
FACEBOOK_URL = os.getenv("FACEBOOK_URL", "https://facebook.com/seriputrahomestay")

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

# Everyone who should receive a new-booking alert. Comma separated numeric ids.
# Get yours by messaging @userinfobot on Telegram.
TELEGRAM_CHAT_IDS = [
    c.strip() for c in os.getenv("TELEGRAM_CHAT_IDS", "").split(",") if c.strip()
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
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")

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
