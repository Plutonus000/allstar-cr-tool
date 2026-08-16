"""views/help.py — Aide / Comment ça marche ? (visible par tous).

Réécrite de façon exhaustive le 16/08/2026 (demande de Flo, une fois la page
Statistiques finalisée) : détaille maintenant TOUTES les pages de l'outil,
organisées en catégories selon ce à quoi la personne connectée a droit — les
sections "chefs" et "admin" ne s'affichent que si `ctx["is_chef"]`/`ctx["is_admin"]`
sont vrais, exactement comme le menu de gauche lui-même (voir app.py::PAGE_DEFS).

Rappel (15/08/2026) : ne jamais citer le nom réel de Flo ici (ni ailleurs dans
l'outil) — utiliser son pseudo Clash Royale "Plutonus" si une mention est
nécessaire, puisque cette page est visible par tout le clan.
"""

from __future__ import annotations

import streamlit as st


def render(ctx: dict) -> None:
    is_chef = bool(ctx.get("is_chef"))
    is_admin = bool(ctx.get("is_admin"))

    st.subheader("❓ Aide — Comment ça marche ?")
    st.write(
        "Ce guide décrit chaque page du menu de gauche. Certaines sections ci-dessous ne "
        "s'affichent que si tu y as accès — donc si une page mentionnée par un autre membre "
        "n'apparaît pas ici pour toi, c'est normal : elle ne t'est pas destinée."
    )

    # -------------------------------------------------------------------
    # Catégorie 1 — accessible à TOUT LE MONDE
    # -------------------------------------------------------------------
    st.markdown("## 📋 Pages accessibles à tout le monde")

    st.markdown("### 🏠 Mon profil")
    st.write(
        "Ta situation personnelle dans le clan, en un coup d'œil :"
    )
    st.markdown(
        "- **Série actuelle** : nombre de GDC consécutives (en partant de la plus récente) où "
        "tu as joué tes 4 decks chaque jour. Une seule GDC incomplète ou une absence remet le "
        "compteur à zéro.\n"
        "- **Taux de participation** : decks joués / decks possibles, affiché sur 3 fenêtres — "
        "les 10 dernières GDC (directement via l'API), l'année civile en cours, et « all-time » "
        "(depuis que l'outil archive les GDC). L'API officielle ne conserve que 10 semaines "
        "d'historique ; les deux autres chiffres se basent sur l'archive de l'outil, qui "
        "s'enrichit semaine après semaine.\n"
        "- **Rôle actuel** et **position au classement** (mêmes règles que l'onglet Classement).\n"
        "- **Membre depuis** : la première semaine de GDC où l'outil retrouve ta trace dans le "
        "clan — une approximation basée sur l'archive, pas une vraie date d'entrée (l'API ne "
        "l'expose pas). Plus l'outil tourne depuis longtemps, plus cette date remonte loin.\n"
        "- **Cartes maxées (deck de GDC)** : nombre de cartes déjà au niveau maximum parmi "
        "celles utilisées sur tes 4 decks du dernier jour de GDC complet joué (une carte "
        "réutilisée sur plusieurs decks n'est comptée qu'une fois). Donnée instantanée, pas "
        "d'historique.\n"
        "- **Progression Membre → Aîné → Chef adjoint** : une frise visuelle de ta série "
        "d'assiduité par rapport aux paliers de promotion.\n"
        "- **Avertissements et grâces en cours** (10 dernières GDC glissantes) : le détail de "
        "chaque avertissement/grâce actif, avec la raison.\n"
    )

    st.markdown("### 🏆 Classement")
    st.write(
        "Le classement du clan basé sur les Trophées (la donnée de participation en GDC la "
        "plus proche des « trophées gagnés »), regroupé par paliers façon « Avengers ». Ta "
        "propre ligne est mise en évidence (bordure bleue) dans tous les tableaux pour te "
        "repérer facilement."
    )
    st.markdown(
        "- **Onglet Classement** : le classement complet par palier, avec une recherche et un "
        "bouton pour publier le classement sur Discord (visible par les chefs).\n"
        "- **Onglet GDC en cours** : qui a encore des decks à jouer cette semaine.\n"
        "- **Onglet Historique GDC** : les GDC passées, regroupées par saison (jusqu'à 4 "
        "semaines par saison affichées d'un coup, avec la période exacte en date).\n"
    )

    st.markdown("### 📊 Statistiques")
    st.write(
        "Des graphiques sur la santé et l'évolution du clan au fil des GDC, avec un filtre de "
        "période commun en haut de page : Dernière GDC, 10 dernières GDC, Année en cours, ou "
        "All time (basé sur l'archive de l'outil, comme pour « Mon profil »)."
    )
    st.markdown(
        "- **Taux de participation du clan** : decks joués par tout le monde / decks "
        "théoriquement possibles (nombre de participants × 16), en %.\n"
        "- **Trophées du clan après chaque GDC** : évolution du score total du clan.\n"
        "- **Trophées moyens par joueur** : le score total du clan divisé par le nombre de "
        "participants, GDC par GDC.\n"
    )
    st.caption(
        "Si le filtre ne laisse qu'une seule GDC (« Dernière GDC »), le chiffre s'affiche "
        "directement plutôt qu'en graphique — une courbe à un seul point n'a pas grand intérêt."
    )

    st.markdown("### 💡 Suggestions")
    st.write(
        "Pour logger une idée d'amélioration ou signaler un bug — voir la section "
        "« Une question, un bug, une idée ? » tout en bas de cette page pour les détails."
    )

    # -------------------------------------------------------------------
    # Catégorie 2 — réservée aux chefs et chefs adjoints
    # -------------------------------------------------------------------
    if is_chef:
        st.markdown("## 🛡️ Pages réservées aux chefs et chefs adjoints")
        st.caption("Cette section n'apparaît que pour les comptes Chef ou Chef adjoint en jeu.")

        st.markdown("### 🛡️ Suivi clan")
        st.write("Le tableau de bord des chefs, en 3 onglets :")
        st.markdown(
            "- **📊 Rapport (stats GDC en cours)** : les decks joués/non-joués et les attaques "
            "de bateaux adverses, sur la dernière GDC et sur les 10 dernières.\n"
            "- **🔴 Exclusions** : les recommandations basées sur le règlement du clan, sur 3 "
            "niveaux — exclusions, avertissements, puis grâces (automatiques ou manuelles) — "
            "calculées sur les 10 dernières GDC glissantes de chaque joueur. Un joueur avec "
            "10 GDC d'ancienneté ou plus dans le clan obtient une grâce automatique en cas de "
            "GDC incomplète (avant ce seuil, c'est un avertissement direct). Un chef peut aussi "
            "accorder une grâce manuelle à tout moment, avec un commentaire optionnel.\n"
            "- **⭐ Promotions** : les joueurs actuellement éligibles Aîné ou Chef adjoint "
            "(séries de GDC à 100% d'assiduité). La promotion elle-même reste manuelle, en jeu "
            "— l'outil ne fait que la détection.\n"
        )

        st.markdown("### 🔍 Suivi joueur")
        st.write(
            "La même page que « Mon profil », mais pour n'importe quel membre du clan de ton "
            "choix (liste déroulante) — pratique pour vérifier la situation d'un joueur sans "
            "lui demander de se connecter lui-même."
        )

        st.markdown("### 📥 Demandes d'accès")
        st.write(
            "Les demandes de connexion des joueurs du clan à valider — l'outil essaie de faire "
            "correspondre automatiquement le pseudo saisi au bon membre du clan ; sinon, un "
            "chef choisit manuellement le bon joueur avant de valider."
        )

    # -------------------------------------------------------------------
    # Catégorie 3 — réservée à l'admin
    # -------------------------------------------------------------------
    if is_admin:
        st.markdown("## 🔑 Page réservée à l'admin")
        st.caption(
            "Cette section n'apparaît que pour le compte ayant le statut admin — un statut "
            "propre à l'outil, indépendant du rôle en jeu (même un chef ou chef adjoint n'y a "
            "pas accès sans ce statut)."
        )

        st.markdown("### 👥 Suivi Comptes")
        st.write(
            "Gestion des comptes ayant accès à l'outil : liste de tous les comptes (avec leur "
            "statut, leur date de création), attribution ou retrait du statut admin à un autre "
            "compte, et révocation manuelle d'un accès si besoin. L'admin voit aussi TOUTES les "
            "suggestions envoyées par les autres joueurs dans l'onglet 💡 Suggestions (les "
            "autres joueurs ne voient que les leurs)."
        )

    # -------------------------------------------------------------------
    st.markdown("---")
    st.markdown("### Une question, un bug, une idée ?")
    st.write(
        "Utilise l'onglet **💡 Suggestions** dans le menu de gauche pour logger ta question, "
        "ton bug ou ton idée d'amélioration — l'outil évolue en continu grâce à vos retours. "
        "Si tu es admin, tu retrouveras toutes les suggestions envoyées par le clan dans ce "
        "même onglet."
    )
