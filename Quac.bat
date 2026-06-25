@echo off
REM Lanzador de ¡Quac! (versión completa, con transformers)
REM Ejecuta la GUI con el Python del entorno 3.12 (torch+pysentimiento+bertopic).
REM Modo ligero por defecto; activa las casillas de transformer/BERTopic para el
REM análisis fino (sentimiento+emoción+ODIO con pysentimiento, tópicos BERTopic).

cd /d "%~dp0"
set "PYPRO=C:\quac_pro_env\Scripts\pythonw.exe"

if exist "%PYPRO%" (
    start "" "%PYPRO%" "%~dp0gui.py"
) else (
    REM Si no existe el entorno completo, cae al Python del sistema (modo ligero).
    start "" pythonw "%~dp0gui.py"
)
