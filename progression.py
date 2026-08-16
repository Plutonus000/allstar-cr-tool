"""
progression.py — série d'assiduité, éligibilité Aîné/Chef adjoint, écarts au règlement.

Logique pure (pas de Streamlit, pas de réseau) — testable indépendamment.
"""

from __future__ import annotations

ELDER_WEEKS_REQUIRED = 5
COLEADER_WEEKS_REQUIRED = 10
FULL_DECKS_PER_RACE = 16  # V1 : pas de proratisation mid-war (comme logic.compute_ranking)


def _norm(tag: str) -> str:
    return tag.strip().upper().lstrip("#")


def _find_our_standing(item: dict, clan_tag: str) -> dict | None:
    target = _norm(clan_tag)
    return next(
        (s for s in item.get("standings", []) if _norm(s.get("clan", {}).get("tag", "")) == target),
        None,
    )


def compute_participation_streak(race_log_items: list[dict], player_tag: str, clan_tag: str) -> tuple[int, list[dict]]:
    """
    Parcourt les GDC de la plus récente à la plus ancienne et compte la série
    en cours de GDC consécutives jouées à 100% (16/16 decks). S'arrête au
    premier manque, à la première absence, ou à la première GDC incomplète.

    Renvoie (streak_semaines, historique) — historique couvre toute la
    fenêtre fournie (utile pour affichage détaillé), pas seulement la série.
    """
    target = _norm(player_tag)
    history = []
    streak = 0
    streak_broken = False

    for item in race_log_items:
        standing = _find_our_standing(item, clan_tag)
        participant = None
        if standing:
            participant = next(
                (p for p in standing["clan"].get("participants", []) if _norm(p.get("tag", "")) == target),
                None,
            )

        present = participant is not None
        decks_used = participant.get("decksUsed", 0) if participant else 0
        full = present and decks_used >= FULL_DECKS_PER_RACE

        history.append(
            {
                "seasonId": item.get("seasonId"),
                "createdDate": item.get("createdDate"),
                "present": present,
                "decks_used": decks_used,
                "full": full,
            }
        )

        if not streak_broken:
            if full:
                streak += 1
            else:
                streak_broken = True

    return streak, history


def eligibility_status(streak_weeks: int) -> dict:
    return {
        "streak_weeks": streak_weeks,
        "elder_eligible": streak_weeks >= ELDER_WEEKS_REQUIRED,
        "coleader_eligible": streak_weeks >= COLEADER_WEEKS_REQUIRED,
        "weeks_to_elder": max(0, ELDER_WEEKS_REQUIRED - streak_weeks),
        "weeks_to_coleader": max(0, COLEADER_WEEKS_REQUIRED - streak_weeks),
    }


def participation_rate(race_log_items: list[dict], player_tag: str, clan_tag: str, n_races: int = 10) -> float | None:
    """Taux de participation moyen (%) sur les n_races dernières GDC où le joueur était présent."""
    target = _norm(player_tag)
    total_used = 0
    total_max = 0

    for item in race_log_items[:n_races]:
        standing = _find_our_standing(item, clan_tag)
        if not standing:
            continue
        participant = next(
            (p for p in standing["clan"].get("participants", []) if _norm(p.get("tag", "")) == target),
            None,
        )
        if not participant:
            continue
        total_used += participant.get("decksUsed", 0)
        total_max += FULL_DECKS_PER_RACE

    if total_max == 0:
        return None
    return round(total_used / total_max * 100, 1)


def find_rule_violations(race_log_items: list[dict], clan_tag: str, n_races: int = 1) -> list[dict]:
    """
    V1 simple : joueurs n'ayant pas joué tous leurs decks sur la/les dernière(s)
    GDC. Base pour l'onglet "Alertes" — à enrichir plus tard (attaques bateau
    adverse, etc.) si besoin.
    """
    violations = []
    for item in race_log_items[:n_races]:
        standing = _find_our_standing(item, clan_tag)
        if not standing:
            continue
        for p in standing["clan"].get("participants", []):
            decks_used = p.get("decksUsed", 0)
            if decks_used < FULL_DECKS_PER_RACE:
                violations.append(
                    {
                        "player_tag": p.get("tag"),
                        "name": p.get("name"),
                        "decks_used": decks_used,
                        "decks_expected": FULL_DECKS_PER_RACE,
                        "seasonId": item.get("seasonId"),
                        "createdDate": item.get("createdDate"),
                    }
                )
    return violations


def find_promotable_players(members: list[dict], race_log_items: list[dict], clan_tag: str) -> list[dict]:
    """
    Pour chaque membre (rôle 'member' ou 'elder'), calcule sa série et indique
    s'il vient d'atteindre le palier Aîné ou Chef adjoint. Les rôles déjà au niveau
    ou au-dessus (coLeader/leader) sont exclus — rien à promouvoir.
    """
    promotable = []
    for m in members:
        role = m.get("role")
        if role in ("coLeader", "leader"):
            continue
        streak, _ = compute_participation_streak(race_log_items, m.get("tag", ""), clan_tag)
        status = eligibility_status(streak)
        if role == "member" and status["elder_eligible"]:
            promotable.append({**m, "streak_weeks": streak, "next_rank": "Aîné"})
        elif role == "elder" and status["coleader_eligible"]:
            promotable.append({**m, "streak_weeks": streak, "next_rank": "Chef adjoint"})
    return promotable
