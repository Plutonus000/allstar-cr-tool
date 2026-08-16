"""views/player_watch.py — Suivi joueur (chefs uniquement).

Affiche la même page que "🏠 Mon profil", mais pour n'importe quel membre du
clan choisi par un chef — réutilise entièrement views/profile.render() via son
paramètre `viewed_player` plutôt que de dupliquer la logique (demande de Flo,
16/08/2026 : "possibilité de sélectionner un joueur du clan dans la liste et
ça affiche l'équivalent de la page 'Mon profil' de ce joueur")."""

from __future__ import annotations

import streamlit as st

import clash_api as api
import data
from views import profile


def render(ctx: dict) -> None:
    st.subheader("🔍 Suivi joueur")
    st.caption(
        "Affiche la même page que « Mon profil », pour le membre du clan de ton choix — "
        "progression, taux de participation, avertissements/grâces en cours, etc."
    )

    clan_tag = ctx["clan_tag"]
    try:
        members = data.load_clan_members(clan_tag)
    except api.ClashAPIError as exc:
        st.error(str(exc))
        return

    if not members:
        st.info("Aucun membre trouvé pour ce clan.")
        return

    members_sorted = sorted(members, key=lambda m: (m.get("name") or "").lower())
    options = {f"{m.get('name', '?')} ({m.get('tag', '?')})": m for m in members_sorted}
    choice = st.selectbox("Choisir un joueur", options=list(options.keys()))
    if not choice:
        return

    member = options[choice]
    viewed_player = {
        "player_tag": member.get("tag", ""),
        "display_name": member.get("name", "?"),
        "role": member.get("role"),
    }

    st.markdown("---")
    profile.render(ctx, viewed_player=viewed_player)
