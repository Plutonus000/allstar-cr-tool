"""views/profile.py — "Mon profil" : progression et santé de participation (tous les joueurs)."""

from __future__ import annotations

import streamlit as st

import auth
import clash_api as api
import data
import fmt
import progression

ROLE_LABELS = {
    "member": "Membre",
    "elder": "Aîné",
    "coLeader": "Co-chef",
    "leader": "Chef",
}


def render(ctx: dict) -> None:
    st.subheader("🏠 Mon profil")
    clan_tag = ctx["clan_tag"]
    player_tag = ctx["player_tag"]
    role = ctx["role"]

    st.markdown(f"**{ctx['display_name']}** — {ROLE_LABELS.get(role, role or '?')}")

    try:
        race_log = data.load_race_log(clan_tag, limit=max(progression.COLEADER_WEEKS_REQUIRED, 10))
    except api.ClashAPIError as exc:
        st.error(str(exc))
        return

    streak, history = progression.compute_participation_streak(race_log, player_tag, clan_tag)
    status = progression.eligibility_status(streak)
    rate = progression.participation_rate(race_log, player_tag, clan_tag, n_races=10)

    col1, col2, col3 = st.columns(3)
    col1.metric("Série actuelle (100% assiduité)", f"{streak} semaine(s)")
    col2.metric("Taux de participation (10 dernières GDC)", f"{rate}%" if rate is not None else "—")
    col3.metric("Rôle actuel", ROLE_LABELS.get(role, role or "?"))

    st.markdown("---")

    if role in ("coLeader", "leader"):
        st.success("Tu as déjà le rang maximum suivi ici — rien à débloquer de ce côté. 🎉")
    elif role == "elder":
        st.markdown("**Progression vers Co-chef**")
        st.progress(min(streak / progression.COLEADER_WEEKS_REQUIRED, 1.0))
        if status["coleader_eligible"]:
            st.success(
                f"Tu es éligible au rang Co-chef ({streak} semaines à 100%) — "
                "signale-le à un chef pour qu'il/elle te promeuve en jeu."
            )
        else:
            st.info(f"Encore {status['weeks_to_coleader']} semaine(s) à 100% d'assiduité pour être éligible Co-chef.")
    else:  # member ou rôle inconnu
        st.markdown("**Progression vers Aîné**")
        st.progress(min(streak / progression.ELDER_WEEKS_REQUIRED, 1.0))
        if status["elder_eligible"]:
            st.success(
                f"Tu es éligible au rang Aîné ({streak} semaines à 100%) — "
                "signale-le à un chef pour qu'il/elle te promeuve en jeu."
            )
        else:
            st.info(f"Encore {status['weeks_to_elder']} semaine(s) à 100% d'assiduité pour être éligible Aîné.")

    # Messages d'amélioration
    st.markdown("---")
    st.markdown("**Points à surveiller**")
    if not history:
        st.caption("Pas encore d'historique de GDC disponible.")
    else:
        recent_miss = next((h for h in history if not h["full"]), None)
        if recent_miss is None:
            st.write("✅ Aucun manque détecté sur l'historique disponible — continue comme ça !")
        else:
            if not recent_miss["present"]:
                st.write(
                    f"⚠️ Tu étais absent de la GDC du {fmt.format_date(recent_miss['createdDate'])} — "
                    "ça casse la série pour l'éligibilité Aîné/Co-chef."
                )
            else:
                st.write(
                    f"⚠️ GDC du {fmt.format_date(recent_miss['createdDate'])} : {recent_miss['decks_used']}/16 decks joués — "
                    "pense à jouer tous tes decks chaque jour de GDC pour construire ta série."
                )

    with st.expander("Historique détaillé"):
        for h in history:
            icon = "✅" if h["full"] else ("➖" if not h["present"] else "⚠️")
            label = "absent" if not h["present"] else f"{h['decks_used']}/16 decks"
            st.write(f"{icon} GDC #{h['seasonId']} — {fmt.format_date(h['createdDate'])} — {label}")
