"""Tests de la logique auth.py avec l'API mockée (pas d'appel réseau réel)."""
from unittest.mock import patch

import bcrypt

import auth
import clash_api as api
import storage


def _reset():
    storage.ACCOUNTS_FILE.write_text("{}")
    storage.REQUESTS_FILE.write_text("[]")


def _make_account(username="flo", player_tag="#ABC123", password="testpass123"):
    h = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    return storage.create_account(username, "Flo", h, player_tag)


# --- cas 1 : joueur toujours dans le clan, rôle membre simple ---
_reset()
_make_account()
with patch.object(auth, "find_clan_member", return_value={"tag": "#ABC123", "role": "member"}):
    ok, msg = auth._check_membership_at_login("#ABC123")
    assert ok is True, msg
print("cas 1 (toujours dans le clan) OK")

# --- cas 2 : joueur plus dans le clan -> refus + révocation ---
_reset()
_make_account()
with patch.object(auth, "find_clan_member", return_value=None):
    ok, msg = auth._do_login("flo", "testpass123")
    assert ok is False
    assert "plus partie du clan" in msg
    assert storage.get_accounts()["flo"]["status"] == "revoked"
print("cas 2 (a quitté le clan -> révoqué) OK")

# --- cas 3 : API injoignable -> refus SANS révocation (pas de faux positif) ---
_reset()
_make_account()
with patch.object(auth, "find_clan_member", side_effect=api.ClashAPIError("panne réseau simulée")):
    ok, msg = auth._do_login("flo", "testpass123")
    assert ok is False
    assert "Impossible de vérifier" in msg
    assert storage.get_accounts()["flo"]["status"] == "active"  # pas révoqué !
print("cas 3 (API en panne -> pas de révocation) OK")

# --- cas 4 : mauvais mot de passe ---
_reset()
_make_account()
with patch.object(auth, "find_clan_member", return_value={"tag": "#ABC123", "role": "member"}):
    ok, msg = auth._do_login("flo", "mauvais_mdp")
    assert ok is False
    assert "authenticated" not in auth.st.session_state if hasattr(auth, "st") else True
print("cas 4 (mauvais mot de passe) OK")

# --- cas 5 : is_chef_role ---
assert auth.is_chef_role("leader") is True
assert auth.is_chef_role("coLeader") is True
assert auth.is_chef_role("elder") is False
assert auth.is_chef_role("member") is False
assert auth.is_chef_role(None) is False
print("cas 5 (is_chef_role) OK")

# --- cas 6 : compte révoqué ne peut plus se connecter même avec bon mdp ---
_reset()
_make_account()
storage.revoke_account("flo", "test")
with patch.object(auth, "find_clan_member", return_value={"tag": "#ABC123", "role": "member"}):
    ok, msg = auth._do_login("flo", "testpass123")
    assert ok is False
print("cas 6 (compte révoqué -> refus) OK")

# --- cas 7 : flux demande d'accès -> approbation -> nouveau compte actif ---
_reset()
req = storage.add_access_request("Joueur2", bcrypt.hashpw(b"pass12345", bcrypt.gensalt()).decode())
account = storage.approve_access_request(req["id"], "#XYZ999", matched_by="flo")
assert account["status"] == "active"
assert account["player_tag"] == "#XYZ999"
with patch.object(auth, "find_clan_member", return_value={"tag": "#XYZ999", "role": "member"}):
    ok, msg = auth._do_login(account["username"], "pass12345")
    assert ok is True, msg
print("cas 7 (demande -> approbation -> connexion) OK")

_reset()
print("\nTOUS LES TESTS AUTH PASSENT")
