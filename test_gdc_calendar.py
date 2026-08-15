"""Tests gdc_calendar.py — repères temporels de GDC (pas de dépendance réseau/Streamlit)."""

from __future__ import annotations

from datetime import datetime

import gdc_calendar as cal

# --- expected_decks_now() --- (2026-08-17 = lundi, 08-20 = jeudi, 08-21 = vendredi,
# 08-22 = samedi, 08-23 = dimanche, 08-18/19 = mardi/mercredi)
assert cal.expected_decks_now(datetime(2026, 8, 17, 10, 0, tzinfo=cal.BRUSSELS_TZ)) == 16, "lundi"
assert cal.expected_decks_now(datetime(2026, 8, 18, 10, 0, tzinfo=cal.BRUSSELS_TZ)) is None, "mardi"
assert cal.expected_decks_now(datetime(2026, 8, 19, 10, 0, tzinfo=cal.BRUSSELS_TZ)) is None, "mercredi"
assert cal.expected_decks_now(datetime(2026, 8, 20, 10, 0, tzinfo=cal.BRUSSELS_TZ)) is None, "jeudi (comme le bot : pas de rapport ce jour-là)"
assert cal.expected_decks_now(datetime(2026, 8, 21, 10, 0, tzinfo=cal.BRUSSELS_TZ)) == 4, "vendredi"
assert cal.expected_decks_now(datetime(2026, 8, 22, 10, 0, tzinfo=cal.BRUSSELS_TZ)) == 8, "samedi"
assert cal.expected_decks_now(datetime(2026, 8, 23, 10, 0, tzinfo=cal.BRUSSELS_TZ)) == 12, "dimanche"
print("expected_decks_now OK")

# --- is_after_monday_noon() ---
assert cal.is_after_monday_noon(datetime(2026, 8, 17, 11, 59, tzinfo=cal.BRUSSELS_TZ)) is False, "lundi 11h59 -> pas encore"
assert cal.is_after_monday_noon(datetime(2026, 8, 17, 12, 0, tzinfo=cal.BRUSSELS_TZ)) is True, "lundi 12h00 pile -> ok"
assert cal.is_after_monday_noon(datetime(2026, 8, 17, 23, 0, tzinfo=cal.BRUSSELS_TZ)) is True, "lundi soir -> ok"
assert cal.is_after_monday_noon(datetime(2026, 8, 18, 0, 1, tzinfo=cal.BRUSSELS_TZ)) is True, "mardi -> ok"
assert cal.is_after_monday_noon(datetime(2026, 8, 23, 20, 0, tzinfo=cal.BRUSSELS_TZ)) is True, "dimanche -> ok"
print("is_after_monday_noon OK")

print("\nTOUS LES TESTS GDC_CALENDAR PASSENT")
