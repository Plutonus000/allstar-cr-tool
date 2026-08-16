"""fmt.py — formatage partagé (dates) utilisé par toutes les vues."""

from __future__ import annotations

from datetime import datetime

_SUPERCELL_FORMATS = ("%Y%m%dT%H%M%S.%fZ", "%Y%m%dT%H%M%SZ")


def _parse(value: str) -> datetime | None:
    if not value:
        return None
    for f in _SUPERCELL_FORMATS:
        try:
            return datetime.strptime(value, f)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def format_date(value: str, with_time: bool = False) -> str:
    """
    Formate une date API Supercell ('20260629T093811.000Z') ou une date ISO
    maison ('2026-08-14T21:08:08+00:00') en dd/mm/yy (ou dd/mm/yy HH:mm).
    Renvoie la valeur brute si le format est inconnu, plutôt que planter.
    """
    dt = _parse(value)
    if dt is None:
        return value or "—"
    return dt.strftime("%d/%m/%y %H:%M" if with_time else "%d/%m/%y")
