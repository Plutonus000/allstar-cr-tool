"""
app.py — Outil local/partagé ALLSTAR Belgium : gestion et suivi du clan Clash Royale.

Lancement : `streamlit run app.py` (ou via run_app.bat sous Windows).
Données : API officielle Supercell, via le proxy RoyaleAPI (voir clash_api.py).
"""

from __future__ import annotations

import streamlit as st
from streamlit_option_menu import option_menu

import auth
import clash_api as api
import data
from views import accounts_admin, cards, profile, ranking, requests_admin, stats, suivi

st.set_page_config(page_title="ALLSTAR — Clash Royale", page_icon="⚔️", layout="wide")

# Petite couche de style pour un rendu plus "pro" — palette cohérente avec les
# graphiques (voir views/stats.py), sidebar plus aérée, en-tête avec un vrai
# bloc visuel plutôt qu'un simple titre texte.
st.markdown(
    """
    <style>
    section[data-testid="stSidebar"] {
        background-color: #f7f9fc;
        border-right: 1px solid #e6eaf0;
    }
    section[data-testid="stSidebar"] .block-container {
        padding-top: 1.2rem;
    }
    .allstar-sidebar-header {
        padding: 4px 4px 14px 4px;
        margin-bottom: 6px;
        border-bottom: 1px solid #e6eaf0;
    }
    .allstar-sidebar-header h1 {
        font-size: 1.35rem;
        font-weight: 700;
        margin: 0 0 2px 0;
        color: #16213e;
    }
    .allstar-sidebar-header p {
        font-size: 0.85rem;
        color: #5b6472;
        margin: 0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

display_name = auth.require_login()  # bloque tant que non connecté
role = auth.current_role()  # recalculé à chaque run, jamais stocké
is_chef = auth.is_chef_role(role)

ctx = {
    "clan_tag": api.DEFAULT_CLAN_TAG,
    "username": st.session_state.get("username"),
    "display_name": display_name,
    "player_tag": st.session_state.get("player_tag"),
    "role": role,
    "is_chef": is_chef,
}

# ---------------------------------------------------------------------------
# Sidebar — navigation principale
# ---------------------------------------------------------------------------

ROLE_LABELS = {"member": "Membre", "elder": "Aîné", "coLeader": "Co-chef", "leader": "Chef"}

PAGE_DEFS = [
    {"label": "Mon profil", "icon": "house", "render": profile.render, "chef_only": False},
    {"label": "Classement", "icon": "trophy", "render": ranking.render, "chef_only": False},
    {"label": "Statistiques", "icon": "bar-chart-line", "render": stats.render, "chef_only": False},
    {"label": "Suivi clan", "icon": "shield-exclamation", "render": suivi.render, "chef_only": True},
    {"label": "Niveaux de cartes", "icon": "layers", "render": cards.render, "chef_only": True},
    {"label": "Demandes d'accès", "icon": "inbox", "render": requests_admin.render, "chef_only": True},
    {"label": "Comptes", "icon": "people", "render": accounts_admin.render, "chef_only": True},
]
visible_pages = [p for p in PAGE_DEFS if not p["chef_only"] or is_chef]

with st.sidebar:
    st.markdown(
        f"""
        <div class="allstar-sidebar-header">
            <h1>⚔️ ALLSTAR Belgium</h1>
            <p>Connecté en tant que <b>{display_name}</b> — {ROLE_LABELS.get(role, role or "?")}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if role is None:
        st.warning("Rôle clan introuvable — statut recalculé au prochain rafraîchissement.")

    auth.logout_button()
    if st.button("🔄 Rafraîchir les données", use_container_width=True):
        data.clear_all()
        st.session_state.pop("cards_data", None)
        st.rerun()

    st.markdown("")

    selected_label = option_menu(
        menu_title=None,
        options=[p["label"] for p in visible_pages],
        icons=[p["icon"] for p in visible_pages],
        default_index=0,
        styles={
            "container": {"padding": "0", "background-color": "transparent"},
            "icon": {"color": "#2a78d6", "font-size": "16px"},
            "nav-link": {
                "font-size": "15px",
                "text-align": "left",
                "margin": "3px 0",
                "padding": "11px 14px",
                "border-radius": "10px",
                "--hover-color": "#eaf1fb",
            },
            "nav-link-selected": {
                "background-color": "#2a78d6",
                "font-weight": "600",
                "color": "white",
            },
        },
    )

    st.markdown("---")
    st.caption("Données via l'API officielle Supercell (proxy RoyaleAPI).")

selected_page = next(p for p in visible_pages if p["label"] == selected_label)

# ---------------------------------------------------------------------------
# Contenu de la page sélectionnée
# ---------------------------------------------------------------------------

selected_page["render"](ctx)
