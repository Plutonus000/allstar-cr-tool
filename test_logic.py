"""Test rapide de la logique métier avec des données factices (pas d'appel réseau)."""
import logic as app  # alias pour ne pas réécrire les assertions ci-dessous

# --- normalized_card_level ---
import clash_api as api
assert api.normalized_card_level(14, 14) == 14  # commune maxée
assert api.normalized_card_level(11, 11) == 14  # légendaire maxée -> ramenée à l'échelle 14
assert api.normalized_card_level(5, 11) == 8
print("normalized_card_level OK")

# --- compute_ranking ---
fake_log = [
    {
        "seasonId": 100,
        "createdDate": "20260803T000000.000Z",
        "standings": [
            {
                "rank": 1,
                "trophyChange": 40,
                "clan": {
                    "tag": "#2Q2Q889",
                    "name": "ALLSTAR Belgium",
                    "fame": 12000,
                    "participants": [
                        {"tag": "#A", "name": "Alice", "decksUsed": 16, "fame": 3000, "boatAttacks": 0},
                        {"tag": "#B", "name": "Bob", "decksUsed": 8, "fame": 1200, "boatAttacks": 1},
                    ],
                },
            },
            {"rank": 2, "trophyChange": -20, "clan": {"tag": "#OTHER", "name": "Ennemi", "fame": 9000, "participants": []}},
        ],
    },
    {
        "seasonId": 99,
        "createdDate": "20260727T000000.000Z",
        "standings": [
            {
                "rank": 3,
                "trophyChange": 10,
                "clan": {
                    "tag": "#2Q2Q889",
                    "name": "ALLSTAR Belgium",
                    "fame": 11000,
                    "participants": [
                        {"tag": "#A", "name": "Alice", "decksUsed": 14, "fame": 2800, "boatAttacks": 0},
                    ],
                },
            }
        ],
    },
]

df = app.compute_ranking(fake_log, "#2Q2Q889", n_races=2)
assert len(df) == 2, df
alice = df[df["Joueur"] == "Alice"].iloc[0]
assert alice["GDC jouées"] == 2
assert alice["Decks joués"] == 30
assert alice["Decks max"] == 32
bob = df[df["Joueur"] == "Bob"].iloc[0]
assert bob["GDC jouées"] == 1
assert bob["Decks max"] == 16
print("compute_ranking OK")
print(df)

# --- compute_current_race_table ---
fake_current = {
    "state": "war",
    "clan": {
        "tag": "#2Q2Q889",
        "participants": [
            {"tag": "#A", "name": "Alice", "decksUsed": 8, "decksUsedToday": 2, "fame": 1500, "boatAttacks": 0},
        ],
    },
}
df2 = app.compute_current_race_table(fake_current)
assert len(df2) == 1
print("compute_current_race_table OK")

# --- compute_card_levels ---
fake_player = {
    "name": "Alice",
    "cards": [
        {"name": "Chevalier", "rarity": "Common", "level": 14, "maxLevel": 14},
        {"name": "Le Prince", "rarity": "Epic", "level": 6, "maxLevel": 9},
    ],
}
cdf = app.compute_card_levels(fake_player)
assert list(cdf["Niveau (jeu)"]) == sorted(cdf["Niveau (jeu)"])
print("compute_card_levels OK")
print(cdf)

print("\nTOUS LES TESTS PASSENT")
