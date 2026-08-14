@echo off
cd /d "%~dp0"
echo Verification des dependances...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo [ERREUR] Impossible d'installer les dependances. Verifie que Python est installe.
    pause
    exit /b 1
)
echo.
python hash_password.py
echo.
echo === Termine — appuie sur une touche pour fermer ===
pause
