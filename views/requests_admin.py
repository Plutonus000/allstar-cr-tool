"""views/requests_admin.py — file d'attente des demandes d'accès (chef uniquement)."""

from __future__ import annotations

import streamlit as st

import data
import fmt
import storage


def _norm(s: str) -> str:
    return "".join(c.lower() for c in s.strip() if c.isalnum())


def _linked_player_tags(accounts: dict) -> set[str]:
    return {
        a["player_tag"].strip().upper().lstrip("#")
        for a in accounts.values()
        if a.get("status") == "active" and a.get("player_tag")
    }


def render(ctx: dict) -> None:
    st.subheader("📥 Demandes d'accès")

    accounts = storage.get_accounts()
    linked_tags = _linked_player_tags(accounts)

    try:
        members = data.load_clan_members(ctx["clan_tag"])
    except Exception as exc:  # ClashAPIError
        st.error(f"Impossible de charger les membres du clan : {exc}")
        members = []

    unlinked_members = [m for m in members if m.get("tag", "").strip().upper().lstrip("#") not in linked_tags]

    requests_ = storage.get_access_requests()
    pending = [r for r in requests_ if r.get("status") == "pending"]
    processed = [r for r in requests_ if r.get("status") != "pending"]

    if not pending:
        st.info("Aucune demande en attente.")
    else:
        st.caption(f"{len(pending)} demande(s) en attente.")

    for req in sorted(pending, key=lambda r: r.get("requested_at", ""), reverse=True):
        with st.container(border=True):
            col1, col2 = st.columns([2, 3])
            with col1:
                st.markdown(f"**{req['pseudo_submitted']}**")
                st.caption(f"Demandé le {fmt.format_date(req.get('requested_at', ''), with_time=True)}")

            # Auto-match : nom exact (normalisé) parmi les membres non liés
            exact_match = next(
                (m for m in unlinked_members if _norm(m.get("name", "")) == _norm(req["pseudo_submitted"])),
                None,
            )

            with col2:
                if exact_match:
                    st.success(f"Correspondance trouvée : **{exact_match['name']}** ({exact_match['tag']})")
                    bcol1, bcol2 = st.columns(2)
                    if bcol1.button("✅ Confirmer ce lien", key=f"confirm_{req['id']}"):
                        storage.approve_access_request(req["id"], exact_match["tag"], matched_by=ctx["username"])
                        st.rerun()
                    if bcol2.button("❌ Rejeter la demande", key=f"reject_exact_{req['id']}"):
                        storage.reject_access_request(req["id"], rejected_by=ctx["username"])
                        st.rerun()
                else:
                    if not unlinked_members:
                        st.warning("Aucun membre du clan disponible pour un lien manuel (tous déjà liés, ou clan vide).")
                    else:
                        unlinked_sorted = sorted(unlinked_members, key=lambda m: (m.get("name") or "").lower())
                        options = {f"{m['name']} ({m['tag']})": m["tag"] for m in unlinked_sorted}
                        choice = st.selectbox(
                            "Aucune correspondance auto — choisis le bon pseudo :",
                            options=list(options.keys()),
                            key=f"select_{req['id']}",
                        )
                        bcol1, bcol2 = st.columns(2)
                        if bcol1.button("✅ Lier ce compte", key=f"link_{req['id']}"):
                            storage.approve_access_request(req["id"], options[choice], matched_by=ctx["username"])
                            st.rerun()
                        if bcol2.button("❌ Rejeter la demande", key=f"reject_manual_{req['id']}"):
                            storage.reject_access_request(req["id"], rejected_by=ctx["username"])
                            st.rerun()

    if processed:
        with st.expander(f"Historique ({len(processed)} demande(s) traitée(s))"):
            for req in sorted(processed, key=lambda r: r.get("requested_at", ""), reverse=True):
                status_icon = "✅" if req["status"] == "matched" else "❌"
                st.write(
                    f"{status_icon} **{req['pseudo_submitted']}** — {req['status']} "
                    f"le {fmt.format_date(req.get('matched_at', ''), with_time=True)} par {req.get('matched_by', '?')}"
                )
