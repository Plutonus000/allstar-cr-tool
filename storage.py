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

Cache (15/08/2026 soir) : les fonctions de LECTURE publiques sont mises en
cache 30 secondes (`st.cache_data`) — sans ça, chaque interaction Streamlit
(l'app entière se réexécute à chaque clic) relit intégralement plusieurs
onglets Google Sheets, ce qui épuise vite le quota gratuit de l'API Sheets
("Quota exceeded... Read requests per minute", constaté par Flo). Chaque
fonction d'ÉCRITURE vide le cache correspondant juste après (`.clear()`)
pour qu'un chef voie immédiatement l'effet de son action, sans attendre 30s.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import streamlit as st

_CACHE_TTL = 30  # secondes

ACCOUNTS_FILE = Path(__file__).parent / "accounts.json"
REQUESTS_FILE = Path(__file__).parent / "access_requests.json"
SEASONS_FILE = Path(__file__).parent / "race_log_seasons.json"
PARTICIPANTS_FILE = Path(__file__).parent / "race_log_participants.json"
GRACES_FILE = Path(__file__).parent / "manual_graces.json"
RANKING_POSTS_FILE = Path(__file__).parent / "ranking_posts.json"
SUGGESTIONS_FILE = Path(__file__).parent / "suggestions.json"

ACCOUNTS_SHEET_NAME = "accounts"
REQUESTS_SHEET_NAME = "access_requests"
SEASONS_SHEET_NAME = "race_log_seasons"
PARTICIPANTS_SHEET_NAME = "race_log_participants"
GRACES_SHEET_NAME = "manual_graces"
RANKING_POSTS_SHEET_NAME = "ranking_posts"
SUGGESTIONS_SHEET_NAME = "suggestions"

ACCOUNTS_FIELDS = [
    "username", "name", "password_hash", "player_tag",
    "status", "created_at", "revoked_at", "revoked_reason",
    "is_admin",  # ajouté en fin de liste (pas au milieu) pour rester compatible
    # avec les comptes déjà créés avant l'introduction du statut admin
    # (15/08/2026 soir) — voir account_is_admin()/set_admin_status() plus bas.
]
REQUEST_FIELDS = [
    "id", "pseudo_submitted", "password_hash", "requested_at", "status",
    "matched_player_tag", "matched_username", "matched_by", "matched_at",
]

# Archive de l'historique GDC — voir history.py. L'API officielle ne renvoie
# jamais plus de 10 semaines d'historique (confirmé, quel que soit le `limit`
# demandé) ; ces deux tables permettent à l'outil de constituer son propre
# historique plus long au fil du temps, comme le fait royaleapi.com.
#
# IMPORTANT : un `season_id` Supercell ne représente PAS forcément une seule
# semaine de GDC — le schéma officiel (RiverRaceLogEntry) inclut aussi un
# `sectionIndex`, et plusieurs semaines peuvent partager le même season_id
# (ex. lors d'un mois à plusieurs sections). L'identifiant unique d'une
# semaine est donc (season_id, section_index) — voir week_key() ci-dessous.
# `section_index` est ajouté en fin de liste (pas au milieu) pour rester
# compatible avec d'éventuelles lignes déjà archivées sans cette colonne.
SEASONS_FIELDS = ["season_id", "created_date", "clan_tag", "archived_at", "section_index"]
PARTICIPANTS_FIELDS = [
    "season_id", "clan_tag", "player_tag", "player_name",
    "decks_used", "fame", "boat_attacks", "section_index",
]


def week_key(season_id, section_index=0) -> str:
    """Clé unique d'une semaine de GDC : season_id seul ne suffit pas (voir
    note ci-dessus), donc season_id + section_index."""
    si = section_index if section_index not in (None, "") else 0
    return f"{season_id}_{si}"

# Grâces manuelles accordées par un chef malgré une recommandation d'exclusion
# (bouton "grâcier" — voir exclusions.py). C'est la seule donnée du système
# d'exclusions qui n'est pas déductible des données brutes de GDC ; tout le
# reste (compteurs de flags actifs, etc.) est recalculé à la volée.
GRACES_FIELDS = [
    "id", "player_tag", "player_name", "season_id",
    "comment", "granted_by", "granted_at",
]

# Trace des classements postés manuellement sur Discord (bouton "Poster sur
# Discord", onglet Classement, chefs uniquement — voir discord_post.py).
# `week_key` = storage.week_key(season_id, section_index) de la GDC la plus
# récente au moment du post ; sert à griser le bouton une fois posté pour
# cette semaine précise et à afficher qui/quand.
RANKING_POSTS_FIELDS = ["week_key", "posted_by", "posted_at"]

# Suggestions / bugs remontés par n'importe quel joueur depuis l'onglet
# "💡 Suggestions" (demande de Flo, 15/08/2026 soir — remplace le "contacte-moi
# directement" de l'onglet Aide). Visible en entier uniquement par l'admin
# (voir auth.is_admin) ; chaque joueur ne voit que ses propres suggestions.
SUGGESTIONS_FIELDS = [
    "id", "player_tag", "player_name", "username",
    "category", "message", "submitted_at",
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

    # `client.open_by_key()` fait un appel réseau (fetch_sheet_metadata) à
    # CHAQUE fois qu'il est appelé — jusqu'ici il était rappelé à chaque accès
    # à _get_worksheet(), donc une fois par onglet différent consulté (comptes,
    # demandes, saisons, participants, grâces, posts classement, suggestions).
    # Ça a provoqué un dépassement de quota (`APIError [429] Quota exceeded for
    # ... Read requests`) juste après un redémarrage de l'app le 16/08/2026 —
    # tous les caches `st.cache_data` étant vides en même temps, une seule page
    # pouvait déclencher jusqu'à 7-8 appels `open_by_key` d'un coup. Corrigé en
    # mettant le classeur (Spreadsheet) ouvert en cache lui aussi, comme le
    # client : un seul appel `open_by_key` par process, plus un par onglet.
    if "sheet" not in _sheets_client_cache:
        client = _sheets_client_cache["client"]
        _sheets_client_cache["sheet"] = client.open_by_key(_sheet_id())

    sheet = _sheets_client_cache["sheet"]
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


def _sheets_get_archived_week_keys(clan_tag: str) -> set[str]:
    ws = _get_worksheet(SEASONS_SHEET_NAME, SEASONS_FIELDS)
    records = ws.get_all_records()
    return {
        week_key(r.get("season_id", ""), r.get("section_index", 0))
        for r in records
        if str(r.get("clan_tag")) == clan_tag
    }


def _sheets_archive_season(
    season_id: str, created_date: str, clan_tag: str, participant_rows: list[dict], section_index=0
) -> None:
    seasons_ws = _get_worksheet(SEASONS_SHEET_NAME, SEASONS_FIELDS)
    seasons_ws.append_row([str(season_id), created_date, clan_tag, _now_iso(), str(section_index)])

    if not participant_rows:
        return
    participants_ws = _get_worksheet(PARTICIPANTS_SHEET_NAME, PARTICIPANTS_FIELDS)
    rows = [[str(r.get(f, "")) for f in PARTICIPANTS_FIELDS] for r in participant_rows]
    participants_ws.append_rows(rows)


def _sheets_get_participants(clan_tag: str, season_ids: Optional[set[str]] = None) -> list[dict]:
    ws = _get_worksheet(PARTICIPANTS_SHEET_NAME, PARTICIPANTS_FIELDS)
    records = ws.get_all_records()
    out = [r for r in records if str(r.get("clan_tag")) == clan_tag]
    if season_ids is not None:
        out = [r for r in out if str(r.get("season_id")) in season_ids]
    return out


def _sheets_get_manual_graces() -> list[dict]:
    ws = _get_worksheet(GRACES_SHEET_NAME, GRACES_FIELDS)
    return ws.get_all_records()


def _sheets_add_manual_grace(grace: dict) -> None:
    ws = _get_worksheet(GRACES_SHEET_NAME, GRACES_FIELDS)
    ws.append_row([str(grace.get(f, "")) for f in GRACES_FIELDS])


def _sheets_get_ranking_posts() -> list[dict]:
    ws = _get_worksheet(RANKING_POSTS_SHEET_NAME, RANKING_POSTS_FIELDS)
    return ws.get_all_records()


def _sheets_add_ranking_post(post: dict) -> None:
    ws = _get_worksheet(RANKING_POSTS_SHEET_NAME, RANKING_POSTS_FIELDS)
    ws.append_row([str(post.get(f, "")) for f in RANKING_POSTS_FIELDS])


def _sheets_get_suggestions() -> list[dict]:
    ws = _get_worksheet(SUGGESTIONS_SHEET_NAME, SUGGESTIONS_FIELDS)
    return ws.get_all_records()


def _sheets_add_suggestion(suggestion: dict) -> None:
    ws = _get_worksheet(SUGGESTIONS_SHEET_NAME, SUGGESTIONS_FIELDS)
    ws.append_row([str(suggestion.get(f, "")) for f in SUGGESTIONS_FIELDS])


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


def _local_get_archived_week_keys(clan_tag: str) -> set[str]:
    seasons = _local_read(SEASONS_FILE, [])
    return {
        week_key(s.get("season_id", ""), s.get("section_index", 0))
        for s in seasons
        if s.get("clan_tag") == clan_tag
    }


def _local_archive_season(
    season_id: str, created_date: str, clan_tag: str, participant_rows: list[dict], section_index=0
) -> None:
    seasons = _local_read(SEASONS_FILE, [])
    seasons.append(
        {
            "season_id": str(season_id),
            "created_date": created_date,
            "clan_tag": clan_tag,
            "archived_at": _now_iso(),
            "section_index": str(section_index),
        }
    )
    _local_write(SEASONS_FILE, seasons)

    if not participant_rows:
        return
    participants = _local_read(PARTICIPANTS_FILE, [])
    participants.extend(participant_rows)
    _local_write(PARTICIPANTS_FILE, participants)


def _local_get_participants(clan_tag: str, season_ids: Optional[set[str]] = None) -> list[dict]:
    participants = _local_read(PARTICIPANTS_FILE, [])
    out = [r for r in participants if r.get("clan_tag") == clan_tag]
    if season_ids is not None:
        out = [r for r in out if str(r.get("season_id")) in season_ids]
    return out


def _local_get_manual_graces() -> list[dict]:
    return _local_read(GRACES_FILE, [])


def _local_add_manual_grace(grace: dict) -> None:
    graces = _local_read(GRACES_FILE, [])
    graces.append(grace)
    _local_write(GRACES_FILE, graces)


def _local_get_ranking_posts() -> list[dict]:
    return _local_read(RANKING_POSTS_FILE, [])


def _local_add_ranking_post(post: dict) -> None:
    posts = _local_read(RANKING_POSTS_FILE, [])
    posts.append(post)
    _local_write(RANKING_POSTS_FILE, posts)


def _local_get_suggestions() -> list[dict]:
    return _local_read(SUGGESTIONS_FILE, [])


def _local_add_suggestion(suggestion: dict) -> None:
    suggestions = _local_read(SUGGESTIONS_FILE, [])
    suggestions.append(suggestion)
    _local_write(SUGGESTIONS_FILE, suggestions)


# ---------------------------------------------------------------------------
# Interface publique (utilisée par le reste de l'appli)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def get_accounts() -> dict:
    """username -> account dict"""
    return _sheets_get_accounts() if backend_name() == "sheets" else _local_get_accounts()


def upsert_account(username: str, account: dict) -> None:
    if backend_name() == "sheets":
        _sheets_upsert_account(username, account)
    else:
        _local_upsert_account(username, account)
    get_accounts.clear()


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
        "is_admin": False,  # jamais admin par défaut — voir set_admin_status()
    }
    upsert_account(username, account)
    return account


def _truthy(value) -> bool:
    """Un booléen stocké en Sheets redevient une string ('True'/'FALSE'/...)
    après un aller-retour — contrairement au JSON local qui garde le vrai
    bool Python. Cette fonction normalise les deux cas."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "1", "yes", "vrai")


def account_is_admin(account: dict) -> bool:
    return _truthy(account.get("is_admin"))


def any_admin_exists() -> bool:
    """Utilisé pour le "bootstrap" de la toute première mise en route du
    statut admin (voir auth.is_admin) : tant qu'AUCUN compte actif n'a
    explicitement le statut admin, on retombe sur un filet de sécurité côté
    auth.py (Chef du clan = admin par défaut) plutôt que de bloquer tout le
    monde hors de l'onglet Comptes."""
    return any(account_is_admin(a) for a in get_accounts().values() if a.get("status") == "active")


def set_admin_status(username: str, is_admin: bool) -> dict:
    """Accorde/retire le statut admin à un compte existant (bouton dans
    l'onglet 👥 Comptes, réservé aux admins — voir views/accounts_admin.py).
    Contrairement au rôle chef (recalculé depuis l'API à chaque run), le
    statut admin est une donnée propre à l'outil, indépendante du clan en
    jeu — demande explicite de Flo, 15/08/2026 soir."""
    accounts = get_accounts()
    account = accounts.get(username)
    if not account:
        raise KeyError(f"Compte introuvable : {username}")
    account["is_admin"] = is_admin
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


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
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
    get_access_requests.clear()
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
    get_access_requests.clear()

    return account


def reject_access_request(request_id: str, rejected_by: str) -> None:
    updates = {"status": "rejected", "matched_by": rejected_by, "matched_at": _now_iso()}
    if backend_name() == "sheets":
        _sheets_update_request(request_id, updates)
    else:
        _local_update_request(request_id, updates)
    get_access_requests.clear()


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def get_archived_week_keys(clan_tag: str) -> set[str]:
    """Ensemble des clés de semaines déjà archivées pour ce clan (voir week_key())."""
    return (
        _sheets_get_archived_week_keys(clan_tag)
        if backend_name() == "sheets"
        else _local_get_archived_week_keys(clan_tag)
    )


def archive_season(
    season_id: str, created_date: str, clan_tag: str, participant_rows: list[dict], section_index=0
) -> None:
    """
    Archive une GDC terminée : une ligne d'index (season_id/section_index/created_date)
    + une ligne par participant. À appeler une seule fois par (season_id, section_index)
    (voir history.sync_archive, qui vérifie get_archived_week_keys() avant).
    """
    if backend_name() == "sheets":
        _sheets_archive_season(season_id, created_date, clan_tag, participant_rows, section_index)
    else:
        _local_archive_season(season_id, created_date, clan_tag, participant_rows, section_index)
    get_archived_week_keys.clear()
    get_archived_participants.clear()


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def get_archived_participants(clan_tag: str, season_ids: Optional[set[str]] = None) -> list[dict]:
    """Lignes participant archivées pour ce clan, filtrées sur season_ids si fourni."""
    return (
        _sheets_get_participants(clan_tag, season_ids)
        if backend_name() == "sheets"
        else _local_get_participants(clan_tag, season_ids)
    )


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def get_manual_graces() -> list[dict]:
    """Toutes les grâces manuelles accordées (tous joueurs/semaines confondus)."""
    return _sheets_get_manual_graces() if backend_name() == "sheets" else _local_get_manual_graces()


def add_manual_grace(player_tag: str, player_name: str, season_id: str, comment: str, granted_by: str) -> dict:
    """Enregistre une grâce manuelle (bouton "grâcier" — voir views/suivi.py, Phase E)."""
    grace = {
        "id": new_request_id(),
        "player_tag": player_tag,
        "player_name": player_name,
        "season_id": str(season_id),
        "comment": comment or "",
        "granted_by": granted_by,
        "granted_at": _now_iso(),
    }
    if backend_name() == "sheets":
        _sheets_add_manual_grace(grace)
    else:
        _local_add_manual_grace(grace)
    get_manual_graces.clear()
    return grace


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def get_ranking_posts() -> list[dict]:
    """Tous les classements postés sur Discord (toutes semaines confondues)."""
    return _sheets_get_ranking_posts() if backend_name() == "sheets" else _local_get_ranking_posts()


def get_ranking_post_for_week(week: str) -> Optional[dict]:
    """Le post existant pour cette semaine (week_key), ou None si pas encore posté."""
    return next((p for p in get_ranking_posts() if str(p.get("week_key")) == str(week)), None)


def record_ranking_post(week: str, posted_by: str) -> dict:
    """Enregistre qu'un chef a posté le classement sur Discord pour cette semaine
    (bouton "Poster sur Discord" — voir views/ranking.py, discord_post.py)."""
    post = {"week_key": str(week), "posted_by": posted_by, "posted_at": _now_iso()}
    if backend_name() == "sheets":
        _sheets_add_ranking_post(post)
    else:
        _local_add_ranking_post(post)
    get_ranking_posts.clear()
    return post


@st.cache_data(ttl=_CACHE_TTL, show_spinner=False)
def get_suggestions() -> list[dict]:
    """Toutes les suggestions/bugs remontés (tous joueurs confondus) — le
    filtrage par joueur (pour un membre non-admin) se fait côté appelant,
    voir views/suggestions.py."""
    return _sheets_get_suggestions() if backend_name() == "sheets" else _local_get_suggestions()


def add_suggestion(player_tag: str, player_name: str, username: str, category: str, message: str) -> dict:
    """Enregistre une suggestion/bug remonté par un joueur (onglet 💡 Suggestions)."""
    suggestion = {
        "id": new_request_id(),
        "player_tag": player_tag,
        "player_name": player_name,
        "username": username,
        "category": category,
        "message": message,
        "submitted_at": _now_iso(),
    }
    if backend_name() == "sheets":
        _sheets_add_suggestion(suggestion)
    else:
        _local_add_suggestion(suggestion)
    get_suggestions.clear()
    return suggestion


def _slugify_username(pseudo: str) -> str:
    base = "".join(c.lower() if c.isalnum() else "" for c in pseudo) or "joueur"
    accounts = get_accounts()
    candidate = base
    i = 2
    while candidate in accounts:
        candidate = f"{base}{i}"
        i += 1
    return candidate
