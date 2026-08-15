"""views/suggestions.py — Suggestions & bugs (visible par tous).

N'importe quel joueur connecté peut logger une suggestion d'amélioration ou un
bug (demande de Flo, 15/08/2026 soir — remplace le "contacte-moi directement"
de l'onglet Aide). Seul l'admin (statut propre à l'outil, voir auth.is_admin —
PAS le rôle chef en jeu) voit l'ensemble des suggestions envoyées par tout le
monde ; les autres joueurs ("users") ne voient que les leurs.
"""

from __future__ import annotations

import streamlit as st

import fmt
import storage

CATEGORIES = ["🐞 Bug", "💡 Suggestion d'amélioration", "❓ Autre"]


def _norm(tag: str) -> str:
    return (tag or "").strip().upper().lstrip("#")


def _submit_form(ctx: dict) -> None:
    st.markdown("### ✍️ Envoyer une suggestion ou signaler un bug")
    with st.form("suggestion_form", clear_on_submit=True):
        category = st.selectbox("Type", options=CATEGORIES)
        message = st.text_area(
            "Ton message",
            placeholder="Décris le bug ou ton idée d'amélioration le plus précisément possible...",
        )
        submitted = st.form_submit_button("Envoyer")

    if submitted:
        if not message.strip():
            st.error("Le message ne peut pas être vide.")
        else:
            storage.add_suggestion(
                player_tag=ctx.get("player_tag", ""),
                player_name=ctx.get("display_name", "?"),
                username=ctx.get("username", "?"),
                category=category,
                message=message.strip(),
            )
            st.success("Merci ! Ta suggestion a bien été envoyée.")
            st.rerun()


def _render_entry(s: dict, show_author: bool) -> None:
    with st.container(border=True):
        header = s.get("category", "❓ Autre")
        if show_author:
            header += f" — **{s.get('player_name', '?')}**"
        st.markdown(header)
        st.caption(fmt.format_date(s.get("submitted_at", ""), with_time=True))
        st.write(s.get("message", ""))


def render(ctx: dict) -> None:
    st.subheader("💡 Suggestions & bugs")
    st.caption(
        "Une idée pour améliorer l'outil ? Un bug rencontré ? Log-le ici plutôt que par un "
        "autre canal — ça permet de garder une trace propre de tout ce qui a été remonté."
    )

    _submit_form(ctx)

    st.markdown("---")

    all_suggestions = storage.get_suggestions()

    if ctx.get("is_admin"):
        st.markdown(f"### 📋 Toutes les suggestions ({len(all_suggestions)})")
        st.caption("Visible uniquement par l'admin.")
        if not all_suggestions:
            st.info("Aucune suggestion envoyée pour l'instant.")
        else:
            for s in sorted(all_suggestions, key=lambda s: s.get("submitted_at", ""), reverse=True):
                _render_entry(s, show_author=True)
    else:
        my_tag = _norm(ctx.get("player_tag", ""))
        mine = [s for s in all_suggestions if _norm(s.get("player_tag", "")) == my_tag]
        st.markdown(f"### 📋 Tes suggestions envoyées ({len(mine)})")
        if not mine:
            st.info("Tu n'as pas encore envoyé de suggestion.")
        else:
            for s in sorted(mine, key=lambda s: s.get("submitted_at", ""), reverse=True):
                _render_entry(s, show_author=False)
