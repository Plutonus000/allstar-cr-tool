"""views/suivi.py — Suivi clan : alertes règlement + promotions éligibles (chef uniquement)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import clash_api as api
import data
import fmt
import progression


def render(ctx: dict) -> None:
    st.subheader("🚨 Suivi clan")
    clan_tag = ctx["clan_tag"]

    tab_alertes, tab_promotions = st.tabs(["⚠️ Alertes", "⭐ Promotions"])

    with tab_alertes:
        st.caption("Joueurs n'ayant pas joué tous leurs decks sur la dernière GDC.")
        try:
            race_log = data.load_race_log(clan_tag, limit=10)
            violations = progression.find_rule_violations(race_log, clan_tag, n_races=1)
            if not violations:
                st.success("Aucune alerte — tout le monde a joué ses decks sur la dernière GDC. 🎉")
            else:
                df = pd.DataFrame(
                    [
                        {
                            "Joueur": v["name"],
                            "Decks joués": v["decks_used"],
                            "Decks attendus": v["decks_expected"],
                            "GDC": f"#{v['seasonId']} — {fmt.format_date(v['createdDate'])}",
                        }
                        for v in violations
                    ]
                ).sort_values("Decks joués")
                st.dataframe(df, use_container_width=True, hide_index=True)
        except api.ClashAPIError as exc:
            st.error(str(exc))

    with tab_promotions:
        st.caption(
            f"Joueurs ayant atteint {progression.ELDER_WEEKS_REQUIRED} semaines à 100% (éligibles Aîné) ou "
            f"{progression.COLEADER_WEEKS_REQUIRED} semaines à 100% (éligibles Co-chef). "
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
                st.dataframe(df, use_container_width=True, hide_index=True)
        except api.ClashAPIError as exc:
            st.error(str(exc))
