"""
migrate_to_sheets.py — copie les comptes/demandes du stockage JSON local vers
Google Sheets, une fois celui-ci configuré dans .env.

À lancer une seule fois, seulement si tu avais déjà des comptes créés en
local (accounts.json) que tu ne veux pas recréer à la main après le passage
à Google Sheets. Si tu n'as qu'un compte ou deux, il est aussi simple de les
recréer directement via create_account.bat / la demande d'accès dans l'appli.
"""

import storage


def main() -> None:
    if storage.backend_name() != "sheets":
        print(
            "Google Sheets n'est pas (encore) configuré — vérifie GOOGLE_SERVICE_ACCOUNT_FILE "
            "et GOOGLE_SHEET_ID dans ton .env avant de relancer ce script."
        )
        raise SystemExit(1)

    local_accounts = storage._local_get_accounts()
    local_requests = storage._local_get_requests()

    if not local_accounts and not local_requests:
        print("Rien à migrer (accounts.json / access_requests.json vides ou absents).")
        return

    print(f"{len(local_accounts)} compte(s) et {len(local_requests)} demande(s) à migrer vers Google Sheets...")

    for username, account in local_accounts.items():
        storage._sheets_upsert_account(username, account)
        print(f"  ✅ compte migré : {username}")

    for req in local_requests:
        storage._sheets_add_request(req)
        print(f"  ✅ demande migrée : {req['pseudo_submitted']}")

    print(
        "\nMigration terminée. accounts.json / access_requests.json ne sont plus utilisés "
        "tant que Google Sheets reste configuré — tu peux les garder comme sauvegarde ou les supprimer."
    )


if __name__ == "__main__":
    main()
