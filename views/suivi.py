"""views/suivi.py — Suivi clan : Rapport, Exclusions, Promotions (chef uniquement).

Note : "Niveaux de cartes" (_render_cards_tab) a été retiré des onglets affichés
le 15/08/2026 soir à la demande de Flo (sera intégré dans une future page
Statistiques) — la fonction reste définie pour réutilisation ultérieure."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import clash_api as api
import data
import exclusions
import fmt
import history as gdc_history
import logic
import progression
import storage
import table_style as ts

FULL_DECKS = exclusions.FULL_DECKS  # 16


def _table_height(n_rows: int, max_height: int = 700) -> int:
    return min(38 + 35 * max(n_rows, 1), max_height)


def _narrow_text_input(label: str, key: str | None = None) -> str:
    """st.text_input mais dans une colonne étroite plutôt que pleine largeur
    (demande de Flo, 15/08/2026 — valable pour tous les champs de recherche)."""
    col, _ = st.columns([1, 3])
    with col:
        return st.text_input(label, key=key)


def _current_member_tags(clan_tag: str) -> set[str] | None:
    """Tags normalisés des membres actuels du clan, ou None si indisponible
    (dans ce cas on ne filtre pas plutôt que de tout casser)."""
    try:
        return {logic.norm_tag(m.get("tag", "")) for m in data.load_clan_members(clan_tag)}
    except api.ClashAPIError:
        return None


def _load_full_history(clan_tag: str) -> list[dict] | None:
    """Historique complet (archive + live) — nécessaire pour le moteur
    d'exclusions (ancienneté réelle + fenêtre glissante, voir exclusions.py).
    Renvoie None si l'API est indisponible plutôt que de faire planter la page."""
    try:
        race_log = data.load_race_log(clan_tag, limit=10)
        if not race_log:
            return []
        gdc_history.sync_archive(race_log, clan_tag)
        return gdc_history.get_full_history(clan_tag, race_log)
    except api.ClashAPIError:
        return None


def compute_pending_exclusions_count(clan_tag: str) -> int:
    """Nombre de recommandations d'exclusion actuelles — utilisé pour les
    pastilles de notification (menu de gauche + onglet Exclusions). Retourne
    0 si les données ne sont pas disponibles plutôt que de faire planter la
    sidebar."""
    full_history = _load_full_history(clan_tag)
    if not full_history:
        return 0
    manual_graces = exclusions.manual_grace_keys(storage.get_manual_graces())
    current_tags = _current_member_tags(clan_tag)
    report = exclusions.build_exclusion_report(full_history, clan_tag, manual_graces, current_tags)
    return len(report["excl"])


def _dual_window_table(stats_last: dict, stats_10: dict, current_tags: set[str] | None) -> pd.DataFrame:
    """Fusionne les stats 1-GDC et 10-GDC par joueur pour les 2 tableaux du Rapport."""
    tags = set(stats_last) | set(stats_10)
    if current_tags is not None:
        tags &= current_tags
    rows = []
    for tag in tags:
        s1 = stats_last.get(tag)
        s10 = stats_10.get(tag)
        name = (s1 or s10)["name"]
        decks_last = s1["total_decks"] if s1 else None
        diff_last = (FULL_DECKS - decks_last) if s1 else None
        decks_10 = s10["total_decks"] if s10 else 0
        gdc_10 = s10["gdc_count"] if s10 else 0
        diff_10 = (gdc_10 * FULL_DECKS - decks_10) if s10 else 0
        boats_last = s1["total_boat_attacks"] if s1 else 0
        boats_10 = s10["total_boat_attacks"] if s10 else 0
        rows.append(
            {
                "tag": tag, "Joueur": name, "Tag": f"#{tag}",
                "Decks joués (dernière GDC)": decks_last,
                "Différence (dernière GDC)": diff_last,
                "Decks joués (10 dernières GDC)": decks_10,
                "Différence (10 dernières GDC)": diff_10,
                "Attaques bateau (dernière GDC)": boats_last,
                "Decks dépensés sur bateaux (10 dernières GDC)": boats_10,
            }
        )
    return pd.DataFrame(rows)


def _grace_widget(tag: str, name: str, season_id: str, granted_by: str, key_prefix: str) -> None:
    """Bouton + commentaire optionnel pour accorder une grâce manuelle à un joueur."""
    with st.expander(f"🕊️ Grâcier {name}"):
        comment = st.text_input(
            "Commentaire (optionnel, visible par les chefs et par le joueur)",
            key=f"{key_prefix}_comment_{tag}",
        )
        if st.button("Confirmer la grâce", key=f"{key_prefix}_btn_{tag}"):
            storage.add_manual_grace(
                player_tag=f"#{tag}", player_name=name, season_id=season_id,
                comment=comment, granted_by=granted_by,
            )
            st.success(f"{name} a été gracié pour cette GDC.")
            st.rerun()


def _render_rapport_tab(ctx: dict) -> None:
    """Les 2 tableaux bruts (decks joués/non-joués + attaques bateau), côte à
    côte (demande de Flo, 15/08/2026 soir)."""
    clan_tag = ctx["clan_tag"]
    try:
        race_log = data.load_race_log(clan_tag, limit=10)
        if not race_log:
            st.info("Aucun historique de GDC disponible.")
            return

        current_tags = _current_member_tags(clan_tag)
        stats_last = exclusions.compute_player_stats(race_log[:1], clan_tag)
        stats_10 = exclusions.compute_player_stats(race_log[:10], clan_tag)
        full = _dual_window_table(stats_last, stats_10, current_tags)

        col_decks, col_boats = st.columns(2)

        with col_decks:
            st.markdown("**Decks joués/non-joués**")
            st.caption(
                "« Différence » = decks attendus moins decks joués (16 par GDC). "
                "Classé sur la différence de la dernière GDC."
            )
            missing = full[full["Différence (dernière GDC)"].fillna(0) > 0].copy()
            missing = missing.sort_values(
                ["Différence (dernière GDC)", "Différence (10 dernières GDC)"], ascending=False
            ).reset_index(drop=True)
            if missing.empty:
                st.success("✅ Personne n'a de decks manquants sur la dernière GDC.")
            else:
                cols = [
                    "Joueur", "Tag", "Decks joués (dernière GDC)", "Différence (dernière GDC)",
                    "Decks joués (10 dernières GDC)", "Différence (10 dernières GDC)",
                ]
                int_cols = [
                    "Decks joués (dernière GDC)", "Différence (dernière GDC)",
                    "Decks joués (10 dernières GDC)", "Différence (10 dernières GDC)",
                ]
                styler = missing[cols].style
                styler = styler.apply(
                    lambda row: ts.paired_decks_color_row(row, "Decks joués (dernière GDC)", "Différence (dernière GDC)"),
                    axis=1, subset=["Decks joués (dernière GDC)", "Différence (dernière GDC)"],
                )
                styler = styler.apply(
                    lambda row: ts.paired_decks_color_row(
                        row, "Decks joués (10 dernières GDC)", "Différence (10 dernières GDC)"
                    ),
                    axis=1, subset=["Decks joués (10 dernières GDC)", "Différence (10 dernières GDC)"],
                )
                styler = ts.format_int_columns(styler, int_cols)
                st.dataframe(
                    styler, hide_index=True, use_container_width=True, height=_table_height(len(missing)),
                    column_config=ts.mobile_column_config(cols),
                )

        with col_boats:
            st.markdown("**Attaques de bateaux adverses**")
            st.caption("Decks dépensés sur des bateaux adverses plutôt que sur le clan adverse. Classé sur la dernière GDC.")
            boats = full[full["Attaques bateau (dernière GDC)"].fillna(0) > 0].copy()
            boats = boats.sort_values(
                ["Attaques bateau (dernière GDC)", "Decks dépensés sur bateaux (10 dernières GDC)"], ascending=False
            ).reset_index(drop=True)
            if boats.empty:
                st.success("✅ Aucune attaque de bateau adverse détectée sur la dernière GDC.")
            else:
                cols = ["Joueur", "Tag", "Attaques bateau (dernière GDC)", "Decks dépensés sur bateaux (10 dernières GDC)"]
                int_cols = ["Attaques bateau (dernière GDC)", "Decks dépensés sur bateaux (10 dernières GDC)"]
                styler = boats[cols].style
                styler = ts.style_map(
                    styler, ts.boat_attacks_color,
                    subset=["Attaques bateau (dernière GDC)", "Decks dépensés sur bateaux (10 dernières GDC)"],
                )
                styler = ts.format_int_columns(styler, int_cols)
                st.dataframe(
                    styler, hide_index=True, use_container_width=True, height=_table_height(len(boats)),
                    column_config=ts.mobile_column_config(cols),
                )
    except api.ClashAPIError as exc:
        st.error(str(exc))


def _render_exclusions_tab(ctx: dict) -> None:
    """Recommandations d'exclusion, en 3 colonnes (exclusions / avertissements
    / grâces — demande de Flo, 15/08/2026 soir)."""
    clan_tag = ctx["clan_tag"]

    # Récap du règlement, tout en haut de l'onglet, avant les rapports —
    # demande de Flo, 16/08/2026 soir (pendant du récap affiché aux joueurs
    # sur "Mon profil", même source : exclusions.rules_summary_markdown()).
    with st.expander("📜 Règlement du clan (résumé)", expanded=True):
        st.markdown(exclusions.rules_summary_markdown())

    full_history = _load_full_history(clan_tag)
    if full_history is None:
        st.error("Impossible de charger l'historique GDC (API indisponible).")
        return
    if not full_history:
        st.info("Aucun historique de GDC disponible.")
        return

    current_tags = _current_member_tags(clan_tag)
    manual_graces_raw = storage.get_manual_graces()
    manual_graces = exclusions.manual_grace_keys(manual_graces_raw)
    report = exclusions.build_exclusion_report(full_history, clan_tag, manual_graces, current_tags)
    excl, warn, grace = report["excl"], report["warn"], report["grace"]
    latest_season = str(full_history[0].get("seasonId", ""))

    st.caption(
        "Calculé sur les 10 dernières GDC glissantes de chaque joueur (Règles 1 à 7 — "
        "voir l'explication complète transmise le 15/08/2026). Seuls les membres actuels du clan sont affichés."
    )

    if not excl and not warn and not grace:
        st.success("✅ Aucune recommandation — tout le monde respecte le règlement. 🎉")

    col_excl, col_warn, col_grace = st.columns(3)

    with col_excl:
        st.markdown(f"🔴 **Exclusions recommandées ({len(excl)})**")
        for tag, s in sorted(excl.items(), key=lambda kv: kv[1]["name"].lower()):
            with st.container(border=True):
                st.markdown(f"**{s['name']}** ({s['tag']}) — {s['tenure']} semaine(s) d'ancienneté")
                # Format compact "GDC #X - Y/16 decks joués (Règle N)" au lieu
                # de la phrase complète du motif — demande de Flo, 16/08/2026
                # ("plus compact, plus lisible"). Un SEUL affichage par semaine
                # désormais (avant : le résumé `reason_excl` listait déjà ces
                # mêmes semaines, PUIS cette boucle les relistait une 2e fois
                # avec les dates -> vrai doublon visible dans le rapport,
                # signalé par Flo via capture d'écran).
                for w in s["excl_weeks"]:
                    st.caption(exclusions.format_week_line(w))
                # Cas où l'exclusion vient du cumul ({WARN_TO_EXCL_THRESHOLD}
                # avertissements actifs) plutôt que d'une exclusion directe :
                # une phrase de résumé toujours visible + le détail dans un
                # expander (cartes compactes par défaut, surtout à 3 colonnes).
                if s["warning_count"] >= exclusions.WARN_TO_EXCL_THRESHOLD:
                    st.caption(
                        f"Cumul de {s['warning_count']} avertissement(s) actif(s) sur les "
                        f"{exclusions.NB_GDC} dernières GDC."
                    )
                    if s["warning_weeks"]:
                        with st.expander(f"Détail des {s['warning_count']} avertissement(s)"):
                            for w in s["warning_weeks"]:
                                st.caption(exclusions.format_week_line(w))
                            if s.get("converted_from_grace"):
                                st.caption(
                                    f"+ {s['converted_from_grace']} avertissement(s) issu(s) de la conversion "
                                    "de grâces (Règle 5)."
                                )
                _grace_widget(tag, s["name"], latest_season, ctx["username"], "excl")

    with col_warn:
        st.markdown(f"⚠️ **Avertissements ({len(warn)})**")
        for tag, s in sorted(warn.items(), key=lambda kv: kv[1]["name"].lower()):
            with st.container(border=True):
                st.markdown(
                    f"**{s['name']}** ({s['tag']}) — {s['warning_count']} avertissement(s) actif(s), "
                    f"{s['tenure']} semaine(s) d'ancienneté"
                )
                for w in s["warning_weeks"]:
                    st.caption(exclusions.format_week_line(w))
                if s.get("converted_from_grace"):
                    st.caption(f"+ {s['converted_from_grace']} avertissement(s) issu(s) de la conversion de grâces (Règle 5).")
                _grace_widget(tag, s["name"], latest_season, ctx["username"], "warn")

    with col_grace:
        st.markdown(f"✅ **Grâces ({len(grace)})**")
        for tag, s in sorted(grace.items(), key=lambda kv: kv[1]["name"].lower()):
            with st.container(border=True):
                st.markdown(
                    f"**{s['name']}** ({s['tag']}) — {s['grace_count']} grâce(s) active(s), "
                    f"{s['tenure']} semaine(s) d'ancienneté"
                )
                for w in s["grace_weeks"]:
                    origin = "manuelle" if w["manual"] else "automatique"
                    st.caption(f"{exclusions.format_week_line(w)} — grâce {origin}")

    if manual_graces_raw:
        with st.expander(f"🕊️ Historique des grâces manuelles ({len(manual_graces_raw)})"):
            for g in sorted(manual_graces_raw, key=lambda g: g.get("granted_at", ""), reverse=True):
                comment = f" — « {g['comment']} »" if g.get("comment") else ""
                st.write(
                    f"**{g.get('player_name', '?')}** ({g.get('player_tag', '?')}) — "
                    f"GDC #{g.get('season_id', '?')} — accordée par {g.get('granted_by', '?')} "
                    f"le {fmt.format_date(g.get('granted_at', ''), with_time=True)}{comment}"
                )


def _render_promotions_tab(ctx: dict) -> None:
    clan_tag = ctx["clan_tag"]
    st.caption(
        f"Joueurs ayant atteint {progression.ELDER_WEEKS_REQUIRED} semaines à 100% (éligibles Aîné) ou "
        f"{progression.COLEADER_WEEKS_REQUIRED} semaines à 100% (éligibles Chef adjoint). "
        "La promotion doit être faite manuellement dans le jeu — l'API ne permet pas de le faire depuis l'outil."
    )
    try:
        members = data.load_clan_members(clan_tag)
        race_log = data.load_race_log(clan_tag, limit=max(progression.COLEADER_WEEKS_REQUIRED, 10))
        promotable = progression.find_promotable_players(members, race_log, clan_tag)
        if not promotable:
            st.info("Personne n'est actuellement éligible à une promotion.")
        else:
            df = pd.DataFrame(
                [
                    {
                        "Joueur": p["name"],
                        "Tag": p["tag"],
                        "Rôle actuel": p["role"],
                        "Prochain rang": p["next_rank"],
                        "Série (semaines à 100%)": p["streak_weeks"],
                    }
                    for p in promotable
                ]
            ).sort_values("Série (semaines à 100%)", ascending=False)
            st.dataframe(
                df, hide_index=True, use_container_width=False, height=_table_height(len(df)),
                column_config=ts.mobile_column_config(list(df.columns)),
            )
    except api.ClashAPIError as exc:
        st.error(str(exc))


def _render_cards_tab(ctx: dict) -> None:
    clan_tag = ctx["clan_tag"]
    tab_clan, tab_joueur = st.tabs(["Vue d'ensemble du clan", "Fiche joueur"])

    with tab_clan:
        st.caption(
            "Récupère la fiche de chaque membre pour comparer les niveaux de cartes normalisés "
            "(échelle commune, indépendante de la rareté). Peut prendre quelques dizaines de secondes."
        )
        if st.button("📥 Charger les niveaux de cartes de tout le clan"):
            try:
                members = data.load_clan(clan_tag).get("memberList", [])
                tags = [m.get("tag") for m in members if m.get("tag")]
                progress_bar = st.progress(0.0, text="Récupération des fiches joueurs...")

                def _cb(done, total):
                    progress_bar.progress(done / total, text=f"{done}/{total} joueurs récupérés")

                st.session_state["cards_data"] = logic.fetch_all_members_cards(tags, data.load_player, progress_cb=_cb)
                progress_bar.empty()
            except api.ClashAPIError as exc:
                st.error(str(exc))

        cards_data = st.session_state.get("cards_data")
        if cards_data:
            summary_rows = []
            errors = []
            for tag, player in cards_data.items():
                if "__error__" in player:
                    errors.append((tag, player["__error__"]))
                    continue
                cdf = logic.compute_card_levels(player)
                if cdf.empty:
                    continue
                summary_rows.append(
                    {
                        "Joueur": player.get("name", tag),
                        "Tag": tag,
                        "Niveau moyen (jeu)": round(cdf["Niveau (jeu)"].mean(), 1),
                        "Niveau min (jeu)": int(cdf["Niveau (jeu)"].min()),
                        "Carte la plus faible": cdf.iloc[0]["Carte"],
                    }
                )
            summary_df = pd.DataFrame(summary_rows).sort_values("Niveau moyen (jeu)")

            threshold = st.slider("Seuil d'alerte : niveau (jeu) minimum attendu", 1, 14, 11)
            summary_df["Cartes sous le seuil"] = [
                int((logic.compute_card_levels(cards_data[row["Tag"]])["Niveau (jeu)"] < threshold).sum())
                for _, row in summary_df.iterrows()
            ]

            only_below = st.checkbox("N'afficher que les joueurs ayant des cartes sous le seuil")
            view = summary_df[summary_df["Cartes sous le seuil"] > 0] if only_below else summary_df
            st.dataframe(view, hide_index=True, use_container_width=False, height=_table_height(len(view)))

            if errors:
                with st.expander(f"⚠️ {len(errors)} joueur(s) non récupéré(s)"):
                    for tag, err in errors:
                        st.write(f"`{tag}` — {err}")
        else:
            st.info("Clique sur le bouton ci-dessus pour charger les données.")

    with tab_joueur:
        try:
            members = data.load_clan(clan_tag).get("memberList", [])
            members_sorted = sorted(members, key=lambda m: (m.get("name") or "").lower())
            member_options = {f"{m.get('name')} ({m.get('tag')})": m.get("tag") for m in members_sorted}
            choice = st.selectbox("Choisir un membre", options=list(member_options.keys()) if member_options else [])
            manual_tag = _narrow_text_input("...ou saisir un tag joueur directement (optionnel)")
            target_tag = manual_tag.strip() or (member_options.get(choice) if choice else None)

            if target_tag:
                player = data.load_player(target_tag)
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Niveau d'XP", player.get("expLevel", "?"))
                col2.metric("Trophées", player.get("trophies", "?"))
                col3.metric("Meilleur score", player.get("bestTrophies", "?"))
                col4.metric("Rôle clan", player.get("role", "?"))

                cards_df = logic.compute_card_levels(player)
                st.markdown("**Cartes**")
                rarity_filter = st.multiselect(
                    "Filtrer par rareté", options=sorted(cards_df["Rareté"].unique()) if not cards_df.empty else []
                )
                max_level_threshold = st.slider("N'afficher que les cartes de niveau (jeu) ≤", 1, 14, 14)
                view = cards_df[cards_df["Niveau (jeu)"] <= max_level_threshold]
                if rarity_filter:
                    view = view[view["Rareté"].isin(rarity_filter)]
                st.dataframe(view, hide_index=True, use_container_width=False, height=_table_height(len(view)))
        except api.ClashAPIError as exc:
            st.error(str(exc))


def render(ctx: dict) -> None:
    st.subheader("🛡️ Suivi clan")

    excl_count = compute_pending_exclusions_count(ctx["clan_tag"])
    excl_label = f"🔴 Exclusions 🔴{excl_count}" if excl_count else "🔴 Exclusions"

    # Ordre demandé par Flo (15/08/2026 soir) : "Rapport" en premier. Onglet
    # "Niveaux de cartes" retiré (sera intégré dans une future page Statistiques
    # — voir _render_cards_tab, conservée mais non appelée ici pour l'instant).
    tab_rapport, tab_exclusions, tab_promotions = st.tabs(
        ["📊 Rapport (stats GDC en cours)", excl_label, "⭐ Promotions"]
    )

    with tab_rapport:
        _render_rapport_tab(ctx)

    with tab_exclusions:
        _render_exclusions_tab(ctx)

    with tab_promotions:
        _render_promotions_tab(ctx)
