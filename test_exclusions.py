"""Tests de exclusions.py (Règles 1-7 redéfinies avec Flo le 15/08/2026 soir).

Note : les tags sont normalisés en interne (majuscules, sans '#') — les
fixtures utilisent des tags avec '#' comme la vraie API, mais les clés des
dicts renvoyés (stats/rapports) sont donc sans '#'.
"""
import exclusions

CLAN_TAG = "#2Q2Q889"


def _gdc(season_id, date, players, section_index=0):
    """players : dict tag -> (decks, boats, fame)."""
    participants = [
        {"tag": tag, "name": tag, "decksUsed": d, "boatAttacks": b, "fame": f}
        for tag, (d, b, f) in players.items()
    ]
    return {
        "seasonId": season_id,
        "sectionIndex": section_index,
        "createdDate": date,
        "standings": [
            {
                "clan": {
                    "tag": CLAN_TAG,
                    "fame": sum(p["fame"] for p in participants),
                    "participants": participants,
                }
            }
        ],
    }


def _history(weeks_chrono):
    """weeks_chrono : liste de GDC du plus ANCIEN au plus RÉCENT (ordre naturel
    d'écriture des tests) -> renvoie l'ordre attendu par exclusions.py (le
    plus récent en premier, comme history.get_full_history())."""
    return list(reversed(weeks_chrono))


# --- compute_player_stats : agrégation de base (inchangé) ---
log = [_gdc(100 - i, f"d{i}", {"#A": (16, 0, 200), "#B": (8, 0, 100)}) for i in range(3)]
stats = exclusions.compute_player_stats(log, CLAN_TAG)
assert stats["A"]["gdc_count"] == 3
assert stats["A"]["total_decks"] == 48
assert stats["A"]["avg_fame"] == 200
assert stats["A"]["assiduity_pct"] == 100.0
assert stats["B"]["assiduity_pct"] == 50.0
print("compute_player_stats OK")


# --- Règle 1 : 1ère GDC visible d'un joueur toujours exemptée ---
weeks = [_gdc(100, "d0", {"#NEW": (2, 0, 50)})]  # arrivée, très incomplet
full_history = _history(weeks)
report = exclusions.build_exclusion_report(full_history, CLAN_TAG)
assert "NEW" not in report["excl"] and "NEW" not in report["warn"] and "NEW" not in report["grace"], report
print("Règle 1 (1ère GDC exemptée, même très incomplète) OK")


# --- Règle 2 : ancienneté <= 5, GDC incomplète -> exclusion directe ---
weeks = [
    _gdc(100, "d0", {"#N2": (16, 0, 200)}),  # tenure 1 (arrivée, exemptée)
    _gdc(101, "d1", {"#N2": (10, 0, 200)}),  # tenure 2, incomplet -> R2 exclusion directe
]
full_history = _history(weeks)
report = exclusions.build_exclusion_report(full_history, CLAN_TAG)
assert "N2" in report["excl"], report
assert report["excl"]["N2"]["bucket"] == "excl"
print("Règle 2 (ancienneté <=5, manquement) -> exclusion directe OK")

# Règle 2 : même joueur mais tous les decks complets -> rien
weeks_ok = [
    _gdc(100, "d0", {"#N3": (16, 0, 200)}),
    _gdc(101, "d1", {"#N3": (16, 0, 200)}),
]
report_ok = exclusions.build_exclusion_report(_history(weeks_ok), CLAN_TAG)
assert "N3" not in report_ok["excl"] and "N3" not in report_ok["warn"] and "N3" not in report_ok["grace"]
print("Règle 2 (ancienneté <=5, tout complet) -> rien OK")


# --- Règle 3 : ancienneté 6-10, GDC incomplète -> avertissement ---
weeks = [_gdc(100 + i, f"d{i}", {"#V6": (16, 0, 200)}) for i in range(5)]  # tenure 1-5, complet
weeks.append(_gdc(105, "d5", {"#V6": (8, 0, 200)}))  # tenure 6, incomplet -> R3 avertissement
full_history = _history(weeks)
report = exclusions.build_exclusion_report(full_history, CLAN_TAG)
assert "V6" in report["warn"], report
assert report["warn"]["V6"]["warning_count"] == 1
print("Règle 3 (ancienneté 6-10, manquement) -> avertissement OK")


# --- Règle 4 : ancienneté >= 10, 1ère GDC incomplète de la fenêtre -> grâce,
# les suivantes -> avertissement ---
weeks = [_gdc(100 + i, f"d{i}", {"#V11": (16, 0, 200)}) for i in range(10)]  # tenure 1-10, complet
weeks.append(_gdc(110, "d10", {"#V11": (8, 0, 200)}))  # tenure 11, incomplet -> R4 grâce
weeks.append(_gdc(111, "d11", {"#V11": (8, 0, 200)}))  # tenure 12, incomplet -> R4 avertissement
full_history = _history(weeks)
report = exclusions.build_exclusion_report(full_history, CLAN_TAG)
assert "V11" in report["warn"], report  # avertissement l'emporte sur la grâce pour le "bucket" affiché
entry = report["warn"]["V11"]
assert entry["warning_count"] == 1, entry
assert entry["grace_count"] == 1, entry
print("Règle 4 (vétéran >10 GDC, 1ère incomplète=grâce, suivante=avertissement) OK")

# --- Règle 4 (cas limite tenure == NB_GDC == 10) : un joueur présent depuis
# le tout début (archive limitée à 10 semaines pour l'instant) doit pouvoir
# obtenir une grâce automatique dès sa 10ème GDC si elle est incomplète —
# bug réel signalé par Flo le 15/08/2026 (Plutonus), corrigé en changeant le
# seuil de "tenure > NB_GDC" à "tenure >= NB_GDC".
weeks_edge = [_gdc(100 + i, f"d{i}", {"#V10": (16, 0, 200)}) for i in range(9)]  # tenure 1-9, complet
weeks_edge.append(_gdc(109, "d9", {"#V10": (8, 0, 200)}))  # tenure 10 pile, incomplet -> R4 grâce (PAS R3 avertissement)
report_edge = exclusions.build_exclusion_report(_history(weeks_edge), CLAN_TAG)
assert "V10" in report_edge["grace"], report_edge
entry_edge = report_edge["grace"]["V10"]
assert entry_edge["grace_count"] == 1, entry_edge
assert entry_edge["warning_count"] == 0, entry_edge
print("Règle 4 (cas limite tenure == NB_GDC == 10) -> grâce automatique (pas avertissement) OK")


# --- Règle 7 : attaque de bateau adverse -> exclusion directe (peu importe l'ancienneté) ---
weeks = [_gdc(100 + i, f"d{i}", {"#BT": (16, 0, 200)}) for i in range(7)]  # tenure 1-7, complet, sans bateau
weeks.append(_gdc(107, "d7", {"#BT": (16, 1, 200)}))  # tenure 8, 1 attaque bateau -> R7 exclusion
full_history = _history(weeks)
report = exclusions.build_exclusion_report(full_history, CLAN_TAG)
assert "BT" in report["excl"], report
print("Règle 7 (attaque de bateau adverse) -> exclusion directe OK")

# Règle 1 + Règle 7 : une attaque de bateau pendant la semaine d'arrivée n'est PAS comptée
weeks_join_boat = [_gdc(100, "d0", {"#BT2": (16, 1, 200)})]  # tenure 1 (arrivée), bateau
report_jb = exclusions.build_exclusion_report(_history(weeks_join_boat), CLAN_TAG)
assert "BT2" not in report_jb["excl"], report_jb
print("Règle 1 (semaine d'arrivée exemptée même avec attaque de bateau) OK")


# --- Règle 5 : 3 grâces glissantes -> 1 avertissement généré, grâce affichée
# plafonnée. La 1ère des 3 GDC incomplètes obtient la grâce AUTOMATIQUE
# (Règle 4, elle est la 1ère incomplète de la fenêtre) ; les 2 suivantes
# auraient normalement été des avertissements (Règle 4), mais un chef les a
# graciées manuellement — 1 grâce auto + 2 grâces manuelles = 3 au total.
weeks = [_gdc(100 + i, f"d{i}", {"#GR3": (16, 0, 200)}) for i in range(10)]  # tenure 1-10, complet
for i in range(3):
    weeks.append(_gdc(110 + i, f"d{10+i}", {"#GR3": (8, 0, 200)}))
full_history = _history(weeks)
manual = {("GR3", "111"), ("GR3", "112")}
report = exclusions.build_exclusion_report(full_history, CLAN_TAG, manual_graces=manual)
assert "GR3" in report["warn"], report  # 3 grâces -> 1 avertissement généré -> bucket "warn"
entry = report["warn"]["GR3"]
assert entry["grace_count"] == 0, entry  # 3 % 3 == 0 (plafonné, converties en totalité)
assert entry["converted_from_grace"] == 1, entry
assert entry["warning_count"] == 1, entry
assert len(entry["grace_weeks"]) == 3, entry
assert sum(w["manual"] for w in entry["grace_weeks"]) == 2  # 2 manuelles + 1 automatique
print("Règle 5 (1 grâce auto + 2 grâces manuelles glissantes -> 1 avertissement généré) OK")


# --- 3 avertissements actifs -> exclusion ; en ressort si le glissement fait
# retomber sous 3 (correction de Flo, 15/08/2026) ---
base_weeks = [_gdc(100 + i, f"d{i}", {"#WRN3": (16, 0, 200)}) for i in range(5)]  # tenure 1-5, complet
base_weeks += [_gdc(105 + i, f"d{5+i}", {"#WRN3": (8, 0, 200)}) for i in range(3)]  # tenure 6,7,8 : 3 avertissements

# À 8 GDC de carrière : les 3 avertissements sont dans la fenêtre des 10
# dernières -> le joueur est dans les EXCLUSIONS, pas les avertissements.
report8 = exclusions.build_exclusion_report(_history(base_weeks), CLAN_TAG)
assert "WRN3" in report8["excl"], report8
assert "WRN3" not in report8["warn"], report8
assert report8["excl"]["WRN3"]["warning_count"] == 3
print("3 avertissements actifs (8 GDC de carrière) -> exclusion OK")

# On ajoute 6 GDC complètes de plus (tenure 9-14) : toujours 14 semaines,
# fenêtre des 10 dernières = tenure 5-14, contient toujours les 3
# avertissements (tenure 6,7,8) -> encore exclusion.
weeks14 = base_weeks + [_gdc(200 + i, f"e{i}", {"#WRN3": (16, 0, 200)}) for i in range(6)]
report14 = exclusions.build_exclusion_report(_history(weeks14), CLAN_TAG)
assert "WRN3" in report14["excl"], report14
print("3 avertissements actifs (14 GDC de carrière, encore dans la fenêtre) -> toujours exclusion OK")

# On ajoute encore 2 GDC complètes (tenure 15, 16) : fenêtre des 10
# dernières = tenure 7-16, le tout 1er avertissement (tenure 6) sort de la
# fenêtre -> il ne reste que 2 avertissements actifs -> retour dans les
# avertissements, plus dans les exclusions.
weeks16 = weeks14 + [_gdc(300 + i, f"f{i}", {"#WRN3": (16, 0, 200)}) for i in range(2)]
report16 = exclusions.build_exclusion_report(_history(weeks16), CLAN_TAG)
assert "WRN3" in report16["warn"], report16
assert "WRN3" not in report16["excl"], report16
assert report16["warn"]["WRN3"]["warning_count"] == 2, report16
print("Glissement : 1er avertissement sort de la fenêtre -> retombe sous 3 -> retour en avertissements OK")


# --- current_tags : un joueur qui a quitté le clan ne doit plus apparaître ---
weeks = [_gdc(100, "d0", {"#LEFT": (16, 0, 200)}), _gdc(101, "d1", {"#LEFT": (2, 0, 200)})]
full_history = _history(weeks)
report_all = exclusions.build_exclusion_report(full_history, CLAN_TAG)
assert "LEFT" in report_all["excl"]
report_filtered = exclusions.build_exclusion_report(full_history, CLAN_TAG, current_tags={"OTHER"})
assert "LEFT" not in report_filtered["excl"] and "LEFT" not in report_filtered["warn"] and "LEFT" not in report_filtered["grace"]
print("current_tags (joueur parti du clan filtré du rapport) OK")


# --- player_recent_report : rapport individuel pour "Mon profil" ---
weeks = [_gdc(100 + i, f"d{i}", {"#ME": (16, 0, 200)}) for i in range(5)]
weeks.append(_gdc(105, "d5", {"#ME": (8, 0, 200)}))  # tenure 6 -> avertissement
full_history = _history(weeks)
individual = exclusions.player_recent_report(full_history, CLAN_TAG, "#ME")
assert individual is not None
assert individual["bucket"] == "warn"
assert individual["warning_count"] == 1
assert exclusions.player_recent_report(full_history, CLAN_TAG, "#GHOST") is None
print("player_recent_report (rapport individuel) OK")


# --- manual_grace_keys (inchangé) ---
keys = exclusions.manual_grace_keys([{"player_tag": "#Vet", "season_id": "100"}])
assert keys == {("VET", "100")}, keys
print("manual_grace_keys OK")


# --- build_tiers : seuils et tailles des tiers Avengers (inchangé) ---
def _stat(tag, gdc_count, score):
    return {"tag": exclusions._norm(tag), "name": tag, "gdc_count": gdc_count, "ranking_score": score}


tier_stats = {}
for i in range(20):
    tag = f"#M{i}"
    tier_stats[exclusions._norm(tag)] = _stat(tag, 7, 100 - i)  # 20 joueurs >= 7 GDC, score décroissant
for i in range(3):
    tag = f"#S{i}"
    tier_stats[exclusions._norm(tag)] = _stat(tag, 5, 50)  # 3 joueurs 4-6 GDC -> SHIELD
for i in range(2):
    tag = f"#X{i}"
    tier_stats[exclusions._norm(tag)] = _stat(tag, 2, 10)  # 2 joueurs <4 GDC -> MULTIVERSE

tiers = exclusions.build_tiers(tier_stats)
assert len(tiers["🏆 AVENGERS ASSEMBLE"]) == 5
assert tiers["🏆 AVENGERS ASSEMBLE"][0]["tag"] == "M0"  # meilleur score en premier
assert len(tiers["⚡ AVENGERS CORE"]) == 10
assert len(tiers["🧠 NEW AVENGERS"]) == 5  # 20 joueurs main : 5+10+5, RESERVE vide
assert len(tiers["🛡️ AVENGERS RESERVE"]) == 0
assert len(tiers["🛡️ S.H.I.E.L.D. ACADEMY"]) == 3
assert len(tiers["🌌 WELCOME TO THE MULTIVERSE"]) == 2
assert exclusions.player_tier("#M0", tiers) == "🏆 AVENGERS ASSEMBLE"
assert exclusions.player_tier("#S0", tiers) == "🛡️ S.H.I.E.L.D. ACADEMY"
print("build_tiers (seuils Avengers) OK")


# --- ranked_list : rang global contigu et cohérent avec les sections ---
ranked = exclusions.ranked_list(tier_stats)
assert len(ranked) == 25, len(ranked)
assert [p["rang"] for p in ranked] == list(range(1, 26))  # 1..25 sans trou ni doublon
assert ranked[0]["tag"] == "M0" and ranked[0]["tier"] == "🏆 AVENGERS ASSEMBLE" and ranked[0]["rang"] == 1
assert ranked[4]["tag"] == "M4" and ranked[4]["tier"] == "🏆 AVENGERS ASSEMBLE" and ranked[4]["rang"] == 5
assert ranked[5]["tag"] == "M5" and ranked[5]["tier"] == "⚡ AVENGERS CORE" and ranked[5]["rang"] == 6
assert ranked[15]["tier"] == "🧠 NEW AVENGERS" and ranked[15]["rang"] == 16
print("ranked_list (rang global cohérent avec les sections) OK")

print("\nTOUS LES TESTS EXCLUSIONS PASSENT")
