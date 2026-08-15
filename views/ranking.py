"""views/ranking.py — Classement (moyenne Trophées), GDC en cours, Historique GDC."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import clash_api as api
import data
import discord_post
import exclusions
import fmt
import gdc_calendar
import history as gdc_history
import logic
import storage
import table_style as ts

POST_N_RACES = 10  # nombre de GDC utilisé pour le classement posté sur Discord (fixe, indépendant du slider d'affichage)


def _table_height(n_rows: int, max_height: int = 900) -> int:
    """Hauteur de tableau qui affiche toutes les lignes sans scroll interne
    (jusqu'à max_height), au lieu de la petite hauteur fixe par défaut de Streamlit."""
    return min(38 + 35 * max(n_rows, 1), max_height)


def _narrow_text_input(label: str, key: str) -> str:
    """st.text_input mais dans une colonne étroite plutôt que pleine largeur
    (demande de Flo, 15/08/2026 — valable pour tous les champs de recherche)."""
    col, _ = st.columns([1, 3])
    with col:
        return st.text_input(label, key=key)


def _narrow_selectbox(label: str, options, format_func, key: str):
    """st.selectbox mais dans une colonne étroite plutôt que pleine largeur
    (même logique que _narrow_text_input, demande de Flo, 15/08/2026 soir —
    utilisé pour le sélecteur de GDC dans 'Historique GDC')."""
    col, _ = st.columns([1, 3])
    with col:
        return st.selectbox(label, options=options, format_func=format_func, key=key)


def _group_race_log_by_season(race_log: list[dict]) -> dict[str, list[dict]]:
    """
    Un `seasonId` Supercell peut regrouper plusieurs semaines de GDC
    (`sectionIndex` 0 à 3) — voir history.py. Pour 'Historique GDC', on
    regroupe donc le race_log par saison plutôt que d'avoir une entrée par
    semaine (demande de Flo, 15/08/2026 soir), avec les semaines triées par
    ordre chronologique (sectionIndex croissant) à l'intérieur de chaque
    saison. L'ordre des clés du dict suit l'ordre d'apparition dans
    `race_log` (donc du plus récent au plus ancien, comme l'API)."""
    seasons: dict[str, list[dict]] = {}
    for item in race_log:
        sid = str(item.get("seasonId", ""))
        seasons.setdefault(sid, []).append(item)
    for sid, weeks in seasons.items():
        weeks.sort(key=lambda it: it.get("sectionIndex", 0))
    return seasons


def _season_label(season_id: str, weeks: list[dict]) -> str:
    """'GDC #<id> — <date>' pour une saison d'une seule semaine, ou
    'GDC #<id> — <date début> → <date fin>' pour une saison à plusieurs
    semaines (fourchette de dates plutôt qu'une entrée par semaine)."""
    dates = [fmt.format_date(w.get("createdDate", "")) for w in weeks]
    dates = [d for d in dates if d]
    if not dates:
        date_str = "?"
    elif len(dates) == 1 or dates[0] == dates[-1]:
        date_str = dates[0]
    else:
        date_str = f"{dates[0]} → {dates[-1]}"
    return f"GDC #{season_id} — {date_str}"


def _current_member_tags(clan_tag: str) -> set[str] | None:
    try:
        return {logic.norm_tag(m.get("tag", "")) for m in data.load_clan_members(clan_tag)}
    except api.ClashAPIError:
        return None


def _render_discord_post_section(ctx: dict, full_history: list[dict], current_tags: set[str] | None) -> None:
    """Bouton "Poster sur Discord" (chefs uniquement) — remplace le post automatique
    du bot Discord, arrêté le 15/08/2026 à la demande de Flo. Actif à partir du lundi
    12h00 (heure de Bruxelles), une seule fois par semaine (voir storage.ranking_posts).

    Placé en haut de l'onglet Classement, à côté de la recherche par pseudo,
    et bien mis en évidence (demande de Flo, 15/08/2026 soir)."""
    if not full_history:
        return

    latest = full_history[0]
    week = storage.week_key(latest.get("seasonId", ""), latest.get("sectionIndex", 0))
    already_posted = storage.get_ranking_post_for_week(week)

    if not discord_post.webhook_configured():
        st.caption("📣 Discord : webhook non configuré.")
        return

    if already_posted:
        st.button(
            "✅ Déjà posté cette semaine",
            disabled=True,
            use_container_width=True,
            help=f"Posté par {already_posted.get('posted_by', '?')} le {already_posted.get('posted_at', '?')}.",
        )
        return

    if not gdc_calendar.is_after_monday_noon():
        st.button("📣 Poster sur Discord", disabled=True, use_container_width=True)
        st.caption("Dispo à partir de lundi 12h00 (heure de Bruxelles).")
        return

    if st.button("📤 Poster sur Discord", type="primary", use_container_width=True):
        post_stats = exclusions.compute_player_stats(full_history[:POST_N_RACES], ctx["clan_tag"])
        if current_tags is not None:
            post_stats = {tag: s for tag, s in post_stats.items() if tag in current_tags}
        ranked_now = exclusions.ranked_list(post_stats)

        ranked_prev = None
        if len(full_history) >= POST_N_RACES + 1:
            prev_stats = exclusions.compute_player_stats(
                full_history[1 : 1 + POST_N_RACES], ctx["clan_tag"]
            )
            if current_tags is not None:
                prev_stats = {tag: s for tag, s in prev_stats.items() if tag in current_tags}
            ranked_prev = exclusions.ranked_list(prev_stats)

        messages = discord_post.build_ranking_messages(
            ranked_now,
            ranked_prev,
            n_gdcs=min(POST_N_RACES, len(full_history)),
            latest_date=fmt.format_date(latest.get("createdDate", "")),
            posted_by=ctx["display_name"],
        )
        try:
            discord_post.post_ranking_to_discord(messages)
        except Exception as exc:
            st.error(f"Échec de l'envoi sur Discord : {exc}")
        else:
            storage.record_ranking_post(week, ctx["display_name"])
            st.success("Classement posté sur Discord !")
            st.rerun()


def render(ctx: dict) -> None:
    st.subheader("🏆 Classement")
    clan_tag = ctx["clan_tag"]

    tab_classement, tab_cours, tab_historique = st.tabs(["Classement", "GDC en cours", "Historique GDC"])

    with tab_classement:
        st.caption(
            "Classement basé sur les **Trophées** (Fame — points de participation individuels en GDC) — "
            "c'est la donnée la plus proche des « trophées gagnés » disponible par joueur via l'API officielle."
        )
        max_available = st.session_state.get("_race_log_max_len", 10)
        n_races = st.slider(
            "Nombre de GDC prises en compte", min_value=1, max_value=max(max_available, 10), value=min(10, max_available),
            help="Le classement (rang, assiduité, trophées) est calculé sur ce nombre de GDC les plus récentes.",
        )
        try:
            race_log = data.load_race_log(clan_tag, limit=max(n_races, 10))
            st.session_state["_race_log_max_len"] = len(race_log) or 10
            gdc_history.sync_archive(race_log, clan_tag)

            current_tags = _current_member_tags(clan_tag)

            # Recherche + bouton Discord en haut, côte à côte et proches l'un de
            # l'autre (demande de Flo, 15/08/2026 soir — le 1er placement mettait
            # le bouton trop loin sur la droite) — avant même le tableau.
            if ctx.get("is_chef"):
                full_history = gdc_history.get_full_history(clan_tag, race_log)
                col_search, col_discord, _col_spacer = st.columns([1, 1, 2], gap="small")
                with col_search:
                    name_filter = st.text_input("Filtrer par nom", key="filter_ranking")
                with col_discord:
                    st.markdown("&nbsp;")  # aligne le bouton avec le champ de recherche (qui a un label)
                    _render_discord_post_section(ctx, full_history, current_tags)
            else:
                name_filter = _narrow_text_input("Filtrer par nom", key="filter_ranking")

            stats = exclusions.compute_player_stats(race_log[:n_races], clan_tag)
            if current_tags is not None:
                stats = {tag: s for tag, s in stats.items() if tag in current_tags}

            if not stats:
                st.info("Aucune donnée d'historique GDC trouvée pour ce clan.")
            else:
                # Rang + palier calculés en UNE seule fois par exclusions.ranked_list()
                # (même critère — ranking_score — que les sections ci-dessous, donc le
                # numéro de rang affiché est toujours cohérent avec la section du joueur).
                ranked = exclusions.ranked_list(stats)
                full_df = pd.DataFrame(
                    [
                        {
                            "Rang": p["rang"],
                            "Palier": p["tier"],
                            "Joueur": p["name"],
                            "Tag": f"#{p['tag']}",
                            "GDC jouées": p["gdc_count"],
                            "Decks joués": p["total_decks"],
                            "Decks max": p["gdc_count"] * exclusions.FULL_DECKS,
                            "Assiduité %": p["assiduity_pct"],
                            "Trophées totaux": p["total_fame"],
                            "Trophées moy./GDC": p["avg_fame"],
                        }
                        for p in ranked
                    ]
                )

                filtered = (
                    full_df[full_df["Joueur"].str.contains(name_filter, case=False, na=False)]
                    if name_filter
                    else full_df
                )

                st.caption(f"{len(filtered)} joueur(s) affiché(s) sur {len(full_df)} — {len(race_log)} GDC disponibles via l'API.")

                cols_to_show = [
                    "Rang", "Joueur", "Tag", "GDC jouées", "Decks joués",
                    "Decks max", "Assiduité %", "Trophées totaux", "Trophées moy./GDC",
                ]
                shown_any = False
                for tier_name in exclusions.TIER_ORDER:
                    section = filtered[filtered["Palier"] == tier_name]
                    if section.empty:
                        continue
                    shown_any = True
                    st.markdown(f"**{tier_name}** ({len(section)})")
                    st.caption(exclusions.TIER_DESCRIPTIONS.get(tier_name, ""))
                    # Ligne du joueur connecté mise en valeur (demande de Flo, 16/08/2026).
                    styler = ts.highlight_player_row(section[cols_to_show].style, "Tag", ctx.get("player_tag", ""))
                    st.dataframe(
                        styler,
                        hide_index=True,
                        use_container_width=False,
                        height=_table_height(len(section)),
                        # "Assiduité %" forcée à 2 décimales (demande de Flo,
                        # 16/08/2026 soir — affichage type "42.0000000000" sinon).
                        column_config=ts.mobile_column_config(
                            cols_to_show, number_formats={"Assiduité %": "%.2f"}
                        ),
                    )
                if not shown_any:
                    st.info("Aucun joueur ne correspond au filtre.")
        except api.ClashAPIError as exc:
            st.error(str(exc))

    with tab_cours:
        try:
            current = data.load_current_race(clan_tag)
            st.caption(f"État : {current.get('state', '?')}")
            df_cur = logic.compute_current_race_table(current)
            # L'API Supercell garde dans `participants` les joueurs ayant quitté
            # le clan en cours de GDC — sans filtrage ça peut afficher plus de
            # 50 lignes pour un clan à 50 max (bug "83 joueurs" signalé par
            # Flo, 15/08/2026 soir). On ne garde que les membres ACTUELS.
            current_tags_cur = _current_member_tags(clan_tag)
            if current_tags_cur is not None and not df_cur.empty:
                df_cur = df_cur[df_cur["Tag"].apply(lambda t: logic.norm_tag(t) in current_tags_cur)].reset_index(drop=True)
            if df_cur.empty:
                st.info("Pas de GDC en cours actuellement (ou données indisponibles).")
            else:
                search = _narrow_text_input("Filtrer par nom", key="filter_cur_race")
                view = df_cur[df_cur["Joueur"].str.contains(search, case=False, na=False)] if search else df_cur
                # Trié par défaut sur les Trophées, décroissant (demande de Flo, 15/08/2026 soir).
                view = view.sort_values("Trophées", ascending=False).reset_index(drop=True)

                view = view.rename(
                    columns={
                        "Decks joués": "Decks joués (total GDC)",
                        "Decks aujourd'hui": "Decks joués aujourd'hui",
                        "Attaques bateau adverse": "Attaques bateau adverse",
                    }
                )
                cols = [
                    "Joueur", "Tag", "Decks joués (total GDC)", "Decks joués aujourd'hui",
                    "Attaques bateau adverse", "Trophées",
                ]
                view = view[cols]

                st.markdown(f"**Tous les joueurs ({len(view)})**")
                expected_total = gdc_calendar.expected_decks_now()
                if expected_total is None:
                    st.caption("Pas de GDC en cours aujourd'hui (mardi/mercredi) — tableau non coloré.")

                styler = view.style
                styler = ts.style_map(
                    styler, lambda v: ts.decks_color(v, expected_total), subset=["Decks joués (total GDC)"]
                )
                styler = ts.style_map(
                    styler, lambda v: ts.decks_color(v, 4), subset=["Decks joués aujourd'hui"]
                )
                styler = ts.style_map(
                    styler, ts.boat_attacks_color, subset=["Attaques bateau adverse"]
                )
                # Ligne du joueur connecté mise en valeur (demande de Flo, 16/08/2026) —
                # bordure, pas un fond : ne casse pas les couleurs déjà posées ci-dessus.
                styler = ts.highlight_player_row(styler, "Tag", ctx.get("player_tag", ""))
                st.dataframe(
                    styler, hide_index=True, use_container_width=False, height=_table_height(len(view)),
                    column_config=ts.mobile_column_config(cols),
                )
        except api.ClashAPIError as exc:
            st.error(str(exc))

    with tab_historique:
        try:
            race_log = data.load_race_log(clan_tag, limit=10)
            if not race_log:
                st.info("Aucun historique disponible.")
            else:
                # Regroupé par saison (une saison = 1 à 4 semaines de GDC) avec
                # une fourchette de dates plutôt qu'une entrée par semaine, et
                # jusqu'à 4 tableaux affichés d'un coup pour la saison choisie
                # — pour voir en un coup d'œil les GDC passées contre les mêmes
                # adversaires (demande de Flo, 15/08/2026 soir).
                seasons = _group_race_log_by_season(race_log)
                season_ids = list(seasons.keys())
                selected_sid = _narrow_selectbox(
                    "Choisir une GDC",
                    options=season_ids,
                    format_func=lambda sid: _season_label(sid, seasons[sid]),
                    key="historique_season",
                )
                weeks = seasons[selected_sid]
                if len(weeks) > 1:
                    st.caption(f"{len(weeks)} semaines dans cette GDC — même adversaires du début à la fin.")

                for i, item in enumerate(weeks):
                    if len(weeks) > 1:
                        st.markdown(
                            f"#### Semaine {item.get('sectionIndex', i) + 1} — {fmt.format_date(item.get('createdDate', ''))}"
                        )
                    standings_df = pd.DataFrame(
                        [
                            {
                                "Rang": s.get("rank"),
                                "Clan": s.get("clan", {}).get("name", "?"),
                                "Trophées": s.get("clan", {}).get("fame", 0),
                                "Δ Trophées (clan)": s.get("trophyChange", 0),
                            }
                            for s in item.get("standings", [])
                        ]
                    ).sort_values("Rang")
                    st.dataframe(
                        standings_df, hide_index=True, use_container_width=False,
                        height=_table_height(len(standings_df)),
                        column_config=ts.mobile_column_config(list(standings_df.columns)),
                    )

                    our_standing = next(
                        (s for s in item.get("standings", []) if logic.norm_tag(s.get("clan", {}).get("tag", "")) == logic.norm_tag(clan_tag)),
                        None,
                    )
                    if our_standing:
                        st.markdown("**Détail par joueur (notre clan) — classé par Trophées :**")
                        detail_df = pd.DataFrame(
                            [
                                {
                                    "Joueur": p.get("name", "?"),
                                    "Tag": p.get("tag", ""),  # gardé pour highlight_player_row, colonne masquée ci-dessous
                                    "Decks joués": p.get("decksUsed", 0),
                                    "Trophées": p.get("fame", 0),
                                    "Attaques bateau adverse": p.get("boatAttacks", 0),
                                }
                                for p in our_standing["clan"].get("participants", [])
                            ]
                        ).sort_values("Trophées", ascending=False).reset_index(drop=True)
                        detail_df.insert(0, "Rang", range(1, len(detail_df) + 1))
                        # Ligne du joueur connecté mise en valeur (demande de Flo, 16/08/2026).
                        styler = ts.highlight_player_row(detail_df.style, "Tag", ctx.get("player_tag", ""))
                        styler = styler.hide(axis="columns", subset=["Tag"])
                        st.dataframe(
                            styler, hide_index=True, use_container_width=False,
                            height=_table_height(len(detail_df)),
                            column_config=ts.mobile_column_config(list(detail_df.columns)),
                        )
                    if len(weeks) > 1 and i < len(weeks) - 1:
                        st.divider()
        except api.ClashAPIError as exc:
            st.error(str(exc))
