"""
create_local_account.py (exécuté via hash_password.py / create_account.bat)
— crée un compte directement, sans passer par le flux de demande d'accès.

À utiliser uniquement pour amorcer le tout premier compte (toi) : il faut au
moins un chef déjà connecté pour valider les demandes suivantes. Tous les
autres membres du clan passeront ensuite par "Demander mon accès" dans l'appli.

Le mot de passe tapé n'est jamais affiché ni enregistré en clair — seul son
hash (bcrypt, non réversible) est stocké dans accounts.json (ou Google Sheets
si déjà configuré).
"""

import getpass
import sys

import bcrypt

import clash_api as api
import storage


def main() -> None:
    print("=== Création d'un compte (bootstrap admin) ===\n")

    pseudo = input("Ton pseudo Clash Royale (tel qu'affiché dans le jeu) : ").strip()
    player_tag = input("Ton tag joueur (ex: #ABC123, visible dans ton profil en jeu) : ").strip()
    if not player_tag.startswith("#"):
        player_tag = "#" + player_tag

    print("\nVérification de ton appartenance au clan...")
    try:
        members = api.get_clan_members()
        norm = player_tag.upper().lstrip("#")
        match = next((m for m in members if m.get("tag", "").upper().lstrip("#") == norm), None)
    except api.ClashAPIError as exc:
        print(f"⚠️  Impossible de vérifier via l'API pour le moment ({exc}).")
        print("Le compte sera quand même créé, mais vérifie que le tag est correct.")
        match = None

    if match:
        print(f"✅ Trouvé dans le clan : {match.get('name')} — rôle actuel : {match.get('role')}")
    else:
        confirm = input("⚠️  Ce tag n'a pas été trouvé dans le clan. Continuer quand même ? (o/n) : ")
        if confirm.strip().lower() != "o":
            print("Annulé.")
            sys.exit(1)

    username = input(f"\nIdentifiant de connexion [{pseudo.lower()}] : ").strip() or pseudo.lower()
    password = getpass.getpass("Mot de passe (invisible en tapant) : ")
    confirm_pw = getpass.getpass("Confirme le mot de passe : ")

    if password != confirm_pw:
        print("Les deux mots de passe ne correspondent pas. Rien n'a été fait.")
        sys.exit(1)
    if len(password) < 8:
        print("⚠️  Mot de passe très court — recommandé : 8 caractères minimum.")

    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    storage.create_account(username=username, name=pseudo, password_hash=hashed, player_tag=player_tag)

    print(f"\n✅ Compte '{username}' créé (stockage : {storage.backend_name()}).")
    if storage.backend_name() == "local":
        print("Pense à commit + push accounts.json si l'appli est déployée sur Streamlit Cloud.")


if __name__ == "__main__":
    main()
