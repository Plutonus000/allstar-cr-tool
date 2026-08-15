"""
clash_api.py — couche d'accès à l'API officielle Clash Royale (via le proxy RoyaleAPI).

Le proxy RoyaleAPI (https://proxy.royaleapi.dev) permet d'appeler l'API officielle
Supercell sans avoir une IP fixe côté client : la clé API est whitelistée sur l'IP
du proxy (45.79.218.79), pas sur l'IP de la machine qui exécute ce script.

Toutes les fonctions renvoient des dicts/list directement issus du JSON de l'API
(aucune transformation ici — les transformations "métier" vivent dans app.py).
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

import requests
from dotenv import load_dotenv

load_dotenv()


def _resolve_secret(name: str, default: str = "") -> str:
    """
    Résout un secret en cherchant d'abord dans st.secrets (Streamlit Cloud),
    puis dans les variables d'environnement / fichier .env (usage local).
    """
    try:
        import streamlit as st  # import local pour ne pas dépendre de streamlit hors appli

        if name in st.secrets:
            return str(st.secrets[name]).strip()
    except Exception:
        pass
    return os.getenv(name, default).strip()


API_KEY = _resolve_secret("CLASH_API_KEY")
DEFAULT_CLAN_TAG = _resolve_secret("CLAN_TAG", "#2Q2Q889")
BASE_URL = "https://proxy.royaleapi.dev/v1"

_SESSION = requests.Session()


class ClashAPIError(Exception):
    """Erreur remontée depuis l'API Clash Royale / le proxy, avec un message clair."""


def _headers() -> dict:
    if not API_KEY:
        raise ClashAPIError(
            "Aucune clé API trouvée (CLASH_API_KEY manquant dans le fichier .env)."
        )
    return {"Authorization": f"Bearer {API_KEY}"}


def tag_encode(tag: str) -> str:
    """Normalise un tag joueur/clan ('2Q2Q889' ou '#2Q2Q889') pour l'URL (# -> %23)."""
    tag = tag.strip().upper()
    if not tag.startswith("#"):
        tag = "#" + tag
    return tag.replace("#", "%23")


def _get(path: str, params: Optional[dict] = None, retries: int = 2) -> Any:
    url = f"{BASE_URL}{path}"
    last_exc: Optional[Exception] = None

    for attempt in range(retries + 1):
        try:
            resp = _SESSION.get(url, headers=_headers(), params=params, timeout=15)
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(0.5 * (attempt + 1))
            continue

        if resp.status_code == 200:
            return resp.json()

        if resp.status_code == 403:
            raise ClashAPIError(
                "Accès refusé (403). Vérifie sur developer.clashroyale.com que la clé "
                "utilisée a bien l'IP 45.79.218.79 dans 'Allowed IP Addresses' "
                "(c'est l'IP du proxy RoyaleAPI, pas la tienne)."
            )
        if resp.status_code == 404:
            raise ClashAPIError(f"Introuvable (404) : {path}. Vérifie le tag saisi.")
        if resp.status_code == 429:
            raise ClashAPIError(
                "Trop de requêtes envoyées (429) — attends quelques secondes et réessaie."
            )
        if resp.status_code == 503:
            last_exc = ClashAPIError("API Supercell temporairement indisponible (503).")
            time.sleep(1.0 * (attempt + 1))
            continue

        raise ClashAPIError(f"Erreur API inattendue ({resp.status_code}) sur {path} : {resp.text[:300]}")

    raise ClashAPIError(f"Échec de connexion à l'API après {retries + 1} tentatives : {last_exc}")


# ---------------------------------------------------------------------------
# Endpoints clan
# ---------------------------------------------------------------------------

def get_clan(clan_tag: Optional[str] = None) -> dict:
    """Infos générales du clan + memberList (rôle, trophées, niveau, rang)."""
    clan_tag = clan_tag or DEFAULT_CLAN_TAG
    return _get(f"/clans/{tag_encode(clan_tag)}")


def get_clan_members(clan_tag: Optional[str] = None) -> list[dict]:
    """Liste des membres du clan (source : /clans/{tag}/members, paginée par l'API)."""
    clan_tag = clan_tag or DEFAULT_CLAN_TAG
    data = _get(f"/clans/{tag_encode(clan_tag)}/members", params={"limit": 50})
    return data.get("items", [])


def get_current_river_race(clan_tag: Optional[str] = None) -> dict:
    """GDC en cours : notre clan (participants, decks joués, fame) + clans adverses."""
    clan_tag = clan_tag or DEFAULT_CLAN_TAG
    return _get(f"/clans/{tag_encode(clan_tag)}/currentriverrace")


def get_river_race_log(clan_tag: Optional[str] = None, limit: int = 10) -> list[dict]:
    """Historique des GDC terminées (le plus récent en premier)."""
    clan_tag = clan_tag or DEFAULT_CLAN_TAG
    data = _get(f"/clans/{tag_encode(clan_tag)}/riverracelog", params={"limit": limit})
    return data.get("items", [])


# ---------------------------------------------------------------------------
# Endpoint joueur
# ---------------------------------------------------------------------------

def get_player(player_tag: str) -> dict:
    """Fiche complète d'un joueur : niveau, trophées, cartes (avec niveau/rareté), deck actuel."""
    return _get(f"/players/{tag_encode(player_tag)}")


def get_player_battlelog(player_tag: str) -> list[dict]:
    """
    Historique récent des combats d'un joueur (/players/{tag}/battlelog) : chaque
    entrée contient `type`, `battleTime`, et `team`/`opponent` (dont les cartes
    RÉELLEMENT utilisées dans ce combat précis, contrairement à get_player() qui ne
    renvoie que la collection complète du joueur).

    ATTENTION (ajouté le 16/08/2026, demande de Flo) : cet endpoint a 2 limites
    réelles, non vérifiables depuis le sandbox de développement (accès réseau
    restreint) — à confirmer une fois l'app testée en conditions réelles :
    1. Rétention limitée côté API — ce n'est PAS un historique complet, seulement
       les combats les plus récents (nombre exact non documenté officiellement).
    2. Les valeurs exactes du champ `type` pour les combats de GDC (river race)
       n'ont pas pu être vérifiées en live — voir logic.compute_maxed_cards_in_war_deck
       pour le filtre best-effort utilisé en attendant confirmation.
    """
    return _get(f"/players/{tag_encode(player_tag)}/battlelog")


# ---------------------------------------------------------------------------
# Calculs utilitaires
# ---------------------------------------------------------------------------

def normalized_card_level(level: int, max_level: int, cap: int = 14) -> int:
    """
    Niveau "affiché en jeu" d'une carte, comparable entre raretés.

    L'API renvoie un niveau interne différent selon la rareté (les communes montent
    plus haut que les légendaires). Le jeu normalise l'affichage sur une échelle
    commune (cap=14 par défaut, niveau max d'une carte commune). Cette fonction
    reproduit ce calcul : niveau_affiché = level + (cap - max_level).
    """
    return level + (cap - max_level)
