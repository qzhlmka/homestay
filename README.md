# Seri Putra Homestay

Booking website for 35, Jalan Megah 10, Taman Megah, 83000 Batu Pahat, Johor.

A guest picks dates on a live calendar, submits a request, and the booking lands
on your Telegram with Confirm / Reject buttons. Confirm it and the stay appears
on the shared calendar that you, your dad and your mom subscribe to.

---

## Run it locally

```bash
pip install -r requirements.txt
```

```bash
uvicorn main:app --reload --port 8000
```

Then open <http://localhost:8000>. It works without any setup — you just won't
get Telegram alerts until you do the step below.

---

## One-time setup

Copy `.env.example` to `.env` and fill in four things.

### 1. Create the Telegram bot

Open Telegram, message **@BotFather**, send `/newbot`, and follow the prompts.
He replies with a token like `8123456789:AAH...`.

```
TELEGRAM_BOT_TOKEN=8123456789:AAH...
```

### 2. Get the three chat IDs

You, your dad and your mom each message **@userinfobot**. It replies with a
numeric Id. Put all three in, comma separated:

```
TELEGRAM_CHAT_IDS=123456789,987654321,555444333
```

**Each of you must also send `/start` to your new bot once.** Telegram refuses
to deliver messages to anyone who has never started a conversation with it. This
is the single most common reason alerts don't arrive.

### 3. Generate two secrets

```bash
python -c "import secrets; print('TELEGRAM_WEBHOOK_SECRET=' + secrets.token_urlsafe(32)); print('CALENDAR_TOKEN=' + secrets.token_urlsafe(32))"
```

Paste both into `.env`.

### 4. Set your public URL

Once deployed, set this to the real https origin. The Telegram webhook will not
register without it — Telegram refuses plain http.

```
PUBLIC_BASE_URL=https://seriputra.up.railway.app
```

---

## Deploying to Railway

Same as bizbot. Push the repo, then in the Railway dashboard:

1. **Add a volume** mounted at `/data`, and set `DATABASE_PATH=/data/bookings.db`.
   Skip this and every redeploy erases bookings you have already confirmed.
2. Add all the `.env` variables as Railway environment variables.
3. Set `PUBLIC_BASE_URL` to the domain Railway gives you.

`railway.toml` already handles the start command.

The Telegram webhook registers itself on startup, so once `PUBLIC_BASE_URL` is
an https address the Confirm/Reject buttons start working with no further steps.

---

## Subscribing to the calendar

Your feed lives at:

```
https://YOUR-DOMAIN/calendar/YOUR_CALENDAR_TOKEN.ics
```

It is protected by being unguessable, so treat that URL like a password — anyone
who has it can read your guests' phone numbers.

**Apple Calendar (iPhone)**
Settings → Calendar → Accounts → Add Account → Other → Add Subscribed Calendar →
paste the URL.

**Apple Calendar (Mac)**
File → New Calendar Subscription → paste the URL → set *Auto-refresh* to
**Every hour** (the default is once a week, which is useless here).

**Google Calendar** (desktop only — the Android app can't add subscriptions)
Other calendars → **+** → From URL → paste the URL.

Send the same URL to your dad and your mom and they each do the same. Everyone
sees the same bookings.

> Google refreshes external calendars on its own schedule and can lag by several
> hours — sometimes up to a day. Telegram is your real-time alert; the calendar
> is the shared record. Don't rely on Google Calendar to tell you about a booking
> that came in an hour ago.

Pending requests show as **⏳ HOLD** and tentative. They turn into confirmed
entries once you tap Confirm.

---

## How a booking flows

1. Guest picks dates and submits. Their nights are held immediately, so nobody
   else can request the same dates.
2. All three of you get a Telegram message with the guest's full details, the
   per-night price breakdown, and four buttons: **Confirm**, **Reject**,
   **WhatsApp guest**, **Call**.
3. Whoever taps first wins — the other two get a message saying who handled it.
   A second tap is rejected rather than silently double-applied.
4. **Confirm** → the stay goes on the shared calendar, and you collect the
   deposit over WhatsApp.
   **Reject** → the dates are released back to the calendar straight away.
5. If nobody responds within 24 hours the hold expires by itself and the dates
   reopen. Change this with `PENDING_HOLD_HOURS` in `config.py`.

Nothing is auto-confirmed. No payment is taken online — the deposit is arranged
by you personally over WhatsApp.

---

## Changing things

| What | Where |
|---|---|
| Prices, deposit, check-in times, max guests | `config.py` |
| Which dates count as holidays | `holidays.json` |
| Phone numbers, Instagram, Facebook | `config.py` / `.env` |
| Photos and captions | `public/images/` + the `PHOTOS` list in `public/app.js` |
| Wording, layout | `public/index.html`, `public/styles.css` |

### Adding a photo

Drop the image in `public/images/full/` (and a smaller copy in
`public/images/thumb/`), then add one line to the `PHOTOS` array at the top of
`public/app.js`. Categories are `living`, `bedrooms`, `bathrooms`.

### Blocking dates yourself

For maintenance or family staying over:

```bash
python -c "import store, datetime as dt; store.init(); store.add_blackout(dt.date(2026,12,24), dt.date(2026,12,27), 'Family'); print('blocked')"
```

The end date is exclusive, so that example blocks the nights of 24, 25 and 26 Dec.

### Public holidays

`holidays.json` covers 2026 and 2027. Rows marked `"verified": false` are
lunar-calendar or moon-sighting dependent and are estimates. When Johor gazettes
its official list for the year, check those rows and correct them — a wrong date
here means charging RM250 on a night you could have charged RM350.

---

## Layout

```
main.py          FastAPI app, all HTTP endpoints
config.py        every tunable setting
pricing.py       nightly rate calculation
store.py         SQLite persistence
notify.py        Telegram messages and Confirm/Reject handling
ics_feed.py      builds the .ics calendar feed
holidays.json    Johor public holidays
public/          the website (plain HTML/CSS/JS, no build step)
```
