@echo off
cd /d "%~dp0"

if not exist ".env" (
    echo Creation du fichier .env avec ta cle API...
    (
        echo CLASH_API_KEY=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiIsImtpZCI6IjI4YTMxOGY3LTAwMDAtYTFlYi03ZmExLTJjNzQzM2M2Y2NhNSJ9.eyJpc3MiOiJzdXBlcmNlbGwiLCJhdWQiOiJzdXBlcmNlbGw6Z2FtZWFwaSIsImp0aSI6IjU5NDczOTNmLTBiMzUtNGNiNS1iYTMzLWViMTYwNzc0YWM3OCIsImlhdCI6MTc4NjczNDg2Niwic3ViIjoiZGV2ZWxvcGVyLzJhNzA3YzY5LWJiNDktNGYzMC1hYWU2LWVmOThjOTk4NDNlOCIsInNjb3BlcyI6WyJyb3lhbGUiXSwibGltaXRzIjpbeyJ0aWVyIjoiZGV2ZWxvcGVyL3NpbHZlciIsInR5cGUiOiJ0aHJvdHRsaW5nIn0seyJjaWRycyI6WyI0NS43OS4yMTguNzkiXSwidHlwZSI6ImNsaWVudCJ9XX0.imjVyXujQrxy_xmVnEpCiZSudoPW6brm4_wg7O0LkdNDAF2xNQ7fKeqB-pFCsA7Glhx9AbxWtV1HHpa-ExiVkA
        echo CLAN_TAG=#2Q2Q889
    ) > .env
)

echo Installation/mise a jour des dependances...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo [ERREUR] L'installation des dependances a echoue.
    echo Verifie que Python est bien installe et accessible via la commande "python".
    pause
    exit /b 1
)

echo Lancement de l'outil ALLSTAR...
python -m streamlit run app.py
pause
