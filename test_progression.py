"""Tests de progression.py avec des données factices (pas d'appel réseau)."""
import progression as prog

CLAN_TAG = "#2Q2Q889"


def _race(season_id, date, decks_by_tag, present_tags=None):
    present_tags = present_tags if present_tags is not None else list(decks_by_tag.keys())
    participants = [
        {"tag": tag, "name": tag, "decksUsed": decks_by_tag.get(tag, 0)}
        for tag in present_tags
    ]
    return {
        "seasonId": season_id,
        "createdDate": date,
        "standings": [
            {"clan": {"tag": CLAN_TAG, "name": "ALLSTAR", "participants": participants}}
        ],
    }


# --- streak parfait sur 6 semaines pour #A ---
log = [_race(100 - i, f"day{i}", {"#A": 16, "#B": 16}) for i in range(6)]
streak, hist = prog.compute_participation_streak(log, "#A", CLAN_TAG)
assert streak == 6, streak
assert len(hist) == 6
print("streak parfait OK")

# --- streak cassé à la 3e semaine en remontant ---
log2 = [
    _race(105, "d0", {"#A": 16}),
    _race(104, "d1", {"#A": 16}),
    _race(103, "d2", {"#A": 12}),  # incomplet -> casse la série
    _race(102, "d3", {"#A": 16}),
    _race(101, "d4", {"#A": 16}),
]
streak2, _ = prog.compute_participation_streak(log2, "#A", CLAN_TAG)
assert streak2 == 2, streak2  # seulement d0 et d1 comptent avant la casse
print("streak cassé OK")

# --- absence = casse la série aussi ---
log3 = [
    _race(105, "d0", {"#A": 16}),
    _race(104, "d1", {}, present_tags=[]),  # #A absent
    _race(103, "d2", {"#A": 16}),
]
streak3, hist3 = prog.compute_participation_streak(log3, "#A", CLAN_TAG)
assert streak3 == 1, streak3
assert hist3[1]["present"] is False
print("absence casse la série OK")

# --- éligibilité ---
status5 = prog.eligibility_status(5)
assert status5["elder_eligible"] is True
assert status5["coleader_eligible"] is False
assert status5["weeks_to_coleader"] == 5
status10 = prog.eligibility_status(10)
assert status10["coleader_eligible"] is True
print("eligibility_status OK")

# --- participation_rate ---
log4 = [_race(100 - i, f"d{i}", {"#A": 16 if i % 2 == 0 else 8}) for i in range(10)]
rate = prog.participation_rate(log4, "#A", CLAN_TAG, n_races=10)
assert rate == 75.0, rate  # (5*16 + 5*8) / (10*16) = 120/160 = 75%
print("participation_rate OK")

# --- find_rule_violations ---
log5 = [_race(100, "d0", {"#A": 16, "#B": 10, "#C": 16})]
violations = prog.find_rule_violations(log5, CLAN_TAG, n_races=1)
assert len(violations) == 1 and violations[0]["player_tag"] == "#B"
print("find_rule_violations OK")

# --- find_promotable_players ---
members = [
    {"tag": "#A", "name": "Alice", "role": "member"},
    {"tag": "#B", "name": "Bob", "role": "elder"},
    {"tag": "#C", "name": "Carla", "role": "leader"},
]
log6 = [_race(100 - i, f"d{i}", {"#A": 16, "#B": 16, "#C": 16}) for i in range(10)]
promotable = prog.find_promotable_players(members, log6, CLAN_TAG)
names = {p["name"]: p["next_rank"] for p in promotable}
assert names.get("Alice") == "Aîné"
assert names.get("Bob") == "Chef adjoint"
assert "Carla" not in names  # déjà leader, exclue
print("find_promotable_players OK")

print("\nTOUS LES TESTS PROGRESSION PASSENT")
