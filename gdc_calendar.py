"""
gdc_calendar.py — repères temporels d'une semaine de GDC (jeudi 11h30 → lundi 11h30),
en heure de Bruxelles explicite.

Logique de decks attendus portée de clan_war_bot.py (compute_expected_decks), mais
avec un fuseau horaire EXPLICITE (Europe/Brussels) plutôt que l'heure locale de la
machine qui exécute le code : important ici car l'outil web peut tourner sur un
serveur Streamlit Cloud dans un fuseau différent de la Belgique, contrairement au
bot qui tourne toujours sur le PC de Flo (heure locale = heure belge par construction).

Logique pure (pas de Streamlit, pas de réseau) — testable indépendamment.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

BRUSSELS_TZ = ZoneInfo("Europe/Brussels")

# jour de semaine (0=Lundi ... 6=Dimanche) -> decks attendus à ce stade de la GDC.
# GDC : jeudi 11h30 -> lundi 11h30 (4 jours de guerre : jeudi/vendredi/samedi/dimanche).
#   Vendredi -> 4  (jeudi écoulé)
#   Samedi   -> 8  (jeudi + vendredi écoulés)
#   Dimanche -> 12 (jeudi + vendredi + samedi écoulés)
#   Lundi    -> 16 (GDC complète, avant 11h30 comme après)
#   Mardi/Mercredi -> None (jours de préparation, pas de guerre en cours)
_EXPECTED_DECKS_BY_WEEKDAY = {0: 16, 4: 4, 5: 8, 6: 12}


def now_brussels() -> datetime:
    return datetime.now(BRUSSELS_TZ)


def expected_decks_now(now: datetime | None = None) -> int | None:
    """
    Decks attendus à ce stade de la GDC pour un joueur assidu, ou None si on
    n'est pas dans la fenêtre de GDC (mardi/mercredi).
    """
    now = now or now_brussels()
    return _EXPECTED_DECKS_BY_WEEKDAY.get(now.weekday())


def is_after_monday_noon(now: datetime | None = None) -> bool:
    """
    True à tout moment SAUF le lundi avant 12h00 (heure de Bruxelles) — c'est-à-dire
    à partir du moment où la GDC de la semaine est terminée (fin officielle 11h30,
    marge jusqu'à midi comme le bot) et jusqu'au lundi suivant.
    """
    now = now or now_brussels()
    if now.weekday() != 0:
        return True
    return now.hour >= 12
