"""
history.py — historique GDC étendu au-delà des 10 semaines de l'API officielle.

L'API officielle (`riverracelog`) ne renvoie JAMAIS plus de 10 semaines
d'historique, quel que soit le `limit` demandé (confirmé — c'est une
limitation connue de Supercell, pas un choix de notre client API). C'est
pour ça que royaleapi.com affiche un historique plus long : ils archivent
eux-mêmes chaque semaine au fil du temps plutôt que de compter sur l'API
pour se souvenir du passé. On fait pareil ici, via storage.py (Sheets ou
JSON local selon le backend actif).

Principe : à chaque fois qu'une page charge le race_log live (jusqu'à 10
semaines), on vérifie quelles semaines ne sont pas encore archivées et on
les enregistre. Avec le temps, l'archive dépasse la fenêtre de 10 semaines
de l'API, même si l'API elle-même reste bloquée à 10.
"""

from __future__ import annotations

from datetime import datetime

import streamlit as st

import storage

_SYNCED_FLAG = "_history_synced_clans"


def _norm_tag(tag: str) -> str:
    return tag.strip().upper().lstrip("#")


def _participant_rows(item: dict, clan_tag: str) -> list[dict]:
    target = _norm_tag(clan_tag)
    standing = next(
        (s for s in item.get("standings", []) if _norm_tag(s.get("clan", {}).get("tag", "")) == target),
        None,
    )
    if not standing:
        return []
    season_id = str(item.get("seasonId", ""))
    section_index = item.get("sectionIndex", 0)
    return [
        {
            "season_id": season_id,
            "clan_tag": clan_tag,
            "player_tag": p.get("tag", ""),
            "player_name": p.get("name", ""),
            "decks_used": p.get("decksUsed", 0),
            "fame": p.get("fame", 0),
            "boat_attacks": p.get("boatAttacks", 0),
            "section_index": section_index,
        }
        for p in standing["clan"].get("participants", [])
    ]


def sync_archive(race_log_items: list[dict], clan_tag: str) -> int:
    """
    Archive les GDC terminées du race_log live qui ne le sont pas encore.
    Ne s'exécute qu'une fois PAR SESSION Streamlit et par clan EN CAS DE
    SUCCÈS COMPLET (évite de re-vérifier l'archive à chaque interaction) —
    voir _SYNCED_FLAG. Si une erreur survient sur une semaine, le clan n'est
    PAS marqué comme synchronisé, pour que la prochaine interaction de la même
    session retente (voir ci-dessous).

    Un `seasonId` Supercell peut regrouper plusieurs semaines de GDC
    (`sectionIndex` 0 à 3) : on identifie donc chaque semaine par
    (season_id, section_index) — voir storage.week_key() — plutôt que par
    season_id seul, sous peine de perdre silencieusement des semaines.

    ⚠️ Résilience ajoutée le 16/08/2026 soir (bug signalé par Flo : ancienneté
    affichée à 4 GDC au lieu de >10 dans l'onglet Exclusions) : chaque semaine
    est archivée dans son propre `try/except`. Avant ce correctif, une seule
    erreur (typiquement `gspread.exceptions.APIError [429]`, voir storage.py)
    sur UNE semaine faisait planter toute la boucle — et donc toute la page,
    voire l'app entière si appelé depuis app.py — AVANT que les semaines
    suivantes du lot n'aient pu être archivées. Avec beaucoup de 429 survenus
    ces derniers jours, il est très probable que l'archive de plusieurs
    joueurs (dont Flo) se soit arrêtée en cours de route, sous-estimant leur
    ancienneté réelle tant que ces semaines restent visibles dans la fenêtre
    live de l'API (elles se rattraperont automatiquement au fil des prochains
    chargements, une fois le 429 corrigé — voir aussi le fix d'ordre
    d'écriture dans storage._sheets_archive_season/_local_archive_season pour
    éviter les "semaines fantômes").

    Renvoie le nombre de nouvelles semaines effectivement archivées (peut être
    inférieur au nombre de semaines à archiver s'il y a eu des erreurs).
    """
    synced = st.session_state.setdefault(_SYNCED_FLAG, set())
    if clan_tag in synced:
        return 0

    if not race_log_items:
        synced.add(clan_tag)
        return 0

    already = storage.get_archived_week_keys(clan_tag)
    archived_count = 0
    had_error = False
    for item in race_log_items:
        season_id = str(item.get("seasonId", ""))
        section_index = item.get("sectionIndex", 0)
        if not season_id:
            continue
        key = storage.week_key(season_id, section_index)
        if key in already:
            continue
        rows = _participant_rows(item, clan_tag)
        try:
            storage.archive_season(
                season_id, item.get("createdDate", ""), clan_tag, rows, section_index=section_index
            )
        except Exception:
            # Ne fait PAS planter la page : cette semaine sera retentée au
            # prochain appel (ce clan n'est pas marqué "synced" plus bas).
            had_error = True
            continue
        already.add(key)
        archived_count += 1

    if not had_error:
        synced.add(clan_tag)

    if archived_count:
        _archived_week_meta.clear()

    return archived_count


def _season_year(created_date: str) -> int | None:
    """Année (calendaire) d'une date Supercell compacte ('20260629T...') ou ISO."""
    if not created_date:
        return None
    try:
        return int(str(created_date)[:4])
    except ValueError:
        return None


def _rebuild_item_from_archive(season_id: str, section_index, clan_tag: str, participants: list[dict]) -> dict:
    """Reconstruit un item façon race_log (standings/participants) depuis les lignes
    archivées d'UNE SEULE semaine (déjà regroupées par (season_id, section_index)).

    Déduplique par tag joueur (garde la ligne avec le plus de decks joués) —
    corrige un bug signalé par Flo le 16/08/2026 : 2 pics à >100 000 trophées
    sur le graphique "Trophées du clan" de Statistiques. Cause probable : une
    même semaine archivée deux fois (ex. deux sessions Streamlit concurrentes
    ayant toutes les deux vu la semaine comme "pas encore archivée" avant que
    l'une des deux n'écrive — voir history.sync_archive/storage.get_archived_week_keys),
    ce qui doublait les lignes participant pour cette semaine et donc la somme
    des `fame` calculée juste en dessous. Même pattern défensif que la
    déduplication déjà appliquée à logic.compute_current_race_table() pour le
    bug "83 joueurs"."""
    by_tag: dict[str, dict] = {}
    for r in participants:
        tag = r.get("player_tag", "")
        decks_used = int(r.get("decks_used") or 0)
        existing = by_tag.get(tag)
        if existing is None or decks_used > existing["decksUsed"]:
            by_tag[tag] = {
                "tag": tag,
                "name": r.get("player_name", ""),
                "decksUsed": decks_used,
                "fame": int(r.get("fame") or 0),
                "boatAttacks": int(r.get("boat_attacks") or 0),
            }
    parts = list(by_tag.values())
    return {
        "seasonId": season_id,
        "sectionIndex": section_index,
        "createdDate": "",  # rempli par l'appelant depuis l'index "seasons"
        "standings": [
            {
                "clan": {
                    "tag": clan_tag,
                    "fame": sum(p["fame"] for p in parts),
                    "participants": parts,
                }
            }
        ],
    }


def get_full_history(clan_tag: str, live_race_log: list[dict]) -> list[dict]:
    """
    Renvoie l'historique GDC complet disponible (archive + live), dédupliqué
    par semaine — c'est-à-dire par (seasonId, sectionIndex), PAS par seasonId
    seul : un seasonId Supercell peut contenir plusieurs semaines de GDC, et
    les traiter comme une seule semaine fusionnerait/perdrait des données
    (c'est le bug corrigé ici — voir storage.week_key()). Le live prime sur
    l'archive en cas de recoupement (donnée la plus fraîche). Trié du plus
    récent au plus ancien, au même format que race_log de l'API.
    """
    by_week: dict[str, dict] = {}

    archived_participants = storage.get_archived_participants(clan_tag)
    grouped: dict[str, list[dict]] = {}
    for row in archived_participants:
        key = storage.week_key(row.get("season_id", ""), row.get("section_index", 0))
        grouped.setdefault(key, []).append(row)

    # Dates/season_id/section_index archivés : lus séparément (index "seasons").
    week_meta = _archived_week_meta(clan_tag)
    for key, rows in grouped.items():
        meta = week_meta.get(key, {})
        season_id = meta.get("season_id") or (rows[0].get("season_id", "") if rows else "")
        section_index = meta.get("section_index", rows[0].get("section_index", 0) if rows else 0)
        item = _rebuild_item_from_archive(season_id, section_index, clan_tag, rows)
        item["createdDate"] = meta.get("created_date", "")
        by_week[key] = item

    for item in live_race_log:
        season_id = str(item.get("seasonId", ""))
        if not season_id:
            continue
        key = storage.week_key(season_id, item.get("sectionIndex", 0))
        by_week[key] = item  # le live écrase l'archive si les deux existent

    def _sort_key(it: dict):
        return it.get("createdDate") or "", str(it.get("seasonId") or ""), str(it.get("sectionIndex") or 0)

    return sorted(by_week.values(), key=_sort_key, reverse=True)


@st.cache_data(ttl=30, show_spinner=False)
def _archived_week_meta(clan_tag: str) -> dict:
    """week_key -> {created_date, season_id, section_index}, depuis l'index 'seasons' archivé.
    Mis en cache (comme les fonctions de storage.py) — lecture Sheets directe,
    sinon rappelée à chaque interaction Streamlit (voir storage.py, note sur le
    quota Google Sheets)."""
    if storage.backend_name() == "sheets":
        ws = storage._get_worksheet(storage.SEASONS_SHEET_NAME, storage.SEASONS_FIELDS)
        records = ws.get_all_records()
    else:
        records = storage._local_read(storage.SEASONS_FILE, [])
    out = {}
    for r in records:
        if r.get("clan_tag") != clan_tag:
            continue
        season_id = r.get("season_id", "")
        section_index = r.get("section_index", 0)
        out[storage.week_key(season_id, section_index)] = {
            "created_date": r.get("created_date", ""),
            "season_id": str(season_id),
            "section_index": section_index,
        }
    return out


def _participation_rate(
    full_history: list[dict], player_tag: str, clan_tag: str, year: int | None, full_decks: int = 16
) -> float | None:
    """Taux de participation (%) sur l'historique fourni, filtré sur `year` si précisé."""
    target = _norm_tag(player_tag)
    clan_target = _norm_tag(clan_tag)
    total_used, total_max = 0, 0
    for item in full_history:
        if year is not None and _season_year(item.get("createdDate", "")) != year:
            continue
        standing = next(
            (s for s in item.get("standings", []) if _norm_tag(s.get("clan", {}).get("tag", "")) == clan_target),
            None,
        )
        if not standing:
            continue
        participant = next(
            (p for p in standing["clan"].get("participants", []) if _norm_tag(p.get("tag", "")) == target),
            None,
        )
        if not participant:
            continue
        total_used += participant.get("decksUsed", 0)
        total_max += full_decks
    if total_max == 0:
        return None
    return round(total_used / total_max * 100, 1)


def participation_rate_for_year(
    full_history: list[dict], player_tag: str, clan_tag: str, year: int, full_decks: int = 16
) -> float | None:
    """Taux de participation (%) sur toutes les GDC archivées/live de l'année civile donnée."""
    return _participation_rate(full_history, player_tag, clan_tag, year, full_decks)


def participation_rate_all_time(
    full_history: list[dict], player_tag: str, clan_tag: str, full_decks: int = 16
) -> float | None:
    """Taux de participation (%) sur tout l'historique disponible (archive + live)."""
    return _participation_rate(full_history, player_tag, clan_tag, None, full_decks)


def current_year() -> int:
    return datetime.now().year
