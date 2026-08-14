"""views/cards.py — niveaux de cartes : vue clan + fiche joueur (chef uniquement)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import clash_api as api
import data
import logic


def render(ctx: dict) -> None:
    st.subheader("🃏 Niveaux de cartes")
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
            st.dataframe(view, use_container_width=True, hide_index=True)

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
            manual_tag = st.text_input("...ou saisir un tag joueur directement (optionnel)")
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
                st.dataframe(view, use_container_width=True, hide_index=True)
        except api.ClashAPIError as exc:
            st.error(str(exc))
