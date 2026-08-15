"""
data.py — chargement des données API, mis en cache (utilisé par toutes les vues).

Centralisé ici pour éviter que chaque page réimplémente son propre cache.
"""

from __future__ import annotations

import streamlit as st

import clash_api as api


@st.cache_data(ttl=300, show_spinner=False)
def load_clan(clan_tag: str) -> dict:
    return api.get_clan(clan_tag)


@st.cache_data(ttl=300, show_spinner=False)
def load_clan_members(clan_tag: str) -> list[dict]:
    return api.get_clan_members(clan_tag)


@st.cache_data(ttl=300, show_spinner=False)
def load_current_race(clan_tag: str) -> dict:
    return api.get_current_river_race(clan_tag)


@st.cache_data(ttl=600, show_spinner=False)
def load_race_log(clan_tag: str, limit: int = 10) -> list[dict]:
    return api.get_river_race_log(clan_tag, limit=limit)


@st.cache_data(ttl=1800, show_spinner=False)
def load_player(player_tag: str) -> dict:
    return api.get_player(player_tag)


@st.cache_data(ttl=1800, show_spinner=False)
def load_player_battlelog(player_tag: str) -> list[dict]:
    """TTL 30 min comme load_player — le battlelog ne bouge pas assez vite pour
    justifier un rafraîchissement plus fréquent (voir clash_api.get_player_battlelog)."""
    return api.get_player_battlelog(player_tag)


def clear_all() -> None:
    st.cache_data.clear()
