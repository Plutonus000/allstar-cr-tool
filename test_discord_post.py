"""Tests discord_post.py — construction du message (pas d'appel réseau)."""

from __future__ import annotations

import exclusions
import discord_post as dp

CLAN_TAG = "#2Q2Q889"


def _gdc(season_id, date, players):
    """players : dict tag -> (decks, boats, fame)."""
    participants = [
        {"tag": tag, "name": tag, "decksUsed": d, "boatAttacks": b, "fame": f}
        for tag, (d, b, f) in players.items()
    ]
    return {
        "seasonId": season_id,
        "createdDate": date,
        "standings": [
            {"clan": {"tag": CLAN_TAG, "fame": sum(p["fame"] for p in participants), "participants": participants}}
        ],
    }


# 7 GDC (>= TIER_FULL_THRESHOLD) pour 6 joueurs -> paliers principaux, pas juste MULTIVERSE.
log = [_gdc(200 - i, f"d{i}", {f"#P{n}": (16, 0, 200 - n * 5) for n in range(6)}) for i in range(7)]
stats = exclusions.compute_player_stats(log, CLAN_TAG)
ranked_now = exclusions.ranked_list(stats)
assert len(ranked_now) == 6, ranked_now

# --- build_ranking_messages sans historique précédent (première publication) ---
msgs = dp.build_ranking_messages(ranked_now, None, n_gdcs=7, latest_date="17/08/26", posted_by="Testeur")
assert len(msgs) >= 1
full_text = "\n".join(msgs)
assert "CLASSEMENT AVENGERS" in full_text
assert "Historique insuffisant" in full_text
assert "🆕" in full_text
assert "Testeur" in full_text
print("build_ranking_messages (sans historique précédent -> 🆕 partout) OK")

# --- build_ranking_messages avec un classement précédent (indicateurs ▲▼) ---
# P0 était #2 la semaine dernière, passe #1 -> 🟢+1. P1 était #1, passe #2 -> 🔴-1.
ranked_prev = [dict(p) for p in ranked_now]
ranked_prev[0]["rang"], ranked_prev[1]["rang"] = ranked_prev[1]["rang"], ranked_prev[0]["rang"]

msgs2 = dp.build_ranking_messages(ranked_now, ranked_prev, n_gdcs=7, latest_date="17/08/26", posted_by="Testeur")
full_text2 = "\n".join(msgs2)
assert "🟢+1" in full_text2, full_text2
assert "🔴-1" in full_text2, full_text2
assert "Historique insuffisant" not in full_text2
print("build_ranking_messages (avec historique précédent -> indicateurs ▲▼) OK")

# --- _split_message : jamais de coupure en plein milieu d'une section ---
lines = ["**Titre**", "ligne", ""] * 200  # volontairement long pour forcer une coupure
messages = dp._split_message(lines, max_len=500)
assert len(messages) > 1
for m in messages:
    assert len(m) <= 500 + 50  # tolérance : une section ne peut pas dépasser max_len à elle seule ici
print("_split_message (découpe multi-messages) OK")

# --- webhook_configured() / post_ranking_to_discord() sans secret configuré ---
assert dp.webhook_configured() is False  # aucun secret DISCORD_WEBHOOK_RANKING dans cet environnement de test
# dry_run=True ne doit JAMAIS exiger de webhook ni faire d'appel réseau (utilisé en test/dev).
dp.post_ranking_to_discord(["test"], dry_run=True)
try:
    dp.post_ranking_to_discord(["test"], dry_run=False)
    raise AssertionError("aurait dû lever RuntimeError (pas de webhook configuré)")
except RuntimeError:
    pass
print("post_ranking_to_discord (dry_run -> aucun appel/pas besoin de webhook, sinon erreur claire) OK")

print("\nTOUS LES TESTS DISCORD_POST PASSENT")
