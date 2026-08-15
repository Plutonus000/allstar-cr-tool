"""
table_style.py — mise en couleur vert/jaune/rouge des tableaux Streamlit
("GDC en cours", "Exclusions"), même principe partout (voir demande de Flo,
15/08/2026 soir) :
- vert  : à jour / rien à signaler
- jaune : entre les deux (ni complet, ni à zéro)
- rouge : rien fait (0 deck / 0 sur la période) — ou une attaque de bateau adverse

Compatible avec les anciennes ET nouvelles versions de pandas : `Styler.map`
n'existe que depuis pandas 2.1, et `Styler.applymap` (l'ancienne méthode) a été
RETIRÉ en pandas 3.0. `requirements.txt` ne fixe qu'un plancher (pandas>=2.0)
donc la version réellement installée chez Flo est inconnue — `style_map()`
détecte laquelle des deux méthodes est disponible à l'exécution plutôt que
d'en supposer une (même prudence que pour `use_container_width` vs `width=`
de Streamlit, voir mémoire du projet).
"""

from __future__ import annotations

GREEN = "background-color: #c6f6d5"
YELLOW = "background-color: #fef3c7"
RED = "background-color: #fecaca"


def style_map(styler, func, subset=None):
    """Styler.map (pandas >= 2.1) avec repli sur Styler.applymap (pandas < 2.1)."""
    if hasattr(styler, "map"):
        return styler.map(func, subset=subset)
    return styler.applymap(func, subset=subset)


def _to_float(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def decks_color(value, expected: int | None) -> str:
    """Vert si >= attendu à ce stade, rouge si 0, jaune entre les deux.
    `expected`=None (hors fenêtre de GDC, ex. mardi/mercredi) -> pas de couleur."""
    if expected is None:
        return ""
    v = _to_float(value)
    if v is None:
        return ""
    if v <= 0:
        return RED
    if v >= expected:
        return GREEN
    return YELLOW


def boat_attacks_color(value) -> str:
    """Rouge s'il y a au moins une attaque de bateau adverse, vert sinon (pas de jaune)."""
    v = _to_float(value)
    if v is None:
        return ""
    return RED if v > 0 else GREEN


def format_int_columns(styler, columns: list[str], na_rep: str = "—"):
    """Force l'affichage de colonnes numériques en entiers (0 décimale),
    avec `na_rep` pour les valeurs manquantes. Corrige l'affichage type
    "12.000000" qui apparaît quand une colonne mélange des None (joueur
    absent d'une des deux fenêtres comparées) et des nombres — pandas bascule
    alors toute la colonne en virgule flottante (signalé par Flo, 15/08/2026)."""
    return styler.format({c: "{:.0f}" for c in columns}, na_rep=na_rep)


def highlight_player_row(styler, tag_col: str, own_tag: str):
    """Encadre (bordure bleue + gras) la ligne du joueur CONNECTÉ dans un
    tableau de classement (demande de Flo, 16/08/2026 — "highlight la ligne
    du joueur connecté" dans tous les classements). Une BORDURE plutôt qu'un
    fond : ça ne risque jamais d'écraser une couleur de statut déjà posée sur
    la ligne par ailleurs (ex. decks/bateaux dans "GDC en cours") — bordure et
    fond sont deux propriétés CSS différentes, elles se cumulent sans conflit
    peu importe l'ordre d'application des styles.

    `tag_col` = nom de la colonne du DataFrame stylé contenant le tag du
    joueur (avec ou sans '#', peu importe — comparaison normalisée)."""
    own_tag_norm = (own_tag or "").strip().upper().lstrip("#")

    def _style_row(row):
        if not own_tag_norm:
            return [""] * len(row)
        cell_tag = str(row.get(tag_col, "")).strip().upper().lstrip("#")
        if cell_tag == own_tag_norm:
            style = "border-top: 2px solid #2a78d6; border-bottom: 2px solid #2a78d6; font-weight: 700;"
            return [style] * len(row)
        return [""] * len(row)

    return styler.apply(_style_row, axis=1)


def paired_decks_color_row(row, decks_col: str, diff_col: str) -> list[str]:
    """Couleur partagée pour une paire (decks joués, différence) d'une même
    ligne : rouge si 0 deck joué, vert si différence nulle (complet), jaune
    entre les deux. Pensé pour `styler.apply(func, axis=1, subset=[decks_col, diff_col])`."""
    decks_v = _to_float(row[decks_col])
    diff_v = _to_float(row[diff_col])
    if decks_v is None or diff_v is None:
        return ["", ""]
    if decks_v <= 0:
        color = RED
    elif diff_v <= 0:
        color = GREEN
    else:
        color = YELLOW
    return [color, color]
