"""Tests de history.py avec le backend local (pas d'appel réseau réel)."""
import streamlit as st

import history
import storage

CLAN_TAG = "#2Q2Q889"


def _reset():
    storage.SEASONS_FILE.write_text("[]")
    storage.PARTICIPANTS_FILE.write_text("[]")
    st.session_state.clear()


def _race(season_id, date, decks_by_tag, section_index=0):
    participants = [
        {"tag": tag, "name": tag, "decksUsed": d, "fame": d * 20, "boatAttacks": 0}
        for tag, d in decks_by_tag.items()
    ]
    return {
        "seasonId": season_id,
        "sectionIndex": section_index,
        "createdDate": date,
        "standings": [
            {"clan": {"tag": CLAN_TAG, "fame": sum(p["fame"] for p in participants), "participants": participants}}
        ],
    }


# --- sync_archive : archive une nouvelle saison ---
_reset()
race_log = [_race(105, "20260801T000000.000Z", {"#A": 16, "#B": 8})]
n = history.sync_archive(race_log, CLAN_TAG)
assert n == 1, n
assert storage.get_archived_week_keys(CLAN_TAG) == {"105_0"}
print("sync_archive (nouvelle saison) OK")

# re-appel dans la même session -> protection session_state, pas de re-scan
n2 = history.sync_archive(race_log, CLAN_TAG)
assert n2 == 0, n2
print("sync_archive (protection re-scan même session) OK")

# nouvelle session simulée, saison déjà archivée -> pas de doublon
st.session_state.clear()
n3 = history.sync_archive(race_log, CLAN_TAG)
assert n3 == 0, n3
assert len(storage.get_archived_participants(CLAN_TAG)) == 2  # pas dupliqué
print("sync_archive (déjà archivé, pas de doublon) OK")

# --- get_full_history : fusion archive + live, le live prime en cas de recoupement ---
_reset()
old_race = _race(100, "20260601T000000.000Z", {"#A": 16})
history.sync_archive([old_race], CLAN_TAG)
st.session_state.clear()
live_race = [_race(105, "20260801T000000.000Z", {"#A": 8})]  # pas encore archivé
full = history.get_full_history(CLAN_TAG, live_race)
season_ids = {str(it["seasonId"]) for it in full}
assert season_ids == {"100", "105"}, season_ids
assert full[0]["seasonId"] == 105  # trié du plus récent au plus ancien
print("get_full_history (fusion archive + live, tri) OK")

# --- participation_rate_all_time sur l'historique fusionné ---
rate = history.participation_rate_all_time(full, "#A", CLAN_TAG)
assert rate == 75.0, rate  # (16 + 8) / (16 + 16) = 75%
print("participation_rate_all_time OK")

# --- participation_rate_for_year : filtre par année civile ---
_reset()
race_2025 = _race(90, "20251015T000000.000Z", {"#A": 16})
race_2026 = _race(100, "20260615T000000.000Z", {"#A": 8})
history.sync_archive([race_2025, race_2026], CLAN_TAG)
st.session_state.clear()
full2 = history.get_full_history(CLAN_TAG, [])
rate_2026 = history.participation_rate_for_year(full2, "#A", CLAN_TAG, 2026)
assert rate_2026 == 50.0, rate_2026
rate_2025 = history.participation_rate_for_year(full2, "#A", CLAN_TAG, 2025)
assert rate_2025 == 100.0, rate_2025
print("participation_rate_for_year (filtre année) OK")

# --- régression : un seasonId peut contenir plusieurs semaines (sectionIndex) ---
# Bug réel corrigé : dédupliquer par seasonId seul fusionnait/perdait des
# semaines distinctes partageant le même seasonId. On vérifie ici que les
# 2 semaines d'un même seasonId sont bien archivées et comptées séparément.
_reset()
race_log_multi = [
    _race(120, "20260815T000000.000Z", {"#A": 16}, section_index=1),  # plus récente
    _race(120, "20260808T000000.000Z", {"#A": 8}, section_index=0),  # même seasonId, semaine précédente
]
n = history.sync_archive(race_log_multi, CLAN_TAG)
assert n == 2, n  # les 2 semaines doivent être archivées, pas fusionnées en 1
assert storage.get_archived_week_keys(CLAN_TAG) == {"120_1", "120_0"}
full_multi = history.get_full_history(CLAN_TAG, [])
assert len(full_multi) == 2, len(full_multi)  # pas fusionnées en un seul item
rate_multi = history.participation_rate_all_time(full_multi, "#A", CLAN_TAG)
assert rate_multi == 75.0, rate_multi  # (16 + 8) / (16 + 16) = 75%, les 2 semaines comptent
print("sync_archive + get_full_history (2 semaines, même seasonId) OK")

_reset()

# --- régression (16/08/2026 soir) : semaine archivée deux fois (ex. race condition
# entre 2 sessions Streamlit concurrentes juste après un redémarrage, cf. bug des
# "2 pics à >100 000 trophées" signalé par Flo sur le graphique Statistiques) ---
_reset()
dup_race = _race(130, "20260822T000000.000Z", {"#A": 16, "#B": 8})
participant_rows = [
    {
        "season_id": "130", "clan_tag": CLAN_TAG, "player_tag": p["tag"], "player_name": p["name"],
        "decks_used": p["decksUsed"], "fame": p["fame"], "boat_attacks": p["boatAttacks"], "section_index": 0,
    }
    for p in dup_race["standings"][0]["clan"]["participants"]
]
# Simule le bug : archive_season() appelé 2 fois pour LA MÊME semaine (au lieu
# d'une seule fois normalement garanti par history.sync_archive), comme 2
# sessions concurrentes pourraient le faire si elles lisent toutes les deux
# "pas encore archivé" avant que l'une des deux écrive.
storage.archive_season("130", "20260822T000000.000Z", CLAN_TAG, participant_rows, section_index=0)
storage.archive_season("130", "20260822T000000.000Z", CLAN_TAG, participant_rows, section_index=0)
full_dup = history.get_full_history(CLAN_TAG, [])
assert len(full_dup) == 1, len(full_dup)  # toujours 1 seule semaine (pas 2 items)
item = full_dup[0]
parts = item["standings"][0]["clan"]["participants"]
assert len(parts) == 2, parts  # dédupliqué : #A et #B, pas 4 lignes
fame_a = next(p["fame"] for p in parts if p["tag"] == "#A")
assert fame_a == 16 * 20, fame_a  # pas doublé (320, pas 640)
assert item["standings"][0]["clan"]["fame"] == 16 * 20 + 8 * 20  # pas doublé non plus (480, pas 960)
print("_rebuild_item_from_archive (semaine archivée 2x, déduplication) OK")

_reset()

# --- régression (16/08/2026 soir) : une erreur sur UNE semaine ne doit plus
# faire planter tout l'archivage des autres semaines du lot, ni empêcher une
# nouvelle tentative à la prochaine interaction de la même session (bug
# signalé par Flo : ancienneté affichée à 4 GDC au lieu de >10, très
# probablement causée par des plantages 429 en pleine boucle d'archivage) ---
_reset()
_orig_archive_season = storage.archive_season


def _flaky_archive_season(season_id, created_date, clan_tag, participant_rows, section_index=0):
    if str(season_id) == "201":  # simule un 429 sur CETTE semaine précise
        raise RuntimeError("429 simulé")
    return _orig_archive_season(season_id, created_date, clan_tag, participant_rows, section_index=section_index)


storage.archive_season = _flaky_archive_season
try:
    race_log_flaky = [
        _race(200, "20260901T000000.000Z", {"#A": 16}, section_index=0),  # doit réussir
        _race(201, "20260908T000000.000Z", {"#A": 16}, section_index=0),  # doit échouer (429 simulé)
        _race(202, "20260915T000000.000Z", {"#A": 16}, section_index=0),  # doit réussir malgré l'échec précédent
    ]
    n = history.sync_archive(race_log_flaky, CLAN_TAG)
    assert n == 2, n  # 200 et 202 archivées, 201 en échec
    keys = storage.get_archived_week_keys(CLAN_TAG)
    assert keys == {"200_0", "202_0"}, keys  # 201 absente, pas de "semaine fantôme"
    # Le clan ne doit PAS être marqué "synced" (il y a eu une erreur) — un
    # nouvel appel dans la même session doit retenter la semaine manquante.
    assert CLAN_TAG not in st.session_state.get(history._SYNCED_FLAG, set())
finally:
    storage.archive_season = _orig_archive_season

# Deuxième passage (comme un rerun Streamlit dans la même session) : la
# semaine 201 doit maintenant être archivée avec succès (plus de panne simulée).
n2 = history.sync_archive(race_log_flaky, CLAN_TAG)
assert n2 == 1, n2  # seulement 201 restait à archiver
keys2 = storage.get_archived_week_keys(CLAN_TAG)
assert keys2 == {"200_0", "201_0", "202_0"}, keys2
assert CLAN_TAG in st.session_state.get(history._SYNCED_FLAG, set())  # cette fois, tout a réussi
print("sync_archive (résilience : 1 échec n'interrompt pas les autres, retenté au passage suivant) OK")

_reset()
print("\nTOUS LES TESTS HISTORY PASSENT")
