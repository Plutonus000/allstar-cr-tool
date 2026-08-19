"""
exclusions.py — moteur de détection des exclusions/avertissements/grâces et
des tiers "Avengers".

Règles de détection (2e refonte avec Flo le 18/08/2026 soir — la 1ère refonte
du même jour, à base de "GDC précédente complète ou non", est remplacée par
un système à 2 régimes ci-dessous ; voir git history si besoin de retrouver
une version antérieure) :

- Règle 1 : la toute première GDC visible d'un joueur dans le clan (semaine
  d'arrivée) n'est JAMAIS prise en compte, quel que soit son contenu — ni
  complète, ni incomplète, ni bateau. Limitation connue et acceptée avec Flo :
  l'API Supercell ne donne que le total de decks joués par semaine pour
  l'historique passé (pas de détail jour par jour), donc on ne peut pas
  distinguer "avant l'arrivée" de "après l'arrivée" à l'intérieur de cette
  1ère semaine — on l'exempte donc entièrement plutôt que de pénaliser à tort.
- Règle 2 (régime STRICT) : tant qu'un joueur n'a JAMAIS eu, à un moment de
  son historique, GRADUATION_STREAK (5) GDC CONSÉCUTIVES complètes (tous les
  decks joués, aucune attaque de bateau) depuis son arrivée, il reste dans le
  régime strict : TOUTE GDC incomplète (hors semaine d'arrivée) = avertissement
  direct, aucune grâce possible. Une ancienneté élevée ne suffit PAS à elle
  seule à sortir de ce régime — seul un vrai streak de 5 GDC complètes
  d'affilée le permet (demande explicite de Flo, 18/08/2026 : "un joueur qui a
  15 GDC d'ancienneté mais jamais 5 GDC d'affilée ne fait toujours pas partie
  du régime assoupli").
- Règle 3 : toute attaque de bateau adverse pendant une GDC = avertissement
  automatique, sauf en semaine d'arrivée (toujours exemptée par la Règle 1).
  Une semaine "bateau" ne compte JAMAIS comme candidate à la grâce (Règle 4),
  et casse le streak de GDC consécutives complètes (Règle 2) — seule une GDC
  réellement complète (tous les decks joués ET aucune attaque de bateau) fait
  progresser ce streak.
- Règle 4 (régime ASSOUPLI) : une fois que le joueur a eu, À N'IMPORTE QUEL
  MOMENT de son historique, GRADUATION_STREAK (5) GDC consécutives complètes,
  il passe DÉFINITIVEMENT dans le régime assoupli — même s'il enchaîne ensuite
  des manquements, il n'y retourne JAMAIS ("une fois qu'on passe en régime
  assoupli on y reste pour toujours", Flo 18/08/2026). Dans ce régime : sur
  une fenêtre glissante des NB_GDC (10) dernières GDC, la 1ère GDC incomplète
  (hors bateau, hors arrivée) = grâce automatique, chaque GDC incomplète
  suivante DANS LA MÊME FENÊTRE = avertissement — un joueur assoupli a donc
  droit à 1 GDC incomplète tolérée toutes les 10 GDC. Seules les GDC déjà
  survenues APRÈS le passage en régime assoupli comptent comme candidates à
  cette grâce (une GDC incomplète d'avant la graduation, déjà avertissement
  sous le régime strict, ne "consomme" pas la grâce disponible après coup).
- Règle 5 : GRACE_TO_WARN_RATIO (3) grâces cumulées (sur la fenêtre glissante
  de 10 GDC) = 1 avertissement généré (par tranche complète de 3 — la grâce
  affichée reste donc toujours entre 0 et 2).
- Règle 6 : tout se calcule sur une fenêtre glissante de NB_GDC (10) GDC — un
  événement (grâce/avertissement) sort naturellement du compte une fois que
  la GDC qui l'a généré a plus de 10 semaines. Chaque semaine ne compte
  qu'une seule fois (pas de recomptage en glissant). Le passage en régime
  assoupli (Règle 4), lui, regarde toujours la vraie chronologie complète du
  joueur, même au-delà de cette fenêtre de 10 — un streak de 5 GDC complètes
  vieux de plusieurs mois reste acquis pour toujours.
- WARN_TO_EXCL_THRESHOLD (3) avertissements actifs (cumulés, jamais remis à
  zéro tant qu'ils sont dans la fenêtre de 10 GDC) → le joueur PASSE dans la
  liste des exclusions recommandées (et sort de la liste des avertissements) ;
  si le nombre d'avertissements actifs redescend sous 3 (glissement de
  fenêtre), il revient automatiquement dans les avertissements. Il n'y a donc
  AUCUN cas d'exclusion recommandée directe au niveau d'une seule semaine —
  c'est toujours cette accumulation d'avertissements qui y mène. Rien n'est
  mémorisé nulle part : tout est recalculé à chaque affichage depuis
  l'historique archivé (voir history.py) — pas de journal séparé qui
  pourrait diverger.
- Grâce manuelle (bouton "grâcier" d'un chef, voir storage.get_manual_graces) :
  transforme la semaine concernée en "grâce" (peu importe son statut de base),
  cette grâce participe ensuite normalement au comptage glissant (Règle 5).

Seuls les joueurs actuellement dans le clan sont retenus dans les rapports
(voir le paramètre `current_tags` de build_exclusion_report) — un joueur
exclu/parti ne doit plus apparaître.
"""

from __future__ import annotations

NB_GDC = 10  # fenêtre glissante d'analyse (Règles 4/5/6)
GRADUATION_STREAK = 5  # Règle 2/4 : nb de GDC consécutives complètes pour passer en régime assoupli (à vie)
GRACE_TO_WARN_RATIO = 3  # Règle 5 : 3 grâces glissantes -> 1 avertissement généré
WARN_TO_EXCL_THRESHOLD = 3  # avertissements actifs -> le joueur passe en exclusion
FULL_DECKS = 16


def _norm(tag: str) -> str:
    return (tag or "").strip().upper().lstrip("#")


def _find_our_standing(item: dict, clan_tag: str) -> dict | None:
    target = _norm(clan_tag)
    return next(
        (s for s in item.get("standings", []) if _norm(s.get("clan", {}).get("tag", "")) == target),
        None,
    )


def compute_player_stats(gdcs: list[dict], clan_tag: str) -> dict:
    """
    Stats agrégées par joueur (clé = tag normalisé) sur les GDC fournies
    (plus récente en premier, comme le race_log de l'API). Utilisé pour le
    Classement / les tiers Avengers — PAS pour les exclusions (voir
    build_exclusion_report ci-dessous, qui a besoin de l'historique complet
    pour calculer l'ancienneté réelle, pas seulement de la fenêtre affichée).
    """
    stats: dict[str, dict] = {}
    for gdc in gdcs:
        standing = _find_our_standing(gdc, clan_tag)
        if not standing:
            continue
        for p in standing["clan"].get("participants", []):
            tag = _norm(p.get("tag", ""))
            if not tag:
                continue
            s = stats.setdefault(
                tag,
                {
                    "tag": tag,
                    "name": p.get("name", tag),
                    "gdc_count": 0,
                    "total_decks": 0,
                    "total_boat_attacks": 0,
                    "total_fame": 0,
                    "history": [],  # plus récent en premier
                },
            )
            s["name"] = p.get("name", s["name"])
            s["gdc_count"] += 1
            s["total_decks"] += p.get("decksUsed", 0)
            s["total_boat_attacks"] += p.get("boatAttacks", 0)
            s["total_fame"] += p.get("fame", 0)
            s["history"].append(
                {
                    "seasonId": gdc.get("seasonId"),
                    "createdDate": gdc.get("createdDate"),
                    "decks": p.get("decksUsed", 0),
                    "boats": p.get("boatAttacks", 0),
                    "fame": p.get("fame", 0),
                }
            )

    for s in stats.values():
        g = s["gdc_count"]
        if g == 0:
            s["avg_fame"] = 0
            s["assiduity_pct"] = 0.0
            s["ranking_score"] = 0.0
            continue
        max_decks = g * FULL_DECKS  # pas de proratisation mid-war (voir docstring du module)
        assiduity = s["total_decks"] / max_decks if max_decks else 0.0
        avg_fame = s["total_fame"] / g
        s["avg_fame"] = round(avg_fame)
        # Arrondi au centième (2 décimales) — demande de Flo, 16/08/2026 soir
        # (affichage type "42.0000000000" dans le tableau Classement).
        s["assiduity_pct"] = round(assiduity * 100, 2)
        s["ranking_score"] = avg_fame * assiduity

    return stats


# ---------------------------------------------------------------------------
# Tiers "Avengers" — inchangé (pas concerné par la refonte des règles)
# ---------------------------------------------------------------------------

TIERS = [
    ("🏆 AVENGERS ASSEMBLE", 5),
    ("⚡ AVENGERS CORE", 10),
    ("🧠 NEW AVENGERS", 10),
    ("🛡️ AVENGERS RESERVE", None),  # tous les restants
]
TIER_FULL_THRESHOLD = 7  # ≥ 7 GDC → tiers principaux
TIER_MID_THRESHOLD = 4  # 4-6 GDC → S.H.I.E.L.D. ; < 4 GDC → MULTIVERSE
SHIELD_TIER = "🛡️ S.H.I.E.L.D. ACADEMY"
MULTIVERSE_TIER = "🌌 WELCOME TO THE MULTIVERSE"

# Ordre d'affichage des paliers, du meilleur au moins établi — source unique
# (voir ranked_list() ci-dessous) pour que le classement et "Mon profil" ne
# divergent jamais sur le rang d'un joueur.
TIER_ORDER = [name for name, _ in TIERS] + [SHIELD_TIER, MULTIVERSE_TIER]

TIER_DESCRIPTIONS = {
    "🏆 AVENGERS ASSEMBLE": "Le top 5 du clan — les joueurs les plus performants et assidus (≥7 GDC jouées).",
    "⚡ AVENGERS CORE": "Rangs 6 à 15 — le noyau solide et très régulier du clan (≥7 GDC jouées).",
    "🧠 NEW AVENGERS": "Rangs 16 à 25 — bon niveau, en progression (≥7 GDC jouées).",
    "🛡️ AVENGERS RESERVE": "Rangs 26 et plus parmi les joueurs établis (≥7 GDC jouées).",
    "🛡️ S.H.I.E.L.D. ACADEMY": "4 à 6 GDC jouées — historique encore court pour intégrer un palier Avengers.",
    "🌌 WELCOME TO THE MULTIVERSE": "Moins de 4 GDC jouées — nouveaux arrivants ou très faible historique récent.",
}


def build_tiers(stats: dict) -> dict:
    """Classe les joueurs (sortie de compute_player_stats) dans les tiers Avengers."""
    main, shield, multi = [], [], []
    for s in stats.values():
        g = s["gdc_count"]
        if g >= TIER_FULL_THRESHOLD:
            main.append(s)
        elif g >= TIER_MID_THRESHOLD:
            shield.append(s)
        else:
            multi.append(s)

    # Tri par moyenne de trophées (avg_fame) sur la fenêtre de GDC jouées
    # (≤10, voir compute_player_stats) — demande de Flo, 16/08/2026 soir :
    # "le classement doit être classé en fonction de la moyenne de trophées
    # sur les 10 dernières GDC (ou moins, si le joueur n'a pas 10)".
    main.sort(key=lambda s: s["avg_fame"], reverse=True)
    shield.sort(key=lambda s: s["avg_fame"], reverse=True)
    multi.sort(key=lambda s: s["gdc_count"] * 10000 + s["avg_fame"], reverse=True)

    tiers: dict[str, list[dict]] = {}
    idx = 0
    for name, size in TIERS:
        if size is None:
            tiers[name] = main[idx:]
        else:
            tiers[name] = main[idx : idx + size]
            idx += size
    tiers[SHIELD_TIER] = shield
    tiers[MULTIVERSE_TIER] = multi
    return tiers


def player_tier(player_tag: str, tiers: dict) -> str | None:
    tag = _norm(player_tag)
    for name, players in tiers.items():
        if any(p["tag"] == tag for p in players):
            return name
    return None


def ranked_list(stats: dict) -> list[dict]:
    """
    Classe tous les joueurs (sortie de compute_player_stats) par palier Avengers
    (voir build_tiers) puis aplatit en une liste unique dans l'ordre d'affichage
    du classement. Chaque joueur reçoit un "rang" global et son "tier" — c'est
    la SEULE source de vérité pour le rang d'un joueur, utilisée à la fois par
    views/ranking.py (tableau) et views/profile.py ("Position au classement"),
    pour qu'ils ne puissent jamais afficher un rang différent pour la même
    personne (le rang suit le même critère — avg_fame, la moyenne de trophées —
    que les sections).
    """
    tiers = build_tiers(stats)
    out = []
    rang = 0
    for tier_name in TIER_ORDER:
        for p in tiers.get(tier_name, []):
            rang += 1
            out.append({**p, "rang": rang, "tier": tier_name})
    return out


# ---------------------------------------------------------------------------
# Règles d'exclusion — Règles 1 à 5 (voir docstring du module)
# ---------------------------------------------------------------------------


def rules_summary_markdown() -> str:
    """
    Résumé court (liste à puces) du règlement des exclusions (Règles 1 à 6 —
    voir docstring du module pour le détail complet), affiché aux joueurs sur
    "Mon profil" (à côté de "Points à surveiller") et aux chefs sur "Suivi
    clan" > "Exclusions" (tout en haut, avant les rapports) — demande de Flo,
    16/08/2026 soir. Généré à partir des constantes du module ci-dessus pour
    ne jamais diverger des vraies règles appliquées par le moteur.

    2e refonte du 18/08/2026 (avec Flo) : système à 2 régimes — strict tant
    que le joueur n'a jamais eu GRADUATION_STREAK GDC consécutives complètes,
    puis assoupli (1 GDC incomplète tolérée par fenêtre de 10) une fois ce
    streak atteint une fois, à vie ; les attaques de bateau adverse ne sont
    plus une exclusion directe mais un avertissement.
    """
    return (
        "- **1ère GDC dans le clan** : toujours exemptée, quel que soit son contenu.\n"
        f"- **Tant que le joueur n'a jamais eu {GRADUATION_STREAK} GDC consécutives complètes** "
        "(tous les decks joués, aucune attaque de bateau) depuis son arrivée : toute GDC incomplète "
        "= avertissement direct, aucune grâce possible. Une ancienneté élevée ne suffit pas à elle "
        f"seule à sortir de ce régime — il faut un vrai streak de {GRADUATION_STREAK} GDC complètes "
        "d'affilée.\n"
        f"- **Dès que le joueur a eu, une fois dans son historique, {GRADUATION_STREAK} GDC "
        "consécutives complètes** : passage définitif (à vie, même en cas de manquements ensuite) à "
        f"un régime assoupli où, sur une fenêtre glissante des {NB_GDC} dernières GDC, la 1ère GDC "
        "incomplète = grâce automatique, chaque GDC incomplète suivante dans la même fenêtre = "
        "avertissement.\n"
        "- **Attaque de bateau adverse** : avertissement automatique (sauf en semaine d'arrivée).\n"
        f"- **{GRACE_TO_WARN_RATIO} grâces cumulées** (fenêtre glissante) = 1 avertissement supplémentaire généré.\n"
        f"- **{WARN_TO_EXCL_THRESHOLD} avertissements actifs** (sur les {NB_GDC} dernières GDC) = "
        "recommandation d'exclusion — c'est la SEULE façon d'être recommandé à l'exclusion, il n'y a "
        "plus d'exclusion directe pour une seule GDC.\n"
        f"- Le comptage des grâces/avertissements actifs se fait sur une fenêtre glissante des "
        f"{NB_GDC} dernières GDC — un manquement ancien sort automatiquement du compte au fil des "
        "semaines."
    )


def manual_grace_keys(graces: list[dict]) -> set[tuple[str, str]]:
    """Convertit storage.get_manual_graces() en ensemble (tag_normalisé, season_id) —
    utilisé pour repérer quelles semaines ont été graciées manuellement par un chef."""
    return {(_norm(g.get("player_tag", "")), str(g.get("season_id", ""))) for g in graces}


def _all_players_weeks(full_history: list[dict], clan_tag: str) -> dict[str, list[dict]]:
    """
    tag normalisé -> liste CHRONOLOGIQUE (du plus ancien au plus récent) des
    semaines où ce joueur apparaît dans `full_history` (le plus récent en
    premier en entrée, comme history.get_full_history() — on inverse ici).

    Chaque semaine porte son "tenure" = ancienneté cumulée du joueur à cette
    semaine (1 = semaine d'arrivée dans le clan, voir Règle 1/2).
    """
    chrono = list(reversed(full_history))
    per_player: dict[str, list[dict]] = {}
    tenure_counter: dict[str, int] = {}

    for item in chrono:
        standing = _find_our_standing(item, clan_tag)
        if not standing:
            continue
        season_id = item.get("seasonId")
        section_index = item.get("sectionIndex", 0)
        si = section_index if section_index not in (None, "") else 0
        week_key = f"{season_id}_{si}"
        for p in standing["clan"].get("participants", []):
            tag = _norm(p.get("tag", ""))
            if not tag:
                continue
            tenure_counter[tag] = tenure_counter.get(tag, 0) + 1
            tenure = tenure_counter[tag]
            per_player.setdefault(tag, []).append(
                {
                    "seasonId": season_id,
                    "sectionIndex": section_index,
                    "week_key": week_key,
                    "createdDate": item.get("createdDate"),
                    "decks": p.get("decksUsed", 0),
                    "boats": p.get("boatAttacks", 0),
                    "fame": p.get("fame", 0),
                    "name": p.get("name", tag),
                    "tenure": tenure,
                    "is_join_week": tenure == 1,
                }
            )
    return per_player


def format_week_line(week: dict) -> str:
    """
    Ligne compacte pour une semaine d'infraction — "GDC #X - Y/16 decks
    joués (Règle N)" (ou "GDC #X - N attaque(s) de bateau adverse (Règle 3)")
    — remplace l'ancien format verbeux "GDC #X (date) : <motif complet>"
    dans le rapport d'exclusion (demande de Flo, 16/08/2026 : "plus compact,
    plus lisible"). `week` doit avoir été enrichie par _compute_weekly_statuses()
    (champ "rule"). Repli sur le motif complet si `rule` est absent (ne
    devrait pas arriver pour une semaine warning/grace)."""
    gdc = f"GDC #{week['seasonId']}"
    rule = week.get("rule")
    if rule == 3:
        return f"{gdc} - {week['boats']} attaque(s) de bateau adverse (Règle {rule})"
    if rule is not None:
        return f"{gdc} - {week['decks']}/{FULL_DECKS} decks joués (Règle {rule})"
    return f"{gdc} - {week.get('motif', '')}"


def _compute_weekly_statuses(weeks: list[dict], manual_seasons: set[str]) -> list[dict]:
    """
    Enrichit chaque semaine (chronologique) d'un statut, en UN SEUL passage
    séquentiel sur TOUT l'historique du joueur (pas seulement les 10
    dernières GDC affichées) — 2 régimes (refonte du 18/08/2026 avec Flo,
    voir docstring du module) :

    - Régime STRICT (par défaut, tant que le joueur n'a jamais eu
      GRADUATION_STREAK GDC consécutives complètes) : toute GDC incomplète
      hors semaine d'arrivée = avertissement direct (Règle 2).
    - Régime ASSOUPLI (définitif, dès qu'un streak de GRADUATION_STREAK GDC
      consécutives complètes a été atteint une fois) : 1ère GDC incomplète
      de la fenêtre glissante des NB_GDC dernières GDC = grâce automatique,
      les suivantes = avertissement (Règle 4).

    `consecutive_complete` compte les GDC consécutives réellement complètes
    (decks pleins ET pas de bateau) depuis le début de l'historique — remis à
    zéro par toute GDC incomplète OU toute attaque de bateau. Dès qu'il
    atteint GRADUATION_STREAK, `graduated` passe à True à VIE (le joueur ne
    repasse jamais en régime strict, même si `consecutive_complete` retombe
    ensuite à zéro) et `graduation_index` retient l'index de cette semaine
    (utilisé pour exclure les GDC d'AVANT la graduation des candidates à la
    grâce de la Règle 4 — une GDC incomplète jugée sous le régime strict ne
    doit pas "consommer" la grâce disponible une fois le joueur assoupli).
    """
    out = []
    consecutive_complete = 0
    graduated = False
    graduation_index: int | None = None

    for idx, week in enumerate(weeks):
        is_manual = str(week["seasonId"]) in manual_seasons

        if week["is_join_week"]:
            out.append({
                **week, "status": "exempt",
                "motif": "1ère GDC du joueur dans le clan — toujours exemptée (Règle 1).",
                "manual": False, "rule": 1,
            })
            continue

        decks = week["decks"]
        boats = week["boats"]
        clean = boats == 0 and decks >= FULL_DECKS

        if boats > 0:
            base, motif, rule = "warning", f"{boats} attaque(s) de bateau adverse (Règle 3)", 3
            consecutive_complete = 0
        elif clean:
            base, motif, rule = "ok", "", None
            consecutive_complete += 1
            if not graduated and consecutive_complete >= GRADUATION_STREAK:
                graduated = True
                graduation_index = idx
        else:
            consecutive_complete = 0
            if not graduated:
                base, motif, rule = "warning", (
                    f"{decks}/{FULL_DECKS} decks joués — régime strict, pas encore "
                    f"{GRADUATION_STREAK} GDC complètes d'affilée (Règle 2)"
                ), 2
            else:
                window = list(enumerate(weeks))[max(0, idx - NB_GDC + 1): idx + 1]
                candidates = [
                    w for w_idx, w in window
                    if w_idx >= graduation_index and not w["is_join_week"]
                    and w["boats"] == 0 and w["decks"] < FULL_DECKS
                ]
                if candidates and candidates[0]["week_key"] == week["week_key"]:
                    base, motif, rule = "grace", (
                        f"{decks}/{FULL_DECKS} decks joués — 1ère GDC incomplète de la fenêtre (Règle 4)"
                    ), 4
                else:
                    base, motif, rule = "warning", (
                        f"{decks}/{FULL_DECKS} decks joués — GDC incomplète supplémentaire de la fenêtre (Règle 4)"
                    ), 4

        if is_manual and base == "warning":
            status, final_motif, manual = "grace", f"Grâce manuelle accordée par un chef (motif initial : {motif})", True
        else:
            status, final_motif, manual = base, motif, False

        out.append({**week, "status": status, "motif": final_motif, "manual": manual, "rule": rule})

    return out


def _player_report(weekly: list[dict]) -> dict:
    """
    Rapport "actuel" d'un joueur à partir de son historique de statuts
    hebdomadaires déjà calculé (voir _compute_weekly_statuses) : compte les
    grâces/avertissements sur les NB_GDC dernières semaines glissantes et
    détermine le "bucket" final (excl/warn/grace/None).

    Depuis la refonte du 18/08/2026 il n'y a plus de statut 'excl_direct' au
    niveau d'une semaine (voir docstring du module) — le bucket "excl" ne
    peut désormais venir que de l'accumulation de WARN_TO_EXCL_THRESHOLD
    avertissements actifs. `excl_weeks` reste dans l'entrée renvoyée (toujours
    vide) uniquement pour ne pas casser l'affichage existant (views/suivi.py).
    """
    trailing = weekly[-NB_GDC:]
    warning_weeks = [w for w in trailing if w["status"] == "warning"]
    grace_weeks = [w for w in trailing if w["status"] == "grace"]

    grace_raw = len(grace_weeks)
    converted_from_grace = grace_raw // GRACE_TO_WARN_RATIO
    grace_count = grace_raw % GRACE_TO_WARN_RATIO
    warning_count = len(warning_weeks) + converted_from_grace

    if warning_count >= WARN_TO_EXCL_THRESHOLD:
        bucket = "excl"
        reason_excl = f"{warning_count} avertissement(s) actifs sur les {NB_GDC} dernières GDC"
    elif warning_count > 0:
        bucket = "warn"
        reason_excl = None
    elif grace_count > 0:
        bucket = "grace"
        reason_excl = None
    else:
        bucket = None
        reason_excl = None

    return {
        "bucket": bucket,
        "reason_excl": reason_excl,
        "excl_weeks": [],
        "warning_count": warning_count,
        "warning_weeks": warning_weeks,
        "converted_from_grace": converted_from_grace,
        "grace_count": grace_count,
        "grace_weeks": grace_weeks,
    }


def build_exclusion_report(
    full_history: list[dict],
    clan_tag: str,
    manual_graces: set[tuple[str, str]] | None = None,
    current_tags: set[str] | None = None,
) -> dict:
    """
    Rapport complet {"excl": {tag: entry}, "warn": {...}, "grace": {...}}.

    `full_history` doit être l'historique le plus complet disponible (archive
    + live, voir history.get_full_history()) — PAS limité à 10 GDC : il faut
    toute la chronologie pour savoir si le joueur a déjà atteint son streak de
    graduation (Règle 2/4) et faire glisser correctement les compteurs
    (Règles 5/6), même si seules les 10 dernières semaines de chaque joueur
    comptent pour le rapport final.

    `current_tags` : si fourni, seuls ces joueurs (membres actuels du clan)
    apparaissent dans le rapport — un joueur exclu/parti ne doit plus y figurer.
    """
    manual_graces = manual_graces or set()
    per_player = _all_players_weeks(full_history, clan_tag)

    excl, warn, grace = {}, {}, {}
    for tag, weeks in per_player.items():
        if current_tags is not None and tag not in current_tags:
            continue
        manual_seasons = {season_id for (t, season_id) in manual_graces if t == tag}
        weekly = _compute_weekly_statuses(weeks, manual_seasons)
        report = _player_report(weekly)
        if report["bucket"] is None:
            continue
        entry = {"tag": tag, "name": weeks[-1]["name"], "tenure": weeks[-1]["tenure"], **report}
        if report["bucket"] == "excl":
            excl[tag] = entry
        elif report["bucket"] == "warn":
            warn[tag] = entry
        elif report["bucket"] == "grace":
            grace[tag] = entry

    return {"excl": excl, "warn": warn, "grace": grace}


def player_recent_report(
    full_history: list[dict],
    clan_tag: str,
    player_tag: str,
    manual_graces: set[tuple[str, str]] | None = None,
) -> dict | None:
    """
    Comme build_exclusion_report, mais pour UN SEUL joueur (utilisé par "Mon
    profil" pour que chacun voie ses propres avertissements/grâces en cours).
    Renvoie None si le joueur n'apparaît dans aucune GDC de l'historique.
    """
    manual_graces = manual_graces or set()
    tag = _norm(player_tag)
    per_player = _all_players_weeks(full_history, clan_tag)
    weeks = per_player.get(tag)
    if not weeks:
        return None
    manual_seasons = {season_id for (t, season_id) in manual_graces if t == tag}
    weekly = _compute_weekly_statuses(weeks, manual_seasons)
    report = _player_report(weekly)
    return {"tag": tag, "name": weeks[-1]["name"], "tenure": weeks[-1]["tenure"], **report}
