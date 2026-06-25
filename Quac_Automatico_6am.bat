@echo off
REM ============================================================
REM  Quac Automatico — corre solo (tarea programada 6am)
REM  Busca notas nuevas, scrapea, analiza y genera el dashboard.
REM  Log en datos\logs_auto\. No requiere intervencion.
REM ============================================================
cd /d "%~dp0"
set "PYPRO=C:\quac_pro_env\Scripts\python.exe"

if exist "%PYPRO%" (
    "%PYPRO%" "%~dp0automatico.py" --db datos/quac.db --dias 2
) else (
    python "%~dp0automatico.py" --db datos/quac.db --dias 2
)
