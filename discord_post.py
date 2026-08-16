"""
discord_post.py — construction + envoi du message Discord "Classement" (bouton
"Poster sur Discord", onglet Classement, chefs uniquement — remplace le post
automatique du bot Discord, arrêté le 15/08/2026 à la demande de Flo).

Format inspiré de clan_war_bot.py::format_ranking_message() (mêmes paliers
Avengers, mêmes indicateurs de progression ▲▼🆕), avec deux différences
assumées :
- le webhook est lu depuis un secret (DISCORD_WEBHOOK_RANKING, même mécanisme
  que CLASH_API_KEY/GOOGLE_SHEET_ID — jamais codé en dur dans le code) ;
- les rangs de la semaine précédente sont recalculés depuis l'historique déjà
  archivé par l'outil (voir history.py), pas besoin d'un fichier séparé comme
  ranking_history.json côté bot — tant qu'il n'y a pas assez d'historique
  archivé, les indicateurs affichent 🆕 partout (comme la "publication
  inaugurale" du bot).

Logique de construction de message pure et testable (pas de réseau) ; seule
`post_ranking_to_discord()` fait un appel réseau, et seulement si on ne lui
demande pas explicitement `dry_run=True`.
"""

from __future__ import annotations

import os

import requests

import exclusions

DISCORD_MAX_LEN = 1900


def _resolve_secret(name: str, default: str = "") -> str:
    """Même résolution que clash_api._resolve_secret (secrets Streamlit Cloud,
    puis variable d'env / .env local) — dupliqué ici pour ne pas dépendre d'une
    fonction privée d'un autre module."""
    try:
        import streamlit as st

        if name in st.secrets:
            return str(st.secrets[name]).strip()
    except Exception:
        pass
    return os.getenv(name, default).strip()


def webhook_configured() -> bool:
    return bool(_resolve_secret("DISCORD_WEBHOOK_RANKING"))


def _split_message(lines: list[str], max_len: int = DISCORD_MAX_LEN) -> list[str]:
    """Découpe en messages de max max_len caractères, en coupant entre les
    sections (jamais en plein milieu d'un palier) — même logique que
    clan_war_bot.py::_split_message()."""
    sections, current_section = [], []
    for line in lines:
        current_section.append(line)
        if line == "":
            sections.append(current_section)
            current_section = []
    if current_section:
        sections.append(current_section)

    messages, current_lines, current_len = [], [], 0
    for section in sections:
        section_text = "\n".join(section)
        section_len = len(section_text) + 1
        if current_len + section_len > max_len and current_lines:
            messages.append("\n".join(current_lines).rstrip())
            current_lines, current_len = [], 0
        current_lines.extend(section)
        current_len += section_len

    if current_lines:
        msg = "\n".join(current_lines).strip()
        if msg:
            messages.append(msg)
    return messages


def build_ranking_messages(
    ranked_now: list[dict],
    ranked_prev: list[dict] | None,
    n_gdcs: int,
    latest_date: str,
    posted_by: str,
) -> list[str]:
    """
    ranked_now / ranked_prev : sorties de exclusions.ranked_list() pour la
    semaine courante / la semaine précédente (None si pas assez d'historique
    archivé pour calculer une semaine précédente).
    """
    prev_rank_by_tag = {p["tag"]: p["rang"] for p in ranked_prev} if ranked_prev else None

    lines = [
        f"📋 *Classement posté manuellement par {posted_by} via l'outil ALLSTAR*",
        "",
        f"🦸‍♂️ **CLASSEMENT AVENGERS — GDC {latest_date}**",
        f"*Basé sur les {n_gdcs} dernières GDC · Score moyen × assiduité*",
        "⸻",
        "",
    ]
    if prev_rank_by_tag is None:
        lines += [
            "ℹ️ *Historique insuffisant pour afficher les évolutions (🆕 partout) — "
            "elles apparaîtront dès qu'assez de semaines seront archivées.*",
            "",
        ]

    current_tier = None
    for p in ranked_now:
        if p["tier"] != current_tier:
            current_tier = p["tier"]
            lines.append(f"**{current_tier}**")
            desc = exclusions.TIER_DESCRIPTIONS.get(current_tier, "")
            if desc:
                lines.append(f"*{desc}*")
            lines.append("")

        is_ranked = current_tier not in (exclusions.SHIELD_TIER, exclusions.MULTIVERSE_TIER)
        if is_ranked:
            rank = p["rang"]
            if prev_rank_by_tag is None:
                indicator = "🆕 "
            else:
                prev = prev_rank_by_tag.get(p["tag"])
                if prev is None:
                    indicator = "🆕 "
                elif prev > rank:
                    indicator = f"🟢+{prev - rank} "
                elif prev < rank:
                    indicator = f"🔴-{rank - prev} "
                else:
                    indicator = "🟡= "
            max_decks = p["gdc_count"] * exclusions.FULL_DECKS
            lines.append(f"• {indicator}#{rank} {p['name']} ({p['avg_fame']} | {p['total_decks']}/{max_decks})")
        else:
            lines.append(f"• {p['name']} ({p['gdc_count']} GDC | {p['total_decks']} decks | ~{p['avg_fame']} pts/GDC)")

    lines.append("")
    return _split_message(lines)


def post_ranking_to_discord(messages: list[str], dry_run: bool = False) -> None:
    """
    Envoie les messages du classement sur Discord (un appel par message,
    Discord limite un message à 2000 caractères — voir _split_message).

    dry_run=True n'envoie RIEN sur le vrai Discord (utilisé uniquement en
    test/dev — jamais en production, jamais sans en informer Flo au préalable).
    """
    if dry_run:
        return
    webhook = _resolve_secret("DISCORD_WEBHOOK_RANKING")
    if not webhook:
        raise RuntimeError(
            "Aucun webhook Discord configuré — ajoute le secret DISCORD_WEBHOOK_RANKING "
            "(même valeur que WEBHOOK_RANKING dans clan_war_bot.py) dans .env en local "
            "et dans les Secrets Streamlit Cloud une fois déployé."
        )
    for msg in messages:
        r = requests.post(
            webhook,
            json={"content": msg},
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
