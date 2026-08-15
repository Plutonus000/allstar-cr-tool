"""Tests table_style.py — logique de couleur pure (pas de dépendance Streamlit)."""

from __future__ import annotations

import pandas as pd

import table_style as ts

# --- decks_color ---
assert ts.decks_color(12, 12) == ts.GREEN, "complet -> vert"
assert ts.decks_color(16, 12) == ts.GREEN, "au-dessus de l'attendu -> vert"
assert ts.decks_color(0, 12) == ts.RED, "rien joué -> rouge"
assert ts.decks_color(9, 12) == ts.YELLOW, "entre les deux -> jaune"
assert ts.decks_color(11, 12) == ts.YELLOW
assert ts.decks_color(5, None) == "", "hors fenêtre de GDC -> pas de couleur"
assert ts.decks_color(None, 12) == "", "valeur manquante -> pas de couleur"
print("decks_color OK")

# --- boat_attacks_color ---
assert ts.boat_attacks_color(0) == ts.GREEN
assert ts.boat_attacks_color(1) == ts.RED
assert ts.boat_attacks_color(3) == ts.RED
assert ts.boat_attacks_color(None) == ""
print("boat_attacks_color OK")

# --- paired_decks_color_row ---
row_full = pd.Series({"decks": 16, "diff": 0})
row_zero = pd.Series({"decks": 0, "diff": 16})
row_mid = pd.Series({"decks": 10, "diff": 6})
row_missing = pd.Series({"decks": None, "diff": None})

assert ts.paired_decks_color_row(row_full, "decks", "diff") == [ts.GREEN, ts.GREEN]
assert ts.paired_decks_color_row(row_zero, "decks", "diff") == [ts.RED, ts.RED]
assert ts.paired_decks_color_row(row_mid, "decks", "diff") == [ts.YELLOW, ts.YELLOW]
assert ts.paired_decks_color_row(row_missing, "decks", "diff") == ["", ""]
print("paired_decks_color_row OK")

# --- style_map : fonctionne quelle que soit la méthode disponible (map ou applymap) ---
df = pd.DataFrame({"x": [0, 5, 10]})
styled = ts.style_map(df.style, lambda v: ts.decks_color(v, 10), subset=["x"])
html = styled.to_html()
assert "background-color" in html
print("style_map (compat pandas map/applymap) OK")

# --- format_int_columns : corrige l'affichage "12.000000" (colonnes avec None mélangés) ---
df_mixed = pd.DataFrame({"decks": [12, None, 0], "diff": [4, None, 16]})
styled_mixed = ts.format_int_columns(df_mixed.style, ["decks", "diff"])
html_mixed = styled_mixed.to_html()
assert "12.000000" not in html_mixed
assert ">12<" in html_mixed or ">12.0<" not in html_mixed  # affiché en entier, pas en virgule flottante
assert "—" in html_mixed  # na_rep pour la valeur manquante
print("format_int_columns (pas de virgule flottante, na_rep pour les manquants) OK")

# --- highlight_player_row : bordure sur la ligne du joueur connecté, tag normalisé ---
df_players = pd.DataFrame({"Joueur": ["Alice", "Bob"], "Tag": ["#ABC", "#DEF"]})
styled_own = ts.highlight_player_row(df_players.style, "Tag", "#abc")  # casse/format différents -> normalisé pareil
html_own = styled_own.to_html()
assert "border-top: 2px solid" in html_own
# Aucun tag connu (ex. player_tag absent) -> aucune bordure ajoutée nulle part.
styled_none = ts.highlight_player_row(df_players.style, "Tag", "")
assert "border-top: 2px solid" not in styled_none.to_html()
print("highlight_player_row (bordure sur la ligne du joueur connecté) OK")

print("\nTOUS LES TESTS TABLE_STYLE PASSENT")
