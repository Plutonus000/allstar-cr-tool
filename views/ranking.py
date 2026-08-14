"""views/ranking.py — Classement (moyenne Fame), GDC en cours, Historique GDC."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import clash_api as api
import data
import fmt
import logic


def render(ctx: dict) -> None:
    st.subheader("🏆 Classement")
    clan_tag = ctx["clan_tag"]

    tab_classement, tab_cours, tab_historique = st.tabs(["Classement", "GDC en cours", "Historique GDC"])

    with tab_classement:
        st.caption(
            "Classement basé sur la **Fame** (points de participation individuels en GDC) — "
            "c'est la donnée la plus proche des « trophées gagnés » disponible par joueur via l'API officielle."
        )
        max_available = st.session_state.get("_race_log_max_len", 10)
        n_races = st.slider("Nombre de GDC prises en compte", min_value=1, max_value=max(max_available, 10), value=min(10, max_available))
        try:
            race_log = data.load_race_log(clan_tag, limit=max(n_races, 10))
            st.session_state["_race_log_max_len"] = len(race_log) or 10
            ranking_df = logic.compute_ranking(race_log, clan_tag, n_races)
            if ranking_df.empty:
                st.info("Aucune donnée d'historique GDC trouvée pour ce clan.")
            else:
                name_filter = st.text_input("Filtrer par nom", key="filter_ranking")
                min_gdc = st.slider("GDC jouées minimum", 0, n_races, 0)
                filtered = ranking_df[ranking_df["GDC jouées"] >= min_gdc]
                if name_filter:
                    filtered = filtered[filtered["Joueur"].str.contains(name_filter, case=False, na=False)]
                st.dataframe(filtered, use_container_width=True, hide_index=True)
                st.caption(f"{len(filtered)} joueur(s) affiché(s) sur {len(ranking_df)} — {len(race_log)} GDC disponibles via l'API.")
        except api.ClashAPIError as exc:
            st.error(str(exc))

    with tab_cours:
        try:
            current = data.load_current_race(clan_tag)
            st.caption(f"État : {current.get('state', '?')}")
            df_cur = logic.compute_current_race_table(current)
            if df_cur.empty:
                st.info("Pas de GDC en cours actuellement (ou données indisponibles).")
            else:
                df_cur = df_cur.sort_values("Joueur", key=lambda s: s.str.lower())
                search = st.text_input("Filtrer par nom", key="filter_cur_race")
                view = df_cur[df_cur["Joueur"].str.contains(search, case=False, na=False)] if search else df_cur
                st.dataframe(view, use_container_width=True, hide_index=True)
        except api.ClashAPIError as exc:
            st.error(str(exc))

    with tab_historique:
        try:
            race_log = data.load_race_log(clan_tag, limit=10)
            if not race_log:
                st.info("Aucun historique disponible.")
            else:
                labels = [f"GDC #{item.get('seasonId', '?')} — {fmt.format_date(item.get('createdDate', ''))}" for item in race_log]
                idx = st.selectbox("Choisir une GDC", options=range(len(labels)), format_func=lambda i: labels[i])
                item = race_log[idx]
                standings_df = pd.DataFrame(
                    [
                        {
                            "Rang": s.get("rank"),
                            "Clan": s.get("clan", {}).get("name", "?"),
                            "Fame": s.get("clan", {}).get("fame", 0),
                            "Δ Trophées (clan)": s.get("trophyChange", 0),
                        }
                        for s in item.get("standings", [])
                    ]
                ).sort_values("Rang")
                st.dataframe(standings_df, use_container_width=True, hide_index=True)

                our_standing = next(
                    (s for s in item.get("standings", []) if logic.norm_tag(s.get("clan", {}).get("tag", "")) == logic.norm_tag(clan_tag)),
                    None,
                )
                if our_standing:
                    st.markdown("**Détail par joueur (notre clan) :**")
                    detail_df = pd.DataFrame(
                        [
                            {
                                "Joueur": p.get("name", "?"),
                                "Decks joués": p.get("decksUsed", 0),
                                "Fame": p.get("fame", 0),
                                "Attaques bateau adverse": p.get("boatAttacks", 0),
                            }
                            for p in our_standing["clan"].get("participants", [])
                        ]
                    ).sort_values("Decks joués", ascending=False)
                    st.dataframe(detail_df, use_container_width=True, hide_index=True)
        except api.ClashAPIError as exc:
            st.error(str(exc))
