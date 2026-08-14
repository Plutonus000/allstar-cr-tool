"""views/accounts_admin.py — vue d'ensemble des comptes (chef uniquement)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import fmt
import storage


def render(ctx: dict) -> None:
    st.subheader("👥 Comptes")

    accounts = storage.get_accounts()
    if not accounts:
        st.info("Aucun compte pour l'instant.")
        return

    rows = [
        {
            "Identifiant": a["username"],
            "Nom": a.get("name", ""),
            "Tag joueur": a.get("player_tag", ""),
            "Statut": a.get("status", ""),
            "Créé le": fmt.format_date(a.get("created_at", ""), with_time=True),
            "Révoqué le": fmt.format_date(a.get("revoked_at", ""), with_time=True),
            "Raison révocation": a.get("revoked_reason", ""),
        }
        for a in accounts.values()
    ]
    df = pd.DataFrame(rows).sort_values("Nom", key=lambda s: s.str.lower())

    only_active = st.checkbox("N'afficher que les comptes actifs", value=True)
    view = df[df["Statut"] == "active"] if only_active else df
    st.dataframe(view, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("**Révoquer un accès manuellement**")
    # Ton propre compte n'apparaît jamais ici : un admin ne doit jamais pouvoir
    # se révoquer lui-même (ça bloquerait l'accès à tout le monde).
    active_usernames = sorted(
        (a["username"] for a in accounts.values() if a.get("status") == "active" and a["username"] != ctx.get("username")),
        key=str.lower,
    )
    if active_usernames:
        col1, col2 = st.columns([2, 3])
        target = col1.selectbox("Compte", options=active_usernames)
        reason = col2.text_input("Raison (optionnel)")
        if st.button("🚫 Révoquer cet accès"):
            storage.revoke_account(target, reason or "Révoqué manuellement par un chef")
            st.success(f"Accès de '{target}' révoqué.")
            st.rerun()
    else:
        st.caption("Aucun autre compte actif à révoquer.")
    st.caption("ℹ️ Ton propre compte n'est pas révocable depuis cet écran, pour éviter de te bloquer toi-même.")

    st.caption(f"Stockage actif : **{storage.backend_name()}**")
