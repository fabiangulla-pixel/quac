# scripts/_experimentos

Scripts puntuales de mantenimiento o pruebas manuales. **No son parte del producto**
y no se importan desde la app. Quedan aquí para referencia y para no ensuciar la raíz.

- `regen_dashboard_bd.py` — Regenera `datos/quac.dashboard.html` corriendo el pipeline
  de análisis (limpieza estricta) sobre la BD ya existente, sin re-buscar ni re-scrapear.
  Reutiliza `automatico.analizar_y_dashboard`. Útil tras cambiar `dashboard.py`/`studyInfo.js`
  para ver el resultado sin esperar un scraping. Correr con el venv PRO:
  `C:/quac_pro_env/Scripts/python.exe -u scripts/_experimentos/regen_dashboard_bd.py`
