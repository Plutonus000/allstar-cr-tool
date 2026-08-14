"""
storage.py — couche de stockage pour les comptes et les demandes d'accès.

Deux backends, même interface :
- **local** (fichiers JSON `accounts.json` / `access_requests.json`) — utilisé
  tant qu'aucun identifiant Google Sheets n'est configuré. Parfait pour
  développer/tester en solo sur un PC.
- **sheets** (Google Sheets via un compte de service) — bascule automatique
  dès que les identifiants sont présents (secrets Streamlit Cloud ou .env
  local). Nécessaire dès que plusieurs personnes utilisent l'appli en même
  temps (le stockage local ne survit pas à un redéploiement Streamlit Cloud).

Le reste de l'appli n'a jamais à savoir lequel des deux est actif.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ACCOUNTS_FILE = Path(__file__).parent / "accounts.json"
REQUESTS_FILE = Path(__file__).parent / "access_requests.json"

ACCOUNTS_SHEET_NAME = "accounts"
REQUESTS_SHEET_NAME = "access_requests"

ACCOUNTS_FIELDS = [
    "username", "name", "password_hash", "player_tag",
    "status", "created_at", "revoked_at", "revoked_reason",
]
REQUEST_FIELDS = [
    "id", "pseudo_submitted", "password_hash", "requested_at", "status",
    "matched_player_tag", "matched_username", "matched_by", "matched_at",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# Résolution du backend
# ---------------------------------------------------------------------------

def _google_credentials() -> Optional[dict]:
    """
    Renvoie les identifiants du compte de service Google (dict) si configurés,
    sinon None (auquel cas on utilise le stockage local).

    Cherche, dans l'ordre :
    - st.secrets["gcp_service_account"] (déploiement Streamlit Cloud, table TOML)
    - variable d'env / .env GOOGLE_SERVICE_ACCOUNT_FILE (chemin vers le JSON téléchargé
      depuis Google Cloud — le plus simple en local, pas besoin de tout mettre sur une ligne)
    - variable d'env / .env GOOGLE_SERVICE_ACCOUNT_JSON (JSON complet en une ligne, utile
      si un fichier séparé n'est pas pratique)
    """
    try:
        import streamlit as st

        if "gcp_service_account" in st.secrets:
            return dict(st.secrets["gcp_service_account"])
    except Exception:
        pass

    file_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "").strip()
    if file_path:
        path = Path(__file__).parent / file_path
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return None

    raw = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if raw:
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


def _sheet_id() -> str:
    try:
        import streamlit as st

        if "GOOGLE_SHEET_ID" in st.secrets:
            return str(st.secrets["GOOGLE_SHEET_ID"])
    except Exception:
        pass
    return os.getenv("GOOGLE_SHEET_ID", "").strip()


def backend_name() -> str:
    return "sheets" if (_google_credentials() and _sheet_id()) else "local"


# ---------------------------------------------------------------------------
# Backend "sheets" (Google Sheets via gspread)
# ---------------------------------------------------------------------------

_sheets_client_cache = {}


def _get_worksheet(name: str, fields: list[str]):
    import gspread
    from google.oauth2.service_account import Credentials

    if "client" not in _sheets_client_cache:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(_google_credentials(), scopes=scopes)
        _sheets_client_cache["client"] = gspread.authorize(creds)

    client = _sheets_client_cache["client"]
    sheet = client.open_by_key(_sheet_id())
    try:
        ws = sheet.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sheet.add_worksheet(title=name, rows=200, cols=len(fields))
        ws.append_row(fields)
        return ws

    # L'onglet existait déjà (créé à la main) — vérifie que la ligne d'en-tête
    # est correcte, et la (ré)écrit sinon. Sans ça, la première donnée envoyée
    # finit par être prise pour des en-têtes, d'où des erreurs en cascade.
    header = ws.row_values(1)
    if header != fields:
        ws.update("A1", [fields])
    return ws


def _sheets_get_accounts() -> dict:
    ws = _get_worksheet(ACCOUNTS_SHEET_NAME, ACCOUNTS_FIELDS)
    records = ws.get_all_records()
    return {r["username"]: r for r in records if r.get("username")}


def _sheets_upsert_account(username: str, account: dict) -> None:
    ws = _get_worksheet(ACCOUNTS_SHEET_NAME, ACCOUNTS_FIELDS)
    records = ws.get_all_records()
    row_values = [str(account.get(f, "")) for f in ACCOUNTS_FIELDS]
    for idx, r in enumerate(records, start=2):  # ligne 1 = en-têtes
        if r.get("username") == username:
            ws.update(f"A{idx}", [row_values])
            return
    ws.append_row(row_values)


def _sheets_get_requests() -> list[dict]:
    ws = _get_worksheet(REQUESTS_SHEET_NAME, REQUEST_FIELDS)
    return ws.get_all_records()


def _sheets_add_request(request: dict) -> None:
    ws = _get_worksheet(REQUESTS_SHEET_NAME, REQUEST_FIELDS)
    ws.append_row([str(request.get(f, "")) for f in REQUEST_FIELDS])


def _sheets_update_request(request_id: str, updates: dict) -> None:
    ws = _get_worksheet(REQUESTS_SHEET_NAME, REQUEST_FIELDS)
    records = ws.get_all_records()
    for idx, r in enumerate(records, start=2):
        if str(r.get("id")) == str(request_id):
            merged = {**r, **updates}
            row_values = [str(merged.get(f, "")) for f in REQUEST_FIELDS]
            ws.update(f"A{idx}", [row_values])
            return
    raise KeyError(f"Demande d'accès introuvable : {request_id}")


# ---------------------------------------------------------------------------
# Backend "local" (fichiers JSON)
# ---------------------------------------------------------------------------

def _local_read(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _local_write(path: Path, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _local_get_accounts() -> dict:
    return _local_read(ACCOUNTS_FILE, {})


def _local_upsert_account(username: str, account: dict) -> None:
    accounts = _local_get_accounts()
    accounts[username] = account
    _local_write(ACCOUNTS_FILE, accounts)


def _local_get_requests() -> list[dict]:
    return _local_read(REQUESTS_FILE, [])


def _local_add_request(request: dict) -> None:
    requests_ = _local_get_requests()
    requests_.append(request)
    _local_write(REQUESTS_FILE, requests_)


def _local_update_request(request_id: str, updates: dict) -> None:
    requests_ = _local_get_requests()
    for r in requests_:
        if r.get("id") == request_id:
            r.update(updates)
            _local_write(REQUESTS_FILE, requests_)
            return
    raise KeyError(f"Demande d'accès introuvable : {request_id}")


# ---------------------------------------------------------------------------
# Interface publique (utilisée par le reste de l'appli)
# ---------------------------------------------------------------------------

def get_accounts() -> dict:
    """username -> account dict"""
    return _sheets_get_accounts() if backend_name() == "sheets" else _local_get_accounts()


def upsert_account(username: str, account: dict) -> None:
    if backend_name() == "sheets":
        _sheets_upsert_account(username, account)
    else:
        _local_upsert_account(username, account)


def create_account(username: str, name: str, password_hash: str, player_tag: str) -> dict:
    account = {
        "username": username,
        "name": name,
        "password_hash": password_hash,
        "player_tag": player_tag,
        "status": "active",
        "created_at": _now_iso(),
        "revoked_at": "",
        "revoked_reason": "",
    }
    upsert_account(username, account)
    return account


def revoke_account(username: str, reason: str) -> None:
    accounts = get_accounts()
    account = accounts.get(username)
    if not account:
        raise KeyError(f"Compte introuvable : {username}")
    account["status"] = "revoked"
    account["revoked_at"] = _now_iso()
    account["revoked_reason"] = reason
    upsert_account(username, account)


def get_access_requests() -> list[dict]:
    return _sheets_get_requests() if backend_name() == "sheets" else _local_get_requests()


def add_access_request(pseudo_submitted: str, password_hash: str) -> dict:
    request = {
        "id": new_request_id(),
        "pseudo_submitted": pseudo_submitted,
        "password_hash": password_hash,
        "requested_at": _now_iso(),
        "status": "pending",
        "matched_player_tag": "",
        "matched_username": "",
        "matched_by": "",
        "matched_at": "",
    }
    if backend_name() == "sheets":
        _sheets_add_request(request)
    else:
        _local_add_request(request)
    return request


def approve_access_request(request_id: str, player_tag: str, matched_by: str) -> dict:
    """
    Valide une demande : crée le compte lié au player_tag choisi (avec le mot de
    passe déjà fourni à la demande) et marque la demande comme traitée.
    """
    requests_ = get_access_requests()
    request = next((r for r in requests_ if str(r.get("id")) == str(request_id)), None)
    if not request:
        raise KeyError(f"Demande introuvable : {request_id}")

    username = _slugify_username(request["pseudo_submitted"])
    account = create_account(
        username=username,
        name=request["pseudo_submitted"],
        password_hash=request["password_hash"],
        player_tag=player_tag,
    )

    updates = {
        "status": "matched",
        "matched_player_tag": player_tag,
        "matched_username": username,
        "matched_by": matched_by,
        "matched_at": _now_iso(),
    }
    if backend_name() == "sheets":
        _sheets_update_request(request_id, updates)
    else:
        _local_update_request(request_id, updates)

    return account


def reject_access_request(request_id: str, rejected_by: str) -> None:
    updates = {"status": "rejected", "matched_by": rejected_by, "matched_at": _now_iso()}
    if backend_name() == "sheets":
        _sheets_update_request(request_id, updates)
    else:
        _local_update_request(request_id, updates)


def _slugify_username(pseudo: str) -> str:
    base = "".join(c.lower() if c.isalnum() else "" for c in pseudo) or "joueur"
    accounts = get_accounts()
    candidate = base
    i = 2
    while candidate in accounts:
        candidate = f"{base}{i}"
        i += 1
    return candidate
