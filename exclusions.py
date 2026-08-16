"""
exclusions.py — moteur de détection des exclusions/avertissements/grâces et
des tiers "Avengers".

Règles de détection (redéfinies avec Flo le 15/08/2026 soir, remplacent
entièrement l'ancienne logique portée du bot Discord — voir git history si
besoin de retrouver l'ancienne version) :

- Règle 1 : la toute première GDC visible d'un joueur dans le clan (semaine
  d'arrivée) n'est JAMAIS prise en compte, quel que soit son contenu — ni
  complète, ni incomplète, ni bateau. Limitation connue et acceptée avec Flo :
  l'API Supercell ne donne que le total de decks joués par semaine pour
  l'historique passé (pas de détail jour par jour), donc on ne peut pas
  distinguer "avant l'arrivée" de "après l'arrivée" à l'intérieur de cette
  1ère semaine — on l'exempte donc entièrement plutôt que de pénaliser à tort.
- Règle 2 : joueur avec 5 GDC ou moins d'ancienneté dans le clan (ancienneté
  = nombre total de GDC où le joueur apparaît dans l'historique, la semaine
  d'arrivée comptant comme 1) → doit jouer tous ses decks. Un manquement =
  exclusion directe (pas de grâce, pas d'avertissement).
- Règle 3 : ancienneté entre 6 et 10 GDC → chaque GDC incomplète (dans la
  fenêtre des 10 dernières GDC glissantes) = 1 avertissement.
- Règle 4 : ancienneté strictement supérieure à 10 GDC → dans la fenêtre des
  10 dernières GDC glissantes, la 1ère GDC incomplète = grâce automatique,
  chaque GDC incomplète suivante = 1 avertissement.
- Règle 5 : 3 grâces cumulées (sur la fenêtre glissante de 10 GDC) = 1
  avertissement généré (par tranche complète de 3 — la grâce affichée reste
  donc toujours entre 0 et 2).
- Règle 6 : tout se calcule sur une fenêtre glissante de 10 GDC — un
  événement (grâce/avertissement) sort naturellement du compte une fois que
  la GDC qui l'a généré a plus de 10 semaines. Chaque semaine ne compte
  qu'une seule fois (pas de recomptage en glissant).
- Règle 7 : toute attaque de bateau adverse dans la fenêtre des 10 dernières
  GDC glissantes = exclusion directe.
- 3 avertissements actifs (cumulés, jamais remis à zéro tant qu'ils sont
  dans la fenêtre de 10 GDC) → le joueur PASSE dans la liste des exclusions
  recommandées (et sort de la liste des avertissements) ; si le nombre
  d'avertissements actifs redescend sous 3 (glissement de fenêtre), il
  revient automatiquement dans les avertissements. Rien n'est mémorisé nulle
  part : tout est recalculé à chaque affichage depuis l'historique archivé
  (voir history.py) — pas de journal séparé qui pourrait diverger.
- Grâce manuelle (bouton "grâcier" d'un chef, voir storage.get_manual_graces) :
  transforme la semaine concernée en "grâce" (peu importe son statut de base),
  cette grâce participe ensuite normalement au comptage glissant (Règle 5).

Seuls les joueurs actuellement dans le clan sont retenus dans les rapports
(voir le paramètre `current_tags` de build_exclusion_report) — un joueur
exclu/parti ne doit plus apparaître.
"""

from __future__ import annotations

NB_GDC = 10  # fenêtre glissante d'analyse (Règles 3/4/5/6/7)
TENURE_DIRECT_MAX = 5  # ancienneté max pour la Règle 2 (exclusion directe)
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

    main.sort(key=lambda s: s["ranking_score"], reverse=True)
    shield.sort(key=lambda s: s["ranking_score"], reverse=True)
    multi.sort(key=lambda s: s["gdc_count"] * 10000 + s["ranking_score"], reverse=True)

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
    personne (le rang suit le même critère — ranking_score — que les sections).
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
# Règles d'exclusion — Règles 1 à 7 (voir docstring du module)
# ---------------------------------------------------------------------------


def rules_summary_markdown() -> str:
    """
    Résumé court (liste à puces) du règlement des exclusions (Règles 1 à 7 —
    voir docstring du module pour le détail complet), affiché aux joueurs sur
    "Mon profil" (à côté de "Points à surveiller") et aux chefs sur "Suivi
    clan" > "Exclusions" (tout en haut, avant les rapports) — demande de Flo,
    16/08/2026 soir. Généré à partir des constantes du module ci-dessus pour
    ne jamais diverger des vraies règles appliquées par le moteur.
    """
    return (
        "- **1ère GDC dans le clan** : toujours exemptée, quel que soit son contenu.\n"
        f"- **Ancienneté actuelle ≤ {TENURE_DIRECT_MAX} GDC** : un deck manquant sur une GDC = "
        "exclusion directe (pas de grâce, pas d'avertissement).\n"
        f"- **Ancienneté actuelle entre {TENURE_DIRECT_MAX + 1} et {NB_GDC - 1} GDC** : chaque GDC "
        f"incomplète (sur les {NB_GDC} dernières) = 1 avertissement.\n"
        f"- **Ancienneté actuelle ≥ {NB_GDC} GDC** : sur les {NB_GDC} dernières GDC, la 1ère incomplète "
        "= grâce automatique, chaque suivante = 1 avertissement.\n"
        f"- **{GRACE_TO_WARN_RATIO} grâces cumulées** (fenêtre glissante) = 1 avertissement supplémentaire généré.\n"
        "- **Attaque de bateau adverse** = exclusion directe, quelle que soit l'ancienneté "
        "(sauf en semaine d'arrivée).\n"
        f"- **{WARN_TO_EXCL_THRESHOLD} avertissements actifs** (sur les {NB_GDC} dernières GDC) = "
        "recommandation d'exclusion.\n"
        f"- Tout se calcule sur une fenêtre glissante des {NB_GDC} dernières GDC — un manquement ancien "
        "sort automatiquement du compte au fil des semaines.\n"
        "- L'ancienneté prise en compte est **toujours celle d'aujourd'hui**, pas celle que le joueur "
        "avait à l'époque de chaque semaine passée."
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


def _week_status(week: dict, window: list[dict], is_manual: bool, current_tenure: int) -> tuple[str, str, bool]:
    """
    Statut d'UNE semaine — voir _compute_weekly_statuses().

    `window` = les <=10 semaines du joueur se terminant à `week` INCLUSE
    (dans l'ordre chronologique), utilisé uniquement pour la Règle 4.

    `current_tenure` = ancienneté ACTUELLE du joueur (celle d'AUJOURD'HUI,
    pas celle qu'il avait au moment de `week`) — demande explicite de Flo,
    16/08/2026 soir : "je voudrais que l'ancienneté prise en compte soit
    l'ancienneté ACTUELLE". Avant ce changement, chaque semaine était jugée
    selon l'ancienneté du joueur À CETTE ÉPOQUE (`week["tenure"]`) — un
    manquement commis quand le joueur était encore nouveau restait
    définitivement marqué "Règle 2" (exclusion directe, sans grâce) même des
    mois plus tard une fois le joueur devenu vétéran, tant que cette semaine
    restait dans la fenêtre glissante de 10 GDC (Règle 6). Désormais, TOUTES
    les semaines de la fenêtre sont rejugées avec l'ancienneté DU JOUR : un
    vétéran (>=10 GDC aujourd'hui) voit ses vieux manquements traités par la
    Règle 4 (grâce/avertissement), pas par la Règle 2/3, même s'ils dataient
    d'une époque où il avait moins de GDC d'ancienneté. Seule la Règle 1
    (semaine d'arrivée exemptée) reste basée sur l'ancienneté DE L'ÉPOQUE
    (`week["is_join_week"]`, `week["tenure"] == 1`) — c'est un fait structurel
    (quelle semaine était la toute première), pas une question de sévérité
    qui doit s'assouplir avec le temps.

    Renvoie (status, motif, manual) — status parmi :
    'exempt' / 'ok' / 'grace' / 'warning' / 'excl_direct'.
    """
    if week["is_join_week"]:
        return "exempt", "1ère GDC du joueur dans le clan — toujours exemptée (Règle 1).", False

    decks = week["decks"]
    boats = week["boats"]
    complete = decks >= FULL_DECKS

    if boats > 0:
        base, motif = "excl_direct", f"{boats} attaque(s) de bateau adverse (Règle 7)"
    elif complete:
        base, motif = "ok", ""
    elif current_tenure <= TENURE_DIRECT_MAX:
        base, motif = "excl_direct", (
            f"{decks}/{FULL_DECKS} decks joués, {current_tenure} GDC d'ancienneté actuelle "
            f"(≤{TENURE_DIRECT_MAX} — Règle 2)"
        )
    elif current_tenure < NB_GDC:
        base, motif = "warning", (
            f"{decks}/{FULL_DECKS} decks joués, {current_tenure} GDC d'ancienneté actuelle (Règle 3)"
        )
    else:
        # Règle 4 : parmi les semaines de la fenêtre relevant elles aussi de la
        # Règle 4 (incomplètes, sans bateau, hors semaine d'arrivée — les
        # semaines "bateau" ont déjà leur propre statut indépendant, elles ne
        # concourent pas pour la grâce), la 1ère chronologiquement = grâce,
        # les suivantes = avertissement. Plus de filtre sur l'ancienneté ICI
        # (`w["tenure"] >= NB_GDC`) : on est déjà dans la branche "Règle 4"
        # parce que `current_tenure >= NB_GDC`, et cette ancienneté actuelle
        # est désormais la même pour toutes les semaines du joueur — donc
        # toute semaine incomplète/sans-bateau/hors-arrivée du joueur est un
        # candidat valable, quelle que soit l'ancienneté qu'il avait CE
        # jour-là.
        candidates = [
            w for w in window
            if not w["is_join_week"] and w["boats"] == 0 and w["decks"] < FULL_DECKS
        ]
        if candidates and candidates[0]["week_key"] == week["week_key"]:
            base, motif = "grace", f"{decks}/{FULL_DECKS} decks joués — 1ère GDC incomplète de la fenêtre (Règle 4)"
        else:
            base, motif = "warning", f"{decks}/{FULL_DECKS} decks joués — GDC incomplète supplémentaire (Règle 4)"

    if is_manual and base in ("excl_direct", "warning"):
        return "grace", f"Grâce manuelle accordée par un chef (motif initial : {motif})", True

    return base, motif, False


def _compute_weekly_statuses(weeks: list[dict], manual_seasons: set[str]) -> list[dict]:
    """Enrichit chaque semaine (chronologique) d'un statut — voir _week_status().

    `current_tenure` = ancienneté du joueur à sa semaine la PLUS RÉCENTE
    (`weeks[-1]`) — c'est cette ancienneté "d'aujourd'hui" qui sert désormais
    de référence pour TOUTES les semaines de la fenêtre glissante (voir le
    docstring de _week_status pour le détail de ce changement, 16/08/2026).
    """
    current_tenure = weeks[-1]["tenure"] if weeks else 0
    out = []
    for idx, week in enumerate(weeks):
        window = weeks[max(0, idx - NB_GDC + 1) : idx + 1]
        is_manual = str(week["seasonId"]) in manual_seasons
        status, motif, manual = _week_status(week, window, is_manual, current_tenure)
        out.append({**week, "status": status, "motif": motif, "manual": manual})
    return out


def _player_report(weekly: list[dict]) -> dict:
    """
    Rapport "actuel" d'un joueur à partir de son historique de statuts
    hebdomadaires déjà calculé (voir _compute_weekly_statuses) : compte les
    grâces/avertissements/exclusions directes sur les NB_GDC dernières
    semaines glissantes et détermine le "bucket" final (excl/warn/grace/None).
    """
    trailing = weekly[-NB_GDC:]
    excl_weeks = [w for w in trailing if w["status"] == "excl_direct"]
    warning_weeks = [w for w in trailing if w["status"] == "warning"]
    grace_weeks = [w for w in trailing if w["status"] == "grace"]

    grace_raw = len(grace_weeks)
    converted_from_grace = grace_raw // GRACE_TO_WARN_RATIO
    grace_count = grace_raw % GRACE_TO_WARN_RATIO
    warning_count = len(warning_weeks) + converted_from_grace

    if excl_weeks or warning_count >= WARN_TO_EXCL_THRESHOLD:
        bucket = "excl"
        reasons = [f"GDC #{w['seasonId']} : {w['motif']}" for w in excl_weeks]
        if warning_count >= WARN_TO_EXCL_THRESHOLD:
            reasons.append(f"{warning_count} avertissement(s) actifs sur les {NB_GDC} dernières GDC")
        reason_excl = " ; ".join(reasons)
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
        "excl_weeks": excl_weeks,
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
    tout l'historique pour calculer l'ancienneté réelle (Règles 2/3/4) et
    faire glisser correctement les compteurs (Règles 5/6), même si seules les
    10 dernières semaines de chaque joueur comptent pour le rapport final.

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
