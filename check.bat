@echo off
REM ¡Quac! — verificacion de calidad (lint + formato + tests).
REM Equivalente a `make check` para consola Windows. Sin caracteres unicode
REM para no romper en cp1252.
setlocal
set PY=C:/quac_pro_env/Scripts/python.exe
set RUFF=C:/quac_pro_env/Scripts/ruff.exe

echo [1/3] Lint (ruff check)...
"%RUFF%" check .
if errorlevel 1 goto :fallo

echo [2/3] Formato (ruff format --check)...
"%RUFF%" format --check .
if errorlevel 1 goto :fallo

echo [3/3] Tests (pytest)...
"%PY%" -m pytest tests/ -q
if errorlevel 1 goto :fallo

echo.
echo [OK] Todo paso: lint + formato + tests.
exit /b 0

:fallo
echo.
echo [FALLO] La verificacion no paso. Revisa la salida de arriba.
exit /b 1
