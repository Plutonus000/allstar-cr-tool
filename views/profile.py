"""views/profile.py — "Mon profil" : progression et santé de participation (tous les joueurs)."""

from __future__ import annotations

import streamlit as st

import auth
import clash_api as api
import data
import exclusions
import fmt
import history as gdc_history
import logic
import progression
import storage

ROLE_LABELS = {
    "member": "Membre",
    "elder": "Aîné",
    "coLeader": "Chef adjoint",
    "leader": "Chef",
}

_TIMELINE_GREEN = "#16a34a"
_TIMELINE_GREEN_LIGHT = "#22c55e"
_TIMELINE_GREEN_BG = "#dcfce7"
_TIMELINE_GRAY = "#d1d5db"
_TIMELINE_GRAY_BG = "#f3f4f6"
_TIMELINE_GRAY_TEXT = "#6b7280"
_TIMELINE_DARK_TEXT = "#16213e"

_STATUS_ICONS = {"Membre": "👤", "Aîné": "⭐", "Chef adjoint": "🛡️"}


def _timeline_node(reached: bool, label: str) -> str:
    bg = _TIMELINE_GREEN_LIGHT if reached else "#ffffff"
    border = _TIMELINE_GREEN if reached else _TIMELINE_GRAY
    text_color = "#ffffff" if reached else _TIMELINE_GRAY_TEXT
    mark = "✓" if reached else _STATUS_ICONS.get(label, "")
    return (
        f'<div class="allstar-tl-node" style="width:46px;height:46px;border-radius:50%;background:{bg};'
        f'border:3px solid {border};display:flex;align-items:center;justify-content:center;'
        f'font-size:20px;font-weight:700;color:{text_color};margin:0 auto;'
        f'box-shadow:0 2px 6px rgba(0,0,0,0.10);">{mark}</div>'
    )


def _timeline_bar(pct: float) -> str:
    """Barre de progression épaissie et graduée (ticks à 20/40/60/80%) —
    look plus "pro" demandé par Flo (15/08/2026 soir)."""
    pct = max(0, min(100, pct))
    ticks = "".join(
        f'<div style="position:absolute;left:{t}%;top:0;bottom:0;width:2px;'
        f'background:rgba(255,255,255,0.65);z-index:1;"></div>'
        for t in (20, 40, 60, 80)
    )
    return (
        '<div style="position:relative;height:14px;border-radius:7px;background:#e5e7eb;'
        'margin-top:20px;overflow:hidden;box-shadow:inset 0 1px 2px rgba(0,0,0,0.06);">'
        f'<div style="position:relative;height:100%;width:{pct:.0f}%;border-radius:7px;'
        f'background:linear-gradient(90deg,{_TIMELINE_GREEN_LIGHT},{_TIMELINE_GREEN});'
        'transition:width .3s;z-index:0;"></div>'
        f'{ticks}'
        '</div>'
    )


def _status_badge(label: str, reached: bool) -> str:
    icon = _STATUS_ICONS.get(label, "")
    bg = _TIMELINE_GREEN_BG if reached else _TIMELINE_GRAY_BG
    border = _TIMELINE_GREEN if reached else _TIMELINE_GRAY
    color = "#166534" if reached else _TIMELINE_DARK_TEXT
    return (
        f'<div class="allstar-tl-badge" style="display:inline-block;padding:7px 16px;border-radius:10px;background:{bg};'
        f'border:1.5px solid {border};font-size:16px;font-weight:700;color:{color};'
        f'white-space:nowrap;">{icon} {label}</div>'
    )


def _render_progress_timeline(streak: int, role: str) -> None:
    """
    Frise Membre -> Aîné -> Chef adjoint : chaque segment (5 semaines) se remplit en
    vert au prorata de la série d'assiduité actuelle (voir progression.py), le
    reste en gris. Les deux segments ensemble représentent la même série
    continue de 10 semaines requise pour Chef adjoint (COLEADER_WEEKS_REQUIRED) —
    le second segment couvre les semaines 6 à 10. Look "encadré" avec icônes
    par statut, ligne épaisse et graduée (demande de Flo, 15/08/2026 soir).
    """
    if role in ("coLeader", "leader"):
        seg1_done, seg1_pct = progression.ELDER_WEEKS_REQUIRED, 100.0
        seg2_target = progression.COLEADER_WEEKS_REQUIRED - progression.ELDER_WEEKS_REQUIRED
        seg2_done, seg2_pct = seg2_target, 100.0
    else:
        seg1_done = min(streak, progression.ELDER_WEEKS_REQUIRED)
        seg1_pct = seg1_done / progression.ELDER_WEEKS_REQUIRED * 100
        seg2_target = progression.COLEADER_WEEKS_REQUIRED - progression.ELDER_WEEKS_REQUIRED
        seg2_done = max(0, min(streak - progression.ELDER_WEEKS_REQUIRED, seg2_target))
        seg2_pct = (seg2_done / seg2_target * 100) if seg2_target else 100.0

    node2_reached = seg1_pct >= 100
    node3_reached = seg2_pct >= 100

    seg1_text = f"✅ {seg1_done}/{progression.ELDER_WEEKS_REQUIRED} GDC complétées à 100%" if node2_reached else (
        f"{seg1_done}/{progression.ELDER_WEEKS_REQUIRED} GDC complétées à 100%"
    )
    seg2_text = f"✅ {seg2_done}/{seg2_target} GDC complétées à 100%" if node3_reached else (
        f"{seg2_done}/{seg2_target} GDC complétées à 100%"
    )

    cols = "10% 35% 10% 35% 10%"
    # Media query mobile (16/08/2026 soir, demande de Flo : "sur mobile, la
    # frise est trop grande") : rétrécit cercles/badges/textes sous 480px de
    # large. Les valeurs de base ci-dessus (desktop) restent en style inline ;
    # `!important` est nécessaire ici pour que la media query l'emporte sur
    # ces styles inline.
    style_block = """
    <style>
    @media (max-width: 480px) {
        .allstar-tl-wrap { padding: 12px 8px 10px 8px !important; }
        .allstar-tl-node { width: 30px !important; height: 30px !important; font-size: 13px !important; border-width: 2px !important; }
        .allstar-tl-badge { padding: 4px 8px !important; font-size: 11px !important; border-radius: 8px !important; }
        .allstar-tl-seg-text { font-size: 10px !important; }
    }
    </style>
    """
    html = f"""
    {style_block}
    <div class="allstar-tl-wrap" style="margin-top:10px;padding:20px 16px 16px 16px;border-radius:14px;
                background:#fafbfc;border:1px solid #e6eaf0;">
      <div style="display:grid;grid-template-columns:{cols};align-items:center;">
        <div>{_timeline_node(True, "Membre")}</div>
        <div>{_timeline_bar(seg1_pct)}</div>
        <div>{_timeline_node(node2_reached, "Aîné")}</div>
        <div>{_timeline_bar(seg2_pct)}</div>
        <div>{_timeline_node(node3_reached, "Chef adjoint")}</div>
      </div>
      <div style="display:grid;grid-template-columns:{cols};margin-top:10px;">
        <div></div>
        <div class="allstar-tl-seg-text" style="text-align:center;font-size:13px;font-weight:600;color:#5b6472;">{seg1_text}</div>
        <div></div>
        <div class="allstar-tl-seg-text" style="text-align:center;font-size:13px;font-weight:600;color:#5b6472;">{seg2_text}</div>
        <div></div>
      </div>
      <div style="display:grid;grid-template-columns:{cols};margin-top:14px;align-items:center;">
        <div style="text-align:center;">{_status_badge("Membre", True)}</div>
        <div></div>
        <div style="text-align:center;">{_status_badge("Aîné", node2_reached)}</div>
        <div></div>
        <div style="text-align:center;">{_status_badge("Chef adjoint", node3_reached)}</div>
      </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)


def _render_warnings_graces_section(
    full_history: list[dict], clan_tag: str, player_tag: str, is_self: bool = True, display_name: str = ""
) -> None:
    """Avertissements et grâces en cours du joueur sur les 10 dernières GDC
    glissantes (voir exclusions.py) — demande de Flo, 15/08/2026 soir : chaque
    joueur doit pouvoir voir sa propre situation, avec le détail. Réutilisée
    aussi par "🔍 Suivi joueur" (is_self=False, voir views/player_watch.py)."""
    manual_graces_raw = storage.get_manual_graces()
    manual_graces = exclusions.manual_grace_keys(manual_graces_raw)
    report = exclusions.player_recent_report(full_history, clan_tag, player_tag, manual_graces)

    st.markdown("---")
    st.markdown("**⚠️ Avertissements et grâces (10 dernières GDC)**")

    if report is None or (report["warning_count"] == 0 and report["grace_count"] == 0):
        st.success(
            "✅ Aucun avertissement ni grâce sur les 10 dernières GDC." if is_self
            else f"✅ Aucun avertissement ni grâce pour {display_name} sur les 10 dernières GDC."
        )
        return

    if report["bucket"] == "excl":
        if is_self:
            st.warning(
                "Une recommandation d'exclusion est actuellement active sur ton profil "
                f"({report['reason_excl']}) — parles-en à un chef si tu as des questions."
            )
        else:
            st.warning(
                f"Une recommandation d'exclusion est actuellement active pour {display_name} "
                f"({report['reason_excl']})."
            )

    col_warn, col_grace = st.columns(2)
    with col_warn:
        st.metric("Avertissements actifs", report["warning_count"])
        # Format compact "GDC #X - Y/16 decks joués (Règle N)" — même format
        # que le rapport d'exclusion chefs (voir views/suivi.py), demande de
        # Flo, 16/08/2026 ("plus compact, plus lisible").
        for w in report["warning_weeks"]:
            st.caption(exclusions.format_week_line(w))
        if report.get("converted_from_grace"):
            st.caption(f"+ {report['converted_from_grace']} issu(s) de la conversion de grâces (3 grâces = 1 avertissement).")
    with col_grace:
        st.metric("Grâces actives", report["grace_count"])
        for w in report["grace_weeks"]:
            origin = "manuelle" if w["manual"] else "automatique"
            st.caption(f"{exclusions.format_week_line(w)} — grâce {origin}")
            if w["manual"]:
                match = next(
                    (
                        g for g in manual_graces_raw
                        if logic.norm_tag(g.get("player_tag", "")) == logic.norm_tag(player_tag)
                        and str(g.get("season_id", "")) == str(w["seasonId"])
                    ),
                    None,
                )
                if match and match.get("comment"):
                    st.caption(f"↳ « {match['comment']} » — {match.get('granted_by', '?')}")


def render(ctx: dict, viewed_player: dict | None = None) -> None:
    """
    `viewed_player` (optionnel) = {"player_tag", "display_name", "role"} d'un
    AUTRE joueur que la personne connectée — utilisé par l'onglet "🔍 Suivi
    joueur" (chefs uniquement, voir views/player_watch.py) pour afficher la
    même page que "Mon profil" mais pour n'importe quel membre du clan
    sélectionné, sans dupliquer toute cette logique. Si omis (cas normal de
    "Mon profil"), on affiche le profil de la personne connectée elle-même.
    """
    clan_tag = ctx["clan_tag"]
    is_self = viewed_player is None
    if is_self:
        player_tag = ctx["player_tag"]
        role = ctx["role"]
        display_name = ctx["display_name"]
    else:
        player_tag = viewed_player["player_tag"]
        role = viewed_player["role"]
        display_name = viewed_player["display_name"]

    st.subheader("🏠 Mon profil" if is_self else f"🔍 Profil de {display_name}")
    st.markdown(f"**{display_name}** — {ROLE_LABELS.get(role, role or '?')}")

    # ⚠️ limit=10 ici (pas plus) — corrigé le 16/08/2026 soir (bug signalé par
    # Flo : ancienneté à 4 GDC dans Exclusions alors que "Mon profil" montrait
    # bien 10 GDC). Cette page demandait auparavant `limit=52` en espérant que
    # l'API renvoie plus que 10 semaines si elle en avait plus (elle ne le
    # fait JAMAIS, voir history.py) — mais `data.load_race_log` est mis en
    # cache PAR VALEUR de `limit` (st.cache_data), donc `limit=52` ici et
    # `limit=10` utilisé par toutes les autres pages (Suivi clan, Classement,
    # Statistiques...) créaient DEUX entrées de cache indépendantes, pouvant
    # légitimement contenir des données différentes selon le moment où chacune
    # a été peuplée/rafraîchie — d'où l'incohérence "10 ici, 4 là-bas" alors
    # qu'il s'agit du même historique réel. Toutes les pages utilisent
    # maintenant la même limite pour partager la même entrée de cache.
    try:
        race_log = data.load_race_log(clan_tag, limit=10)
    except api.ClashAPIError as exc:
        st.error(str(exc))
        return

    streak, history = progression.compute_participation_streak(race_log, player_tag, clan_tag)
    status = progression.eligibility_status(streak)
    rate = progression.participation_rate(race_log, player_tag, clan_tag, n_races=10)

    # Archive au fil de l'eau (voir history.py) : dès qu'une GDC de race_log
    # n'est pas encore archivée, elle l'est ici. Une seule vérification par
    # session (pas à chaque interaction sur la page).
    gdc_history.sync_archive(race_log, clan_tag)
    full_history = gdc_history.get_full_history(clan_tag, race_log)
    this_year = gdc_history.current_year()
    rate_year = gdc_history.participation_rate_for_year(full_history, player_tag, clan_tag, this_year)
    rate_all_time = gdc_history.participation_rate_all_time(full_history, player_tag, clan_tag)

    # Position dans le classement du clan — mêmes 10 dernières GDC et même
    # critère que l'onglet "Classement" (voir exclusions.ranked_list()), pour
    # que le rang affiché ici ne diverge jamais de celui du tableau Classement.
    profile_stats = exclusions.compute_player_stats(race_log[: min(10, len(race_log)) or 1], clan_tag)
    try:
        current_tags = {logic.norm_tag(m.get("tag", "")) for m in data.load_clan_members(clan_tag)}
        profile_stats = {tag: s for tag, s in profile_stats.items() if tag in current_tags}
    except api.ClashAPIError:
        pass
    ranked = exclusions.ranked_list(profile_stats)
    ranked_total = len(ranked)
    my_rank = next((p["rang"] for p in ranked if p["tag"] == logic.norm_tag(player_tag)), None)

    poss = "ton" if is_self else "son"  # "ton taux" / "son taux" — accord approximatif, suffisant ici

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Série actuelle (100% assiduité)", f"{streak} semaine(s)",
        help=f"Nombre de GDC consécutives (en partant de la plus récente) où {'tu as' if is_self else display_name + ' a'} joué "
        f"{'tes' if is_self else 'ses'} 16 decks. Une seule GDC incomplète ou une absence remet le compteur à zéro.",
    )
    col2.metric(
        "Taux de participation (10 dernières GDC)", f"{rate}%" if rate is not None else "—",
        help="Total des decks joués divisé par le total de decks possibles (16 × nombre de GDC jouées), "
        "sur les 10 dernières GDC disponibles via l'API.",
    )
    col3.metric(
        "Rôle actuel", ROLE_LABELS.get(role, role or "?"),
        help=f"{'Ton' if is_self else poss.capitalize()} rôle actuel dans le clan, en jeu.",
    )

    col4, col5, col6 = st.columns(3)
    col4.metric(
        "Position au classement", f"#{my_rank} / {ranked_total}" if my_rank else "—",
        help=f"{'Ton' if is_self else poss.capitalize()} rang dans le classement du clan (onglet Classement), basé sur "
        "les Trophées et l'assiduité des 10 dernières GDC.",
    )
    col5.metric(
        f"Taux de participation ({this_year})", f"{rate_year}%" if rate_year is not None else "—",
        help="Comme le taux 10 GDC, mais sur toute l'année civile en cours — basé sur l'historique "
        "archivé par l'outil (voir note ci-dessous).",
    )
    col6.metric(
        "Taux de participation (all-time)", f"{rate_all_time}%" if rate_all_time is not None else "—",
        help="Comme ci-dessus, mais sur tout l'historique archivé par l'outil depuis sa mise en place.",
    )
    st.caption(
        "« Année en cours » et « all-time » se basent sur l'historique archivé par l'outil "
        "au fil du temps (l'API officielle ne conserve que 10 semaines) — plus l'outil est "
        "utilisé longtemps, plus ces deux chiffres deviennent complets."
    )

    # "Membre depuis" (approximatif, basé sur l'archive — pas une vraie date d'entrée
    # dans le clan, l'API ne l'expose pas) + "Cartes maxées" (cartes distinctes maxées
    # sur les 4 decks du dernier jour de GDC complet connu, best-effort via /battlelog,
    # voir logic.compute_maxed_cards_in_war_deck) — ajoutés le 16/08/2026 (demande de Flo).
    since_date = logic.member_since(full_history, player_tag, clan_tag)
    try:
        battlelog = data.load_player_battlelog(player_tag)
        maxed_result = logic.compute_maxed_cards_in_war_deck(battlelog, player_tag)
    except api.ClashAPIError:
        maxed_result = None

    col7, col8 = st.columns(2)
    col7.metric(
        "Membre depuis", fmt.format_date(since_date) if since_date else "—",
        help="Première semaine de GDC archivée par l'outil où l'on retrouve trace du joueur dans le "
        "clan — pas la vraie date d'arrivée (l'API ne l'expose pas). Note : l'archive de l'outil "
        f"ne remonte pas avant sa mise en place — voir la note ci-dessus sur « all-time ».",
    )
    col8.metric(
        "Cartes maxées (deck de GDC)",
        f"{maxed_result['maxed']}/{maxed_result['total']}" if maxed_result else "—",
        help="Nombre de cartes distinctes au niveau max parmi celles utilisées sur les 4 decks du "
        f"dernier jour de GDC complet connu {'de ce joueur' if not is_self else 'joué'} — donnée "
        "instantanée, best-effort (fenêtre de rétention limitée côté API, voir "
        "clash_api.get_player_battlelog).",
    )
    if maxed_result and maxed_result.get("partial_day"):
        st.caption(
            f"⚠️ Seulement {maxed_result['decks_count']}/4 deck(s) de GDC trouvé(s) pour ce jour-là "
            "dans le battlelog — le chiffre ci-dessus n'est donc pas basé sur un jour complet."
        )

    st.markdown("---")
    st.markdown("**Progression dans le clan**")
    _render_progress_timeline(streak, role)

    subj_est = "Tu es" if is_self else f"{display_name} est"
    subj_as = "Tu as" if is_self else f"{display_name} a"
    subj_etais = "Tu étais" if is_self else f"{display_name} était"

    # "Points à surveiller" + récap du règlement, remontés juste après la
    # frise et tout en haut de la page — demande de Flo, 16/08/2026 soir
    # ("remonter 'points à surveiller' tout en haut de la page ... juste
    # après la frise" + "un petit récap des règles du clan ... à côté
    # justement de 'points à surveiller'"). Le récap est généré par
    # exclusions.rules_summary_markdown() (source unique, partagée avec
    # Suivi clan > Exclusions) pour ne jamais diverger du moteur de règles.
    st.markdown("---")
    col_watch, col_rules = st.columns(2)
    with col_watch:
        st.markdown("**Points à surveiller**")
        if not history:
            st.caption("Pas encore d'historique de GDC disponible.")
        else:
            recent_miss = next((h for h in history if not h["full"]), None)
            if recent_miss is None:
                st.write("✅ Aucun manque détecté sur l'historique disponible — continue comme ça !" if is_self
                          else f"✅ Aucun manque détecté sur l'historique disponible pour {display_name}.")
            else:
                if not recent_miss["present"]:
                    st.write(
                        f"⚠️ {subj_etais} absent de la GDC du {fmt.format_date(recent_miss['createdDate'])} — "
                        "ça casse la série pour l'éligibilité Aîné/Chef adjoint."
                    )
                else:
                    advice = (
                        "pense à jouer tous tes decks chaque jour de GDC pour construire ta série."
                        if is_self else "à surveiller pour la suite."
                    )
                    st.write(
                        f"⚠️ GDC du {fmt.format_date(recent_miss['createdDate'])} : "
                        f"{recent_miss['decks_used']}/16 decks joués — {advice}"
                    )
    with col_rules:
        st.markdown("**📜 Règlement du clan (résumé)**")
        with st.container(border=True):
            st.markdown(exclusions.rules_summary_markdown())

    _render_warnings_graces_section(full_history, clan_tag, player_tag, is_self=is_self, display_name=display_name)

    if role in ("coLeader", "leader"):
        st.success(
            f"{'Tu as' if is_self else display_name + ' a'} déjà le rang maximum suivi ici — "
            "rien à débloquer de ce côté. 🎉"
        )
    elif role == "elder":
        if status["coleader_eligible"]:
            st.success(
                f"{subj_est} éligible au rang Chef adjoint ({streak} semaines à 100%) — "
                + ("signale-le à un chef pour qu'il/elle te promeuve en jeu."
                   if is_self else "peut être promu(e) en jeu.")
            )
        else:
            st.info(f"Encore {status['weeks_to_coleader']} semaine(s) à 100% d'assiduité pour être éligible Chef adjoint.")
    else:  # member ou rôle inconnu
        if status["elder_eligible"]:
            st.success(
                f"{subj_est} éligible au rang Aîné ({streak} semaines à 100%) — "
                + ("signale-le à un chef pour qu'il/elle te promeuve en jeu."
                   if is_self else "peut être promu(e) en jeu.")
            )
        else:
            st.info(f"Encore {status['weeks_to_elder']} semaine(s) à 100% d'assiduité pour être éligible Aîné.")

    with st.expander(f"Historique détaillé ({len(history)} GDC disponibles via l'API)"):
        for h in history:
            icon = "✅" if h["full"] else ("➖" if not h["present"] else "⚠️")
            label = "absent" if not h["present"] else f"{h['decks_used']}/16 decks"
            st.write(f"{icon} GDC #{h['seasonId']} — {fmt.format_date(h['createdDate'])} — {label}")
