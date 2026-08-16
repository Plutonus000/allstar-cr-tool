"""views/accounts_admin.py — vue d'ensemble des comptes (admin uniquement).

Réservé au statut admin (voir auth.is_admin) — PAS aux chefs/chefs adjoints en
général, demande explicite de Flo (15/08/2026 soir) : "tous les autres sont
des users"."""

from __future__ import annotations

import pandas as pd
import streamlit as st

import fmt
import storage
import table_style as ts


def render(ctx: dict) -> None:
    st.subheader("👥 Suivi Comptes")

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
            "Admin": "🔑" if storage.account_is_admin(a) else "",
            "Créé le": fmt.format_date(a.get("created_at", ""), with_time=True),
            "Révoqué le": fmt.format_date(a.get("revoked_at", ""), with_time=True),
            "Raison révocation": a.get("revoked_reason", ""),
        }
        for a in accounts.values()
    ]
    df = pd.DataFrame(rows).sort_values("Nom", key=lambda s: s.str.lower())

    only_active = st.checkbox("N'afficher que les comptes actifs", value=True)
    view = df[df["Statut"] == "active"] if only_active else df
    # Colonnes resserrées sur mobile (demande de Flo, 16/08/2026 soir) — voir
    # table_style.mobile_column_config().
    st.dataframe(
        view, use_container_width=True, hide_index=True,
        column_config=ts.mobile_column_config(list(view.columns)),
    )

    st.markdown("---")
    st.markdown("**Gérer le statut admin**")
    st.caption(
        "L'admin a accès à cet onglet Suivi Comptes et voit toutes les suggestions envoyées par "
        "les autres joueurs (onglet 💡 Suggestions). Tous les autres comptes sont des \"users\" "
        "— même un chef/chef adjoint n'a pas ces accès sans le statut admin."
    )
    # Contrairement à la révocation ci-dessous, ton propre compte reste
    # sélectionnable ICI : tu dois pouvoir te confirmer explicitement le
    # statut admin toi-même (notamment la toute première fois, tant que tu
    # es admin uniquement via le filet de sécurité "pseudo Plutonus" — voir
    # auth.is_admin / auth._BOOTSTRAP_ADMIN_NAME). Seul le RETRAIT de ton
    # propre statut est bloqué juste en dessous, pour ne pas te fermer
    # l'accès à cet onglet.
    all_active_usernames = sorted(
        (a["username"] for a in accounts.values() if a.get("status") == "active"),
        key=str.lower,
    )
    if all_active_usernames:
        col1, col2 = st.columns([2, 3])
        with col1:
            admin_target = st.selectbox("Compte", options=all_active_usernames, key="admin_target_select")
        target_is_admin = storage.account_is_admin(accounts[admin_target])
        is_self = admin_target == ctx.get("username")
        with col2:
            st.write("")
            if target_is_admin:
                if is_self:
                    st.caption("Tu ne peux pas te retirer toi-même le statut admin (pour ne pas te bloquer l'accès à cet onglet).")
                elif st.button(f"🔒 Retirer le statut admin à {admin_target}"):
                    storage.set_admin_status(admin_target, False)
                    st.success(f"{admin_target} n'est plus admin.")
                    st.rerun()
            else:
                if st.button(f"🔑 Rendre {admin_target} admin"):
                    storage.set_admin_status(admin_target, True)
                    st.success(f"{admin_target} est maintenant admin.")
                    st.rerun()
    else:
        st.caption("Aucun compte actif.")

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
        target = col1.selectbox("Compte", options=active_usernames, key="revoke_target_select")
        reason = col2.text_input("Raison (optionnel)")
        if st.button("🚫 Révoquer cet accès"):
            storage.revoke_account(target, reason or "Révoqué manuellement par un admin")
            st.success(f"Accès de '{target}' révoqué.")
            st.rerun()
    else:
        st.caption("Aucun autre compte actif à révoquer.")
    st.caption("ℹ️ Ton propre compte n'est pas révocable depuis cet écran, pour éviter de te bloquer toi-même.")

    st.caption(f"Stockage actif : **{storage.backend_name()}**")
