"""
logic.py — fonctions métier pures (pas de dépendance à Streamlit), donc testables seules.

app.py importe ces fonctions et se contente de les brancher à l'interface.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import pandas as pd

import clash_api as api
import fmt


def norm_tag(tag: str) -> str:
    return tag.strip().upper().lstrip("#")


def compute_ranking(race_log_items: list[dict], clan_tag: str, n_races: int) -> pd.DataFrame:
    """
    Agrège les GDC les plus récentes (jusqu'à n_races) pour construire un classement
    par joueur : nombre de GDC jouées, decks utilisés, fame, assiduité.

    Hypothèse V1 : max théorique = 16 decks/GDC (pas de proratisation des arrivées
    en cours de GDC ici, contrairement au bot Discord — à affiner plus tard si besoin).
    """
    target = norm_tag(clan_tag)
    rows: dict[str, dict] = {}

    for item in race_log_items[:n_races]:
        our_standing = next(
            (s for s in item.get("standings", []) if norm_tag(s.get("clan", {}).get("tag", "")) == target),
            None,
        )
        if not our_standing:
            continue
        clan_data = our_standing["clan"]
        for p in clan_data.get("participants", []):
            tag = p.get("tag", "")
            row = rows.setdefault(
                tag,
                {"Tag": tag, "Joueur": p.get("name", "?"), "GDC jouées": 0, "Decks joués": 0, "Trophées totaux": 0},
            )
            row["GDC jouées"] += 1
            row["Decks joués"] += p.get("decksUsed", 0)
            row["Trophées totaux"] += p.get("fame", 0)
            row["Joueur"] = p.get("name", row["Joueur"])  # garde le nom le plus récent

    if not rows:
        return pd.DataFrame(
            columns=["Rang", "Joueur", "Tag", "GDC jouées", "Decks joués", "Decks max", "Assiduité %", "Trophées totaux", "Trophées moy./GDC"]
        )

    df = pd.DataFrame(rows.values())
    df["Decks max"] = df["GDC jouées"] * 16
    df["Assiduité %"] = (df["Decks joués"] / df["Decks max"] * 100).round(1)
    df["Trophées moy./GDC"] = (df["Trophées totaux"] / df["GDC jouées"]).round(0).astype(int)
    df = df.sort_values(["Assiduité %", "Trophées totaux"], ascending=False).reset_index(drop=True)
    df.insert(0, "Rang", range(1, len(df) + 1))
    return df[["Rang", "Joueur", "Tag", "GDC jouées", "Decks joués", "Decks max", "Assiduité %", "Trophées totaux", "Trophées moy./GDC"]]


def compute_current_race_table(current_race: dict) -> pd.DataFrame:
    """
    Note : l'endpoint `currentriverrace` de Supercell garde dans `participants`
    tout joueur ayant contribué à la GDC en cours même s'il a quitté le clan
    entre-temps (il n'y a normalement pas de doublon de tag, mais on
    déduplique quand même par sécurité — garde l'entrée avec le plus de decks
    joués). C'est pour ça que ce tableau peut afficher plus de 50 lignes : le
    filtrage sur les membres ACTUELS du clan se fait côté appelant (voir
    `current_tags` dans views/ranking.py), pas ici.
    """
    participants = current_race.get("clan", {}).get("participants", [])
    if not participants:
        return pd.DataFrame(columns=["Joueur", "Tag", "Decks joués", "Decks aujourd'hui", "Trophées", "Attaques bateau adverse"])
    by_tag: dict[str, dict] = {}
    for p in participants:
        tag = p.get("tag", "")
        existing = by_tag.get(tag)
        if existing is None or p.get("decksUsed", 0) > existing.get("decksUsed", 0):
            by_tag[tag] = p
    df = pd.DataFrame(
        [
            {
                "Joueur": p.get("name", "?"),
                "Tag": p.get("tag", ""),
                "Decks joués": p.get("decksUsed", 0),
                "Decks aujourd'hui": p.get("decksUsedToday", 0),
                "Trophées": p.get("fame", 0),
                "Attaques bateau adverse": p.get("boatAttacks", 0),
            }
            for p in by_tag.values()
        ]
    )
    return df.sort_values("Decks joués", ascending=False).reset_index(drop=True)


def compute_card_levels(player_data: dict) -> pd.DataFrame:
    cards = player_data.get("cards", [])
    if not cards:
        return pd.DataFrame(columns=["Carte", "Rareté", "Niveau (jeu)", "Niveau (interne)", "Niveau max"])
    rows = []
    for c in cards:
        max_level = c.get("maxLevel", 14)
        level = c.get("level", 0)
        rows.append(
            {
                "Carte": c.get("name", "?"),
                "Rareté": c.get("rarity", "?"),
                "Niveau (jeu)": api.normalized_card_level(level, max_level),
                "Niveau (interne)": level,
                "Niveau max": max_level,
            }
        )
    return pd.DataFrame(rows).sort_values("Niveau (jeu)").reset_index(drop=True)


def fetch_all_members_cards(
    member_tags: list[str],
    player_loader: Callable[[str], dict],
    max_workers: int = 5,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> dict[str, dict]:
    """Récupère les fiches joueur (avec cartes) de plusieurs membres en parallèle limité."""
    results: dict[str, dict] = {}
    done = 0
    total = len(member_tags)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(player_loader, tag): tag for tag in member_tags}
        for future in as_completed(futures):
            tag = futures[future]
            try:
                results[tag] = future.result()
            except api.ClashAPIError as exc:
                results[tag] = {"__error__": str(exc)}
            done += 1
            if progress_cb:
                progress_cb(done, total)
            time.sleep(0.05)  # petite marge anti-rate-limit
    return results


# ---------------------------------------------------------------------------
# Page Statistiques (16/08/2026) — série "1 point = 1 GDC" (= 1 semaine, comme
# ailleurs dans l'outil : voir history._participation_rate et
# compute_ranking() ci-dessus, qui comptent chaque item de race_log/full_history
# comme 1 GDC, PAS chaque "saison" de 4 semaines regroupée dans Historique GDC —
# ce regroupement par saison n'est qu'un choix d'affichage dans views/ranking.py).
# ---------------------------------------------------------------------------

FULL_DECKS_PER_GDC = 16  # 4 jours x 4 decks, cf. formule donnée par Flo


def compute_gdc_series(full_history: list[dict], clan_tag: str) -> pd.DataFrame:
    """
    Une ligne par semaine de GDC disponible (archive + live), triée du plus
    ancien au plus récent (ordre chronologique, pour tracer des courbes) :
    Label (affichage court), createdDate (brute), seasonId, sectionIndex,
    Participants, TauxParticipation (%), TrophéesClan, TrophéeMoyenParJoueur.
    """
    target = norm_tag(clan_tag)
    rows = []
    for item in full_history:
        standing = next(
            (s for s in item.get("standings", []) if norm_tag(s.get("clan", {}).get("tag", "")) == target),
            None,
        )
        if not standing:
            continue
        # Déduplication défensive par tag (même pattern que
        # compute_current_race_table, bug "83 joueurs") — garde l'entrée avec
        # le plus de decks joués. Protège aussi le calcul de repli
        # (sum(fame) si le champ "fame" officiel est absent) contre un
        # doublon éventuel de la liste de participants.
        by_tag: dict[str, dict] = {}
        for p in standing["clan"].get("participants", []):
            tag = p.get("tag", "")
            existing = by_tag.get(tag)
            if existing is None or p.get("decksUsed", 0) > existing.get("decksUsed", 0):
                by_tag[tag] = p
        participants = list(by_tag.values())
        n = len(participants)
        if n == 0:
            continue
        decks_used = sum(p.get("decksUsed", 0) for p in participants)
        decks_max = n * FULL_DECKS_PER_GDC
        clan_fame = standing["clan"].get("fame", sum(p.get("fame", 0) for p in participants))
        created_date = item.get("createdDate", "")
        season_id = str(item.get("seasonId", ""))
        section_index = item.get("sectionIndex", 0)
        rows.append(
            {
                "Label": f"{fmt.format_date(created_date)} (#{season_id}.{section_index + 1})"
                if created_date else f"#{season_id}.{section_index + 1}",
                "createdDate": created_date,
                "seasonId": season_id,
                "sectionIndex": section_index,
                "Participants": n,
                "TauxParticipation": round(decks_used / decks_max * 100, 1) if decks_max else None,
                "TrophéesClan": clan_fame,
                "TrophéeMoyenParJoueur": round(clan_fame / n, 1) if n else None,
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "Label", "createdDate", "seasonId", "sectionIndex", "Participants",
                "TauxParticipation", "TrophéesClan", "TrophéeMoyenParJoueur",
            ]
        )
    df = pd.DataFrame(rows)
    return df.sort_values("createdDate").reset_index(drop=True)  # plus ancien -> plus récent


def filter_gdc_series(series: pd.DataFrame, period: str, this_year: Optional[int] = None) -> pd.DataFrame:
    """
    Filtre une série renvoyée par compute_gdc_series() selon la période choisie
    dans la page Statistiques : "last1" (dernière GDC), "last10" (10 dernières),
    "year" (année civile en cours, nécessite this_year), "all" (tout l'historique
    archivé disponible).
    """
    if series.empty:
        return series
    if period == "last1":
        return series.tail(1).reset_index(drop=True)
    if period == "last10":
        return series.tail(10).reset_index(drop=True)
    if period == "year":
        years = series["createdDate"].astype(str).str[:4]
        return series[years == str(this_year)].reset_index(drop=True)
    return series.reset_index(drop=True)  # "all"


# Sous-chaînes (en minuscules) du champ `type` d'un combat de battlelog considérées
# comme "combat de GDC" — NON VÉRIFIÉ en conditions réelles (voir avertissement
# dans clash_api.get_player_battlelog). À ajuster une fois testé chez Flo.
_RIVER_RACE_TYPE_HINTS = ("riverrace", "clanwar", "warday")


def _battle_day_key(battle: dict) -> str:
    """Jour calendaire (8 premiers caractères, 'YYYYMMDD') d'un combat, à partir
    de son `battleTime` brut Supercell ('20260810T183000.000Z' -> '20260810')."""
    bt = str(battle.get("battleTime", ""))
    return bt[:8]


def compute_maxed_cards_in_war_deck(battlelog: list[dict], player_tag: str) -> Optional[dict]:
    """
    Regarde les combats de GDC (voir _RIVER_RACE_TYPE_HINTS — filtre best-effort
    et non vérifié) du battlelog d'un joueur, groupés par jour calendaire (un
    jour de GDC = jusqu'à 4 decks joués). Prend le jour le plus récent ayant
    AU MOINS 4 combats de GDC (un "jour complet"), et compte le nombre de
    cartes DISTINCTES au niveau max (level == maxLevel) parmi toutes les cartes
    utilisées sur les 4 decks de ce jour-là (une même carte utilisée dans
    plusieurs decks du jour n'est comptée qu'une fois) — demande explicite de
    Flo le 16/08/2026 : "il faudrait prendre sur les 4 decks de GDC... regarder
    le dernier jour de GDC où les 4 decks ont été joués et prendre les cartes
    des 4 decks", plutôt que le seul tout dernier combat joué (1ère version,
    corrigée le même jour après son retour).

    Si aucun jour n'a 4 combats de GDC complets (ex. battlelog qui ne couvre
    pas un jour entier), on retombe sur le jour le plus récent disponible
    quand même (avec moins de decks) plutôt que de renvoyer None — le champ
    `partial_day` du résultat indique alors que ce n'est pas un jour complet
    (à afficher comme nuance côté UI). Renvoie None si aucun combat de GDC
    n'est trouvé dans le battlelog fourni (rétention limitée côté API — voir
    clash_api.get_player_battlelog).

    Le niveau max est comparé via le champ `maxLevel` renvoyé par l'API pour
    CHAQUE carte (pas un "16" en dur), puisque ce nombre peut différer d'une
    rareté à l'autre et changer avec le temps côté jeu.
    """
    if not battlelog:
        return None
    target = norm_tag(player_tag)
    river_battles = [
        b for b in battlelog
        if any(hint in str(b.get("type", "")).lower() for hint in _RIVER_RACE_TYPE_HINTS)
    ]
    if not river_battles:
        return None

    by_day: dict[str, list[dict]] = {}
    for b in river_battles:
        by_day.setdefault(_battle_day_key(b), []).append(b)

    days_sorted = sorted(by_day.keys(), reverse=True)  # plus récent en premier
    chosen_day = next((d for d in days_sorted if len(by_day[d]) >= 4), None)
    partial_day = chosen_day is None
    if chosen_day is None:
        chosen_day = days_sorted[0] if days_sorted else None
    if chosen_day is None:
        return None

    day_battles = by_day[chosen_day]
    cards_seen: dict[str, dict] = {}  # clé = nom de carte, dédup entre les decks du jour
    for battle in day_battles:
        team = battle.get("team", [])
        own = next((t for t in team if norm_tag(t.get("tag", "")) == target), team[0] if team else None)
        if not own:
            continue
        for c in own.get("cards", []):
            key = c.get("name") or str(c.get("id", ""))
            if key:
                cards_seen.setdefault(key, c)

    if not cards_seen:
        return None
    maxed = sum(
        1 for c in cards_seen.values()
        if c.get("level") is not None and c.get("maxLevel") is not None and c["level"] >= c["maxLevel"]
    )
    return {
        "maxed": maxed,
        "total": len(cards_seen),
        "battle_time": day_battles[0].get("battleTime", ""),
        "decks_count": len(day_battles),
        "partial_day": partial_day,
    }


def member_since(full_history: list[dict], player_tag: str, clan_tag: str) -> Optional[str]:
    """
    Date (brute, format Supercell) de la plus ancienne semaine archivée où le
    joueur apparaît comme participant du clan — une approximation de "membre
    depuis", puisque l'API ne fournit pas de vraie date d'entrée dans le clan.
    Renvoie None si le joueur n'apparaît dans aucune semaine de l'historique
    fourni (ex : nouveau membre pas encore passé par une GDC archivée).
    """
    target = norm_tag(player_tag)
    clan_target = norm_tag(clan_tag)
    dates = []
    for item in full_history:
        standing = next(
            (s for s in item.get("standings", []) if norm_tag(s.get("clan", {}).get("tag", "")) == clan_target),
            None,
        )
        if not standing:
            continue
        if any(norm_tag(p.get("tag", "")) == target for p in standing["clan"].get("participants", [])):
            created_date = item.get("createdDate", "")
            if created_date:
                dates.append(created_date)
    return min(dates) if dates else None
