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

# --- compute_current_race_table : déduplication par tag (bug "83 joueurs" signalé par Flo) ---
fake_current_dupes = {
    "state": "war",
    "clan": {
        "tag": "#2Q2Q889",
        "participants": [
            {"tag": "#A", "name": "Alice", "decksUsed": 4, "decksUsedToday": 2, "fame": 500, "boatAttacks": 0},
            {"tag": "#A", "name": "Alice", "decksUsed": 8, "decksUsedToday": 2, "fame": 1500, "boatAttacks": 0},
            {"tag": "#B", "name": "Bob", "decksUsed": 2, "decksUsedToday": 2, "fame": 200, "boatAttacks": 0},
        ],
    },
}
df3 = app.compute_current_race_table(fake_current_dupes)
assert len(df3) == 2, df3
assert df3[df3["Tag"] == "#A"].iloc[0]["Decks joués"] == 8  # garde l'entrée avec le plus de decks
print("compute_current_race_table (déduplication par tag) OK")

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

# --- compute_gdc_series / filter_gdc_series (page Statistiques, 16/08/2026) ---
fake_full_history = [
    {
        "seasonId": "100", "sectionIndex": 0, "createdDate": "20260803T000000.000Z",
        "standings": [
            {"clan": {"tag": "#2Q2Q889", "fame": 12000, "participants": [
                {"tag": "#A", "name": "Alice", "decksUsed": 16, "fame": 8000},
                {"tag": "#B", "name": "Bob", "decksUsed": 8, "fame": 4000},
            ]}}
        ],
    },
    {
        "seasonId": "99", "sectionIndex": 3, "createdDate": "20250727T000000.000Z",
        "standings": [
            {"clan": {"tag": "#2Q2Q889", "fame": 11000, "participants": [
                {"tag": "#A", "name": "Alice", "decksUsed": 14, "fame": 11000},
            ]}}
        ],
    },
]
series = app.compute_gdc_series(fake_full_history, "#2Q2Q889")
assert len(series) == 2
# tri chronologique : la GDC 2025 (plus ancienne) doit être en premier
assert series.iloc[0]["seasonId"] == "99"
assert series.iloc[1]["seasonId"] == "100"
row100 = series[series["seasonId"] == "100"].iloc[0]
assert row100["TauxParticipation"] == round(24 / 32 * 100, 1)  # (16+8)/(2*16)
assert row100["TrophéesClan"] == 12000
assert row100["TrophéeMoyenParJoueur"] == 6000.0
print("compute_gdc_series OK")

# --- régression (16/08/2026 soir) : "clan.fame" officiel de Supercell peu fiable
# sur les sections intermédiaires d'une saison à plusieurs semaines (bug signalé
# par Flo : 2 pics à >100 000 trophées, toutes les autres semaines anormalement
# basses). On doit TOUJOURS sommer les participants, jamais faire confiance au
# champ clan.fame — même s'il est présent avec une valeur (trop basse). ---
fake_unreliable_fame = [
    {
        "seasonId": "133", "sectionIndex": 0, "createdDate": "20260608T000000.000Z",
        "standings": [
            {"clan": {"tag": "#2Q2Q889", "fame": 4000, "participants": [  # "fame" officiel trop bas
                {"tag": "#A", "name": "Alice", "decksUsed": 16, "fame": 60000},
                {"tag": "#B", "name": "Bob", "decksUsed": 16, "fame": 45000},
            ]}}
        ],
    },
]
series_unreliable = app.compute_gdc_series(fake_unreliable_fame, "#2Q2Q889")
row_unreliable = series_unreliable.iloc[0]
assert row_unreliable["TrophéesClan"] == 105000, row_unreliable["TrophéesClan"]  # somme des participants, pas 4000
print("compute_gdc_series (clan.fame officiel ignoré, somme des participants utilisée) OK")

f_last1 = app.filter_gdc_series(series, "last1")
assert len(f_last1) == 1 and f_last1.iloc[0]["seasonId"] == "100"
f_last10 = app.filter_gdc_series(series, "last10")
assert len(f_last10) == 2
f_year = app.filter_gdc_series(series, "year", this_year=2026)
assert len(f_year) == 1 and f_year.iloc[0]["seasonId"] == "100"
f_all = app.filter_gdc_series(series, "all")
assert len(f_all) == 2
print("filter_gdc_series OK")

# --- compute_maxed_cards_in_war_deck (agrège les 4 decks du dernier jour de GDC
# complet, dédup par carte — demande de Flo, 16/08/2026 soir) ---
fake_battlelog = [
    {"type": "PvP", "battleTime": "20260812T080000.000Z", "team": [  # pas un combat GDC -> ignoré
        {"tag": "#A", "cards": [{"name": "Squelettes", "level": 1, "maxLevel": 1}]}
    ]},
    {"type": "riverRacePvP", "battleTime": "20260812T090000.000Z", "team": [
        {"tag": "#A", "cards": [
            {"name": "Chevalier", "level": 14, "maxLevel": 14},
            {"name": "Boule de Feu", "level": 13, "maxLevel": 14},
        ]}
    ]},
    {"type": "riverRacePvP", "battleTime": "20260812T100000.000Z", "team": [
        {"tag": "#A", "cards": [
            {"name": "Chevalier", "level": 14, "maxLevel": 14},  # même carte que ci-dessus -> dédupliquée
            {"name": "Sorcière", "level": 11, "maxLevel": 11},
        ]}
    ]},
    {"type": "riverRacePvP", "battleTime": "20260812T110000.000Z", "team": [
        {"tag": "#A", "cards": [{"name": "Golem", "level": 9, "maxLevel": 12}]}
    ]},
    {"type": "riverRacePvP", "battleTime": "20260812T120000.000Z", "team": [
        {"tag": "#A", "cards": [{"name": "Mini P.E.K.K.A", "level": 14, "maxLevel": 14}]}
    ]},
    {"type": "riverRacePvP", "battleTime": "20260805T090000.000Z", "team": [  # jour plus ancien -> ignoré
        {"tag": "#A", "cards": [{"name": "Golem", "level": 8, "maxLevel": 12}]}
    ]},
]
result = app.compute_maxed_cards_in_war_deck(fake_battlelog, "#A")
assert result is not None
assert result["decks_count"] == 4  # les 4 combats riverRacePvP du 12/08, pas le PvP ni le 05/08
assert result["partial_day"] is False
assert result["total"] == 5  # Chevalier, Boule de Feu, Sorcière, Golem, Mini P.E.K.K.A (Chevalier dédupliqué)
assert result["maxed"] == 3  # Chevalier (14/14), Sorcière (11/11), Mini P.E.K.K.A (14/14)
print("compute_maxed_cards_in_war_deck (agrégation 4 decks + dédup) OK")

# Jour incomplet (moins de 4 combats de GDC trouvés, quel que soit le jour) -> partial_day=True.
fake_battlelog_partial = [
    {"type": "riverRacePvP", "battleTime": "20260812T090000.000Z", "team": [
        {"tag": "#A", "cards": [{"name": "Chevalier", "level": 14, "maxLevel": 14}]}
    ]},
    {"type": "riverRacePvP", "battleTime": "20260812T100000.000Z", "team": [
        {"tag": "#A", "cards": [{"name": "Golem", "level": 9, "maxLevel": 12}]}
    ]},
]
result_partial = app.compute_maxed_cards_in_war_deck(fake_battlelog_partial, "#A")
assert result_partial is not None
assert result_partial["partial_day"] is True
assert result_partial["decks_count"] == 2
assert result_partial["total"] == 2
assert result_partial["maxed"] == 1
print("compute_maxed_cards_in_war_deck (jour partiel) OK")

assert app.compute_maxed_cards_in_war_deck([], "#A") is None
assert app.compute_maxed_cards_in_war_deck([{"type": "PvP", "team": []}], "#A") is None
print("compute_maxed_cards_in_war_deck (cas vides) OK")

# --- member_since ---
since = app.member_since(fake_full_history, "#A", "#2Q2Q889")
assert since == "20250727T000000.000Z"  # la plus ancienne semaine où Alice apparaît
since_unknown = app.member_since(fake_full_history, "#Z", "#2Q2Q889")
assert since_unknown is None
print("member_since OK")

print("\nTOUS LES TESTS PASSENT")
