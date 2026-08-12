"""Nightly rate calculation.

A "night" is identified by its check-in date: booking 20 Mar -> 22 Mar is two
nights, the night of the 20th and the night of the 21st. The 22nd is checkout
and is never charged.
"""

import json
import os
from dataclasses import dataclass
from datetime import date, timedelta

import config

_HOLIDAYS_FILE = os.path.join(os.path.dirname(__file__), "holidays.json")


def _load_holidays():
    with open(_HOLIDAYS_FILE, encoding="utf-8") as fh:
        raw = json.load(fh)
    return {
        date.fromisoformat(h["date"]): h["name"]
        for h in raw["holidays"]
    }


HOLIDAYS = _load_holidays()


@dataclass
class Night:
    date: date
    rate: int
    kind: str          # "base" | "weekend" | "holiday"
    label: str = ""    # holiday name, when there is one


def rate_for(day: date) -> Night:
    """Rate for the night beginning on `day`."""
    if day in HOLIDAYS:
        return Night(day, config.HOLIDAY_RATE, "holiday", HOLIDAYS[day])

    tomorrow = day + timedelta(days=1)
    if config.PRICE_HOLIDAY_EVE and tomorrow in HOLIDAYS:
        return Night(day, config.HOLIDAY_RATE, "holiday",
                     "Eve of " + HOLIDAYS[tomorrow])

    if day.weekday() in config.WEEKEND_DAYS:
        return Night(day, config.WEEKEND_RATE, "weekend")

    return Night(day, config.BASE_RATE, "base")


def nights_between(check_in: date, check_out: date):
    """Every chargeable night in a stay."""
    return [rate_for(check_in + timedelta(days=i))
            for i in range((check_out - check_in).days)]


def quote(check_in: date, check_out: date) -> dict:
    """Full price breakdown for a stay."""
    nights = nights_between(check_in, check_out)
    total = sum(n.rate for n in nights)
    return {
        "check_in": check_in.isoformat(),
        "check_out": check_out.isoformat(),
        "nights": len(nights),
        "total": total,
        "deposit": config.DEPOSIT_AMOUNT,
        "balance": total - config.DEPOSIT_AMOUNT,
        "breakdown": [
            {
                "date": n.date.isoformat(),
                "rate": n.rate,
                "kind": n.kind,
                "label": n.label,
            }
            for n in nights
        ],
    }


def calendar_rates(start: date, end: date) -> dict:
    """Per-date rate map the front-end calendar renders."""
    out = {}
    day = start
    while day <= end:
        n = rate_for(day)
        out[day.isoformat()] = {"rate": n.rate, "kind": n.kind, "label": n.label}
        day += timedelta(days=1)
    return out
