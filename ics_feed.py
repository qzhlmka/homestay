"""Builds the subscribable .ics feed.

One all-day event per booking. Apple Calendar and Google Calendar both poll a
webcal/https URL on their own schedule, so all three of you subscribe once and
never touch it again.
"""

from datetime import date, datetime, timedelta, timezone

import config
import notify

PRODID = "-//Seri Putra Homestay//Booking Calendar//EN"


def _escape(text: str) -> str:
    """RFC 5545 text escaping."""
    return (str(text or "")
            .replace("\\", "\\\\")
            .replace(";", "\\;")
            .replace(",", "\\,")
            .replace("\r\n", "\\n")
            .replace("\n", "\\n"))


def _fold(line: str) -> str:
    """RFC 5545 caps content lines at 75 octets; continuations start with a space."""
    encoded = line.encode("utf-8")
    if len(encoded) <= 73:
        return line

    chunks, current = [], b""
    for char in line:
        raw = char.encode("utf-8")
        limit = 73 if not chunks else 72
        if len(current) + len(raw) > limit:
            chunks.append(current)
            current = b""
        current += raw
    chunks.append(current)
    return "\r\n ".join(c.decode("utf-8") for c in chunks)


def _stamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _event(booking: dict) -> list:
    ref = booking["reference"]
    name = booking["guest_name"]
    pending = booking["status"] == "pending"

    summary = "%s%s · %s pax · %s" % (
        "⏳ HOLD — " if pending else "🏡 ",
        name,
        booking["guests"],
        ref,
    )

    wa = notify.wa_number(booking["guest_phone"])
    description = "\n".join(filter(None, [
        f"Reference: {ref}",
        f"Status: {'AWAITING YOUR CONFIRMATION' if pending else 'Confirmed'}",
        "",
        f"Guest: {name}",
        f"Phone: {booking['guest_phone']}",
        f"WhatsApp: https://wa.me/{wa}",
        f"Email: {booking['guest_email']}" if booking.get("guest_email") else "",
        f"IC / Passport: {booking['guest_ic']}" if booking.get("guest_ic") else "",
        f"Coming from: {booking['guest_city']}" if booking.get("guest_city") else "",
        f"Purpose: {booking['purpose']}" if booking.get("purpose") else "",
        f"Notes: {booking['notes']}" if booking.get("notes") else "",
        "",
        f"{booking['nights']} night(s) · {booking['guests']} guest(s)",
        f"Total: {config.CURRENCY}{booking['total']}",
        f"Deposit: {config.CURRENCY}{booking['deposit']}",
        f"Balance on arrival: {config.CURRENCY}{booking['total'] - booking['deposit']}",
        "",
        f"Check-in {config.CHECK_IN_TIME} · Check-out {config.CHECK_OUT_TIME}",
    ]))

    created = datetime.fromisoformat(booking["created_at"])

    return [
        "BEGIN:VEVENT",
        f"UID:{booking['id']}@seriputra",
        f"DTSTAMP:{_stamp(datetime.now(timezone.utc))}",
        f"DTSTART;VALUE=DATE:{booking['check_in'].replace('-', '')}",
        # DTEND is exclusive for all-day events: checkout day stays free.
        f"DTEND;VALUE=DATE:{booking['check_out'].replace('-', '')}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
        f"LOCATION:{_escape(config.ADDRESS)}",
        f"URL:{config.PUBLIC_BASE_URL}",
        f"STATUS:{'TENTATIVE' if pending else 'CONFIRMED'}",
        f"CREATED:{_stamp(created)}",
        "TRANSP:OPAQUE",
        "END:VEVENT",
    ]


def build(bookings: list) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(config.HOMESTAY_NAME + ' — Bookings')}",
        f"X-WR-CALDESC:{_escape('Confirmed stays at ' + config.ADDRESS)}",
        f"X-WR-TIMEZONE:{config.TIMEZONE}",
        # Ask Apple/Google to re-poll hourly instead of their lazy default.
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]

    for booking in bookings:
        lines.extend(_event(booking))

    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
