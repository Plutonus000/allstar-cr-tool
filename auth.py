"""
auth.py — mur de connexion + gestion des accès (indépendant de Streamlit Cloud).

Principes :
- Les comptes/demandes vivent dans storage.py (JSON local ou Google Sheets).
- Le rôle (chef ou non) n'est JAMAIS stocké : il est recalculé à chaque script
  run depuis les données live du clan, pour qu'une promotion/rétrogradation
  in-game se répercute sans délai dans l'appli.
- Un joueur qui a quitté le clan est détecté au moment où il essaie de se
  connecter (pas de révocation silencieuse en tâche de fond) — voir
  check_membership_at_login().
"""

from __future__ import annotations

import secrets as pysecrets
import time
from typing import Optional

import bcrypt
import streamlit as st

import clash_api as api
import storage

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60

CHEF_ROLES = {"leader", "coLeader"}

# ---------------------------------------------------------------------------
# Session "grace period" — évite de redemander le mot de passe à chaque
# rafraîchissement de page. Le token vit en mémoire (perdu si le serveur
# Streamlit redémarre) et est porté par l'URL (?session=...) plutôt que par
# st.session_state, qui lui ne survit pas à un rechargement complet du
# navigateur. Ce n'est pas une persistance "pour toujours" (pas de cookie),
# mais ça couvre les rafraîchissements/redémarrages de session courants.
# ---------------------------------------------------------------------------

_ACTIVE_SESSIONS: dict[str, str] = {}  # token -> username


def _issue_session_token(username: str) -> str:
    token = pysecrets.token_urlsafe(24)
    _ACTIVE_SESSIONS[token] = username
    return token


def _revoke_session_token(token: Optional[str]) -> None:
    if token:
        _ACTIVE_SESSIONS.pop(token, None)


def _restore_session_from_token() -> bool:
    """Si l'URL porte un token de session valide, restaure l'état connecté."""
    token = st.query_params.get("session")
    username = _ACTIVE_SESSIONS.get(token) if token else None
    if not username:
        return False

    account = storage.get_accounts().get(username)
    if not account or account.get("status") != "active":
        _revoke_session_token(token)
        return False

    st.session_state["authenticated"] = True
    st.session_state["username"] = username
    st.session_state["display_name"] = account.get("name", username)
    st.session_state["player_tag"] = account["player_tag"]
    st.session_state["session_token"] = token
    return True


# ---------------------------------------------------------------------------
# Données clan live (rôle, appartenance) — jamais stockées, toujours recalculées
# ---------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False)
def _cached_clan_members(clan_tag: str) -> list[dict]:
    return api.get_clan_members(clan_tag)


def _norm_tag(tag: str) -> str:
    return tag.strip().upper().lstrip("#")


def find_clan_member(player_tag: str, clan_tag: Optional[str] = None) -> Optional[dict]:
    """
    Renvoie la fiche membre (avec son 'role' actuel) si player_tag est bien
    dans le clan, None s'il n'y est pas. Lève ClashAPIError si l'API est
    injoignable (à distinguer explicitement d'un "n'est pas dans le clan").
    """
    clan_tag = clan_tag or api.DEFAULT_CLAN_TAG
    members = _cached_clan_members(clan_tag)  # peut lever ClashAPIError
    target = _norm_tag(player_tag)
    return next((m for m in members if _norm_tag(m.get("tag", "")) == target), None)


def get_current_role(player_tag: str, clan_tag: Optional[str] = None) -> Optional[str]:
    """Rôle actuel ('member'/'elder'/'coLeader'/'leader') ou None si indisponible/absent."""
    try:
        member = find_clan_member(player_tag, clan_tag)
    except api.ClashAPIError:
        return None
    return member.get("role") if member else None


def is_chef_role(role: Optional[str]) -> bool:
    return role in CHEF_ROLES


# ---------------------------------------------------------------------------
# Connexion
# ---------------------------------------------------------------------------

def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _check_membership_at_login(player_tag: str) -> tuple[bool, str]:
    """
    Vérifie l'appartenance au clan au moment de la connexion.
    Renvoie (ok, message_erreur). Ne révoque QUE si on a une réponse claire
    de l'API indiquant que le joueur n'est plus dans le clan (jamais sur une
    simple erreur réseau/API, pour éviter les faux positifs).
    """
    try:
        member = find_clan_member(player_tag)
    except api.ClashAPIError as exc:
        return False, f"Impossible de vérifier ton statut clan pour le moment ({exc}). Réessaie dans un instant."

    if member is None:
        return False, "Tu ne fais plus partie du clan ALLSTAR Belgium — l'accès à l'outil a été retiré."

    return True, ""


def _do_login(username: str, password: str) -> tuple[bool, str]:
    accounts = storage.get_accounts()
    account = accounts.get(username)
    if not account or account.get("status") != "active":
        return False, "Identifiant ou mot de passe incorrect."
    if not _verify_password(password, account.get("password_hash", "")):
        return False, "Identifiant ou mot de passe incorrect."

    ok, message = _check_membership_at_login(account["player_tag"])
    if not ok:
        # Résultat clair (pas une erreur réseau) => on marque le compte révoqué.
        if "plus partie du clan" in message:
            storage.revoke_account(username, "Plus membre du clan (détecté à la connexion)")
        return False, message

    st.session_state["authenticated"] = True
    st.session_state["username"] = username
    st.session_state["display_name"] = account.get("name", username)
    st.session_state["player_tag"] = account["player_tag"]
    st.session_state["login_attempts"] = 0

    token = _issue_session_token(username)
    st.session_state["session_token"] = token
    st.query_params["session"] = token
    return True, ""


def current_role() -> Optional[str]:
    """À appeler à chaque run pour avoir le rôle à jour (pas mis en cache en session)."""
    player_tag = st.session_state.get("player_tag")
    if not player_tag:
        return None
    return get_current_role(player_tag)


def is_chef() -> bool:
    return is_chef_role(current_role())


# ---------------------------------------------------------------------------
# Demande d'accès
# ---------------------------------------------------------------------------

def _request_access_form() -> None:
    st.subheader("Demander un accès")
    st.caption(
        "Renseigne ton pseudo Clash Royale exact et choisis un mot de passe. "
        "Un chef devra valider ta demande avant que tu puisses te connecter."
    )
    with st.form("request_access_form"):
        pseudo = st.text_input("Pseudo Clash Royale")
        password = st.text_input("Choisis un mot de passe", type="password")
        confirm = st.text_input("Confirme le mot de passe", type="password")
        submitted = st.form_submit_button("Envoyer la demande")

    if submitted:
        if not pseudo.strip():
            st.error("Le pseudo ne peut pas être vide.")
        elif len(password) < 8:
            st.error("Mot de passe trop court (8 caractères minimum).")
        elif password != confirm:
            st.error("Les deux mots de passe ne correspondent pas.")
        else:
            password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            storage.add_access_request(pseudo.strip(), password_hash)
            st.success("Demande envoyée ! Un chef doit la valider avant que tu puisses te connecter.")

    if st.button("← Retour à la connexion"):
        st.session_state["show_request_form"] = False
        st.rerun()


def require_login() -> str:
    """
    Affiche connexion / demande d'accès tant que non authentifié.
    Renvoie le nom affiché une fois connecté ; bloque (st.stop()) sinon.
    """
    if st.session_state.get("authenticated"):
        return st.session_state.get("display_name", st.session_state.get("username", "?"))

    if _restore_session_from_token():
        return st.session_state.get("display_name", st.session_state.get("username", "?"))

    st.session_state.setdefault("login_attempts", 0)
    st.session_state.setdefault("locked_until", 0.0)
    st.session_state.setdefault("show_request_form", False)

    gate = st.empty()

    with gate.container():
        st.title("🔒 ALLSTAR — Connexion")

        if st.session_state["show_request_form"]:
            _request_access_form()
            st.stop()

        now = time.time()
        if now < st.session_state["locked_until"]:
            remaining = int(st.session_state["locked_until"] - now)
            st.error(f"Trop de tentatives échouées. Réessaie dans {remaining} secondes.")
            st.stop()

        with st.form("login_form"):
            username = st.text_input("Identifiant")
            password = st.text_input("Mot de passe", type="password")
            submitted = st.form_submit_button("Se connecter")

        if submitted:
            ok, message = _do_login(username, password)
            if ok:
                gate.empty()
                st.rerun()
            else:
                st.session_state["login_attempts"] += 1
                if st.session_state["login_attempts"] >= MAX_ATTEMPTS:
                    st.session_state["locked_until"] = time.time() + LOCKOUT_SECONDS
                    st.session_state["login_attempts"] = 0
                    st.error(f"Trop de tentatives échouées. Réessaie dans {LOCKOUT_SECONDS} secondes.")
                else:
                    st.error(message)

        st.caption("Pas encore de compte ?")
        if st.button("Demander mon accès"):
            st.session_state["show_request_form"] = True
            st.rerun()

    st.stop()


def logout_button() -> None:
    if st.sidebar.button("🚪 Se déconnecter"):
        _revoke_session_token(st.session_state.get("session_token"))
        st.query_params.pop("session", None)
        for key in ("authenticated", "username", "display_name", "player_tag", "session_token"):
            st.session_state.pop(key, None)
        st.rerun()
