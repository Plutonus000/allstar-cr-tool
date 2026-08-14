"""views/stats.py — graphiques du clan (visible par tous)."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import clash_api as api
import data
import logic

# Palette validée (voir skill dataviz) — bleu comme teinte séquentielle par défaut.
BLUE = "#2a78d6"
ORANGE = "#eb6834"
GRID_COLOR = "rgba(0,0,0,0.08)"


def _base_layout(fig: go.Figure, y_title: str) -> go.Figure:
    fig.update_layout(
        template="plotly_white",
        margin=dict(l=10, r=10, t=30, b=10),
        font=dict(size=13),
        showlegend=False,
        xaxis=dict(showgrid=False),
        yaxis=dict(title=y_title, showgrid=True, gridcolor=GRID_COLOR, zeroline=False),
    )
    return fig


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

    # --- Évolution de la Fame du clan par GDC ---
    st.markdown("**Évolution de la Fame du clan par GDC**")
    target = logic.norm_tag(clan_tag)
    evo_rows = []
    for item in reversed(race_log):  # du plus ancien au plus récent
        standing = next(
            (s for s in item.get("standings", []) if logic.norm_tag(s.get("clan", {}).get("tag", "")) == target),
            None,
        )
        if standing:
            evo_rows.append(
                {
                    "GDC": f"#{item.get('seasonId', '?')}",
                    "Fame": standing["clan"].get("fame", 0),
                }
            )
    if evo_rows:
        evo_df = pd.DataFrame(evo_rows)
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=evo_df["GDC"],
                y=evo_df["Fame"],
                mode="lines+markers",
                line=dict(color=BLUE, width=2),
                marker=dict(size=8, color=BLUE),
                hovertemplate="%{x}<br>Fame : %{y}<extra></extra>",
            )
        )
        _base_layout(fig, "Fame du clan")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Pas de données disponibles.")

    st.markdown("---")

    # --- Top 10 joueurs par Fame moyenne ---
    st.markdown("**Top 10 — Fame moyenne par joueur**")
    ranking_df = logic.compute_ranking(race_log, clan_tag, n_races=len(race_log))
    if not ranking_df.empty:
        top10 = ranking_df.nlargest(10, "Fame moy./GDC").sort_values("Fame moy./GDC")
        fig2 = go.Figure()
        fig2.add_trace(
            go.Bar(
                x=top10["Fame moy./GDC"],
                y=top10["Joueur"],
                orientation="h",
                marker=dict(color=BLUE),
                hovertemplate="%{y}<br>Fame moy. : %{x}<extra></extra>",
            )
        )
        fig2.update_layout(
            template="plotly_white",
            margin=dict(l=10, r=10, t=30, b=10),
            font=dict(size=13),
            xaxis=dict(title="Fame moyenne / GDC", showgrid=True, gridcolor=GRID_COLOR),
            yaxis=dict(showgrid=False),
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.caption("Pas de données disponibles.")

    st.markdown("---")

    # --- Distribution de l'assiduité sur la dernière GDC ---
    st.markdown("**Distribution des decks joués — dernière GDC**")
    last_item = race_log[0]
    standing = next(
        (s for s in last_item.get("standings", []) if logic.norm_tag(s.get("clan", {}).get("tag", "")) == target),
        None,
    )
    if standing:
        decks = [p.get("decksUsed", 0) for p in standing["clan"].get("participants", [])]
        fig3 = go.Figure()
        fig3.add_trace(go.Histogram(x=decks, marker=dict(color=BLUE), xbins=dict(start=0, end=17, size=1)))
        fig3.update_layout(
            template="plotly_white",
            margin=dict(l=10, r=10, t=30, b=10),
            font=dict(size=13),
            xaxis=dict(title="Decks joués", showgrid=False),
            yaxis=dict(title="Nombre de joueurs", showgrid=True, gridcolor=GRID_COLOR),
        )
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.caption("Pas de données disponibles pour la dernière GDC.")
