"""
logic.py — fonctions métier pures (pas de dépendance à Streamlit), donc testables seules.

app.py importe ces fonctions et se contente de les brancher à l'interface.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

import pandas as pd

import clash_api as api


def norm_tag(tag: str) -> str:
    return tag.strip().upper().lstrip("#")


def compute_ranking(race_log_items: list[dict], clan_tag: str, n_races: int) -> pd.DataFrame:
    """
    Agrège les GDC les plus récentes (jusqu'à n_races) pour construire un classement
    par joueur : nombre de GDC jouées, decks utilisés, fame, assiduité.

    Hypothèse V1 : max théorique = 16 decks/GDC (pas de proratisation des arrivées
    en cours de GDC ici, contrairement au bot Discord — à affiner plus tard si besoin).
    """
    target = norm_tag(clan_tag)
    rows: dict[str, dict] = {}

    for item in race_log_items[:n_races]:
        our_standing = next(
            (s for s in item.get("standings", []) if norm_tag(s.get("clan", {}).get("tag", "")) == target),
            None,
        )
        if not our_standing:
            continue
        clan_data = our_standing["clan"]
        for p in clan_data.get("participants", []):
            tag = p.get("tag", "")
            row = rows.setdefault(
                tag,
                {"Tag": tag, "Joueur": p.get("name", "?"), "GDC jouées": 0, "Decks joués": 0, "Fame totale": 0},
            )
            row["GDC jouées"] += 1
            row["Decks joués"] += p.get("decksUsed", 0)
            row["Fame totale"] += p.get("fame", 0)
            row["Joueur"] = p.get("name", row["Joueur"])  # garde le nom le plus récent

    if not rows:
        return pd.DataFrame(
            columns=["Rang", "Joueur", "Tag", "GDC jouées", "Decks joués", "Decks max", "Assiduité %", "Fame totale", "Fame moy./GDC"]
        )

    df = pd.DataFrame(rows.values())
    df["Decks max"] = df["GDC jouées"] * 16
    df["Assiduité %"] = (df["Decks joués"] / df["Decks max"] * 100).round(1)
    df["Fame moy./GDC"] = (df["Fame totale"] / df["GDC jouées"]).round(0).astype(int)
    df = df.sort_values(["Assiduité %", "Fame totale"], ascending=False).reset_index(drop=True)
    df.insert(0, "Rang", range(1, len(df) + 1))
    return df[["Rang", "Joueur", "Tag", "GDC jouées", "Decks joués", "Decks max", "Assiduité %", "Fame totale", "Fame moy./GDC"]]


def compute_current_race_table(current_race: dict) -> pd.DataFrame:
    participants = current_race.get("clan", {}).get("participants", [])
    if not participants:
        return pd.DataFrame(columns=["Joueur", "Tag", "Decks joués", "Decks aujourd'hui", "Fame", "Attaques bateau adverse"])
    df = pd.DataFrame(
        [
            {
                "Joueur": p.get("name", "?"),
                "Tag": p.get("tag", ""),
                "Decks joués": p.get("decksUsed", 0),
                "Decks aujourd'hui": p.get("decksUsedToday", 0),
                "Fame": p.get("fame", 0),
                "Attaques bateau adverse": p.get("boatAttacks", 0),
            }
            for p in participants
        ]
    )
    return df.sort_values("Decks joués", ascending=False).reset_index(drop=True)


def compute_card_levels(player_data: dict) -> pd.DataFrame:
    cards = player_data.get("cards", [])
    if not cards:
        return pd.DataFrame(columns=["Carte", "Rareté", "Niveau (jeu)", "Niveau (interne)", "Niveau max"])
    rows = []
    for c in cards:
        max_level = c.get("maxLevel", 14)
        level = c.get("level", 0)
        rows.append(
            {
                "Carte": c.get("name", "?"),
                "Rareté": c.get("rarity", "?"),
                "Niveau (jeu)": api.normalized_card_level(level, max_level),
                "Niveau (interne)": level,
                "Niveau max": max_level,
            }
        )
    return pd.DataFrame(rows).sort_values("Niveau (jeu)").reset_index(drop=True)


def fetch_all_members_cards(
    member_tags: list[str],
    player_loader: Callable[[str], dict],
    max_workers: int = 5,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> dict[str, dict]:
    """Récupère les fiches joueur (avec cartes) de plusieurs membres en parallèle limité."""
    results: dict[str, dict] = {}
    done = 0
    total = len(member_tags)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(player_loader, tag): tag for tag in member_tags}
        for future in as_completed(futures):
            tag = futures[future]
            try:
                results[tag] = future.result()
            except api.ClashAPIError as exc:
                results[tag] = {"__error__": str(exc)}
            done += 1
            if progress_cb:
                progress_cb(done, total)
            time.sleep(0.05)  # petite marge anti-rate-limit
    return results
