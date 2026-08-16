"""views/stats.py — graphiques du clan (visible par tous).

Réécrit le 16/08/2026 (demande de Flo) : taux de participation du clan, trophées
du clan et trophée moyen par joueur, tous les trois en tendance par GDC avec un
filtre de période commun (Dernière GDC / 10 dernières GDC / Année en cours /
All time — voir logic.compute_gdc_series / logic.filter_gdc_series). Remplace
les 3 anciens graphiques (évolution trophées clan, top 10 trophées moyens,
distribution decks dernière GDC) : le contenu est couvert (et étendu) par les
3 graphiques ci-dessous.

Note (16/08/2026, même soir) : la section "Cartes maxées dans les decks de
guerre" initialement prévue ici a été RETIRÉE de cette page à la demande de
Flo — elle reste disponible par joueur sur "Mon profil"/"Suivi joueur" (voir
logic.compute_maxed_cards_in_war_deck, utilisé là-bas uniquement désormais).
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import clash_api as api
import data
import fmt
import history as gdc_history
import logic

BLUE = "#2a78d6"
ORANGE = "#eb6834"
GRID_COLOR = "rgba(0,0,0,0.08)"

# Ordre d'affichage du sélecteur de période -> code interne (voir logic.filter_gdc_series).
PERIOD_OPTIONS = {
    "Dernière GDC": "last1",
    "10 dernières GDC": "last10",
    "Année en cours": "year",
    "All time": "all",
}


def _narrow_selectbox(label: str, options, index: int = 0, key: str | None = None):
    """st.selectbox mais dans une colonne étroite plutôt que pleine largeur —
    même pattern que views/ranking.py/_narrow_selectbox et
    views/suivi.py/_narrow_text_input (demande de Flo, 16/08/2026 soir, pour
    le sélecteur de période)."""
    col, _ = st.columns([1, 3])
    with col:
        return st.selectbox(label, options=options, index=index, key=key)


# Config Plotly commune : désactive le zoom au scroll/pincement et le zoom au
# double-clic/double-tap (demande de Flo, 16/08/2026 soir — "quand on clique
# sur les graphes, ça zoome, ou bien quand on essaie de scroller sur mobile").
# Combiné à dragmode=False dans _base_layout(), le glisser tactile à l'intérieur
# du graphique ne capture plus le scroll de la page.
_PLOTLY_CONFIG = {"scrollZoom": False, "doubleClick": False, "displayModeBar": False}


def _base_layout(fig: go.Figure, y_title: str) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=10, r=10, t=30, b=10),
        font=dict(size=13),
        showlegend=False,
        dragmode=False,
        xaxis=dict(showgrid=False, fixedrange=True),
        # rangemode="tozero" : l'ordonnée part toujours de 0 plutôt que de
        # zoomer automatiquement sur la plage des valeurs (demande de Flo,
        # 16/08/2026 soir, pour "Trophées du clan"/"Trophées moyens par
        # joueur" — "Taux de participation" a déjà sa propre plage fixe
        # [0, 100] passée explicitement via y_range, qui prévaut sur ceci).
        yaxis=dict(
            title=y_title, showgrid=True, gridcolor=GRID_COLOR, zeroline=False,
            fixedrange=True, rangemode="tozero",
        ),
    )
    return fig


def _render_trend(
    title: str, df: pd.DataFrame, y_col: str, y_title: str, hover_label: str, suffix: str = "",
    y_range: tuple[float, float] | None = None,
) -> None:
    """Graphique en ligne si plusieurs points, sinon un simple st.metric (une
    "tendance" à un seul point n'a pas de sens visuellement — cas "Dernière GDC").
    `y_range` force une plage fixe pour l'axe Y plutôt que de laisser Plotly
    zoomer automatiquement sur la plage des valeurs (demande de Flo, 16/08/2026
    soir, sur le graphique du taux de participation — l'axe partait de ~35% —
    puis précisé : 0 à 100 puisque c'est un pourcentage)."""
    st.markdown(f"**{title}**")
    clean = df.dropna(subset=[y_col])
    if clean.empty:
        st.caption("Pas de données disponibles pour cette période.")
        return
    if len(clean) == 1:
        row = clean.iloc[0]
        st.metric(title, f"{row[y_col]}{suffix}")
        st.caption(f"GDC du {fmt.format_date(row['createdDate'])}.")
        return
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=clean["Label"],
            y=clean[y_col],
            mode="lines+markers",
            line=dict(color=BLUE, width=2),
            marker=dict(size=8, color=BLUE),
            hovertemplate=f"%{{x}}<br>{hover_label} : %{{y}}{suffix}<extra></extra>",
        )
    )
    _base_layout(fig, y_title)
    if y_range is not None:
        fig.update_yaxes(range=list(y_range))
    st.plotly_chart(fig, use_container_width=True, config=_PLOTLY_CONFIG)


def render(ctx: dict) -> None:
    st.subheader("📊 Statistiques")
    clan_tag = ctx["clan_tag"]

    try:
        race_log = data.load_race_log(clan_tag, limit=10)
    except api.ClashAPIError as exc:
        st.error(str(exc))
        return

    if not race_log:
        st.info("Pas assez de données pour générer des graphiques.")
        return

    # Archive au fil de l'eau (comme "Mon profil") pour dépasser la fenêtre de
    # 10 GDC de l'API sur les filtres "Année en cours" / "All time".
    gdc_history.sync_archive(race_log, clan_tag)
    full_history = gdc_history.get_full_history(clan_tag, race_log)

    series = logic.compute_gdc_series(full_history, clan_tag)
    if series.empty:
        st.info("Pas assez de données pour générer des graphiques.")
        return

    period_label = _narrow_selectbox("Période", options=list(PERIOD_OPTIONS.keys()), index=1, key="stats_period")
    period = PERIOD_OPTIONS[period_label]
    filtered = logic.filter_gdc_series(series, period, this_year=gdc_history.current_year())
    st.caption(f"{len(filtered)} GDC prise(s) en compte sur cette période.")

    st.markdown("---")
    _render_trend(
        "Taux de participation du clan", filtered, "TauxParticipation", "Taux de participation (%)",
        "Taux", suffix="%", y_range=(0, 100),
    )

    st.markdown("---")
    _render_trend(
        "Trophées du clan après chaque GDC", filtered, "TrophéesClan", "Trophées du clan", "Trophées",
    )

    st.markdown("---")
    _render_trend(
        "Trophées moyens par joueur", filtered, "TrophéeMoyenParJoueur", "Trophées moy. / joueur", "Trophées moy.",
    )
