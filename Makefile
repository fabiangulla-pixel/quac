# ¡Quac! — tareas de calidad. Usa el Python del venv PRO.
PY := C:/quac_pro_env/Scripts/python.exe
RUFF := C:/quac_pro_env/Scripts/ruff.exe

.PHONY: check lint fmt fmt-check test hooks

check: lint fmt-check test ## Lint + formato + tests (lo que corre el hook)

lint: ## Reglas de ruff
	$(RUFF) check .

fmt: ## Formatear el código
	$(RUFF) format .

fmt-check: ## Verificar formato sin modificar
	$(RUFF) format --check .

test: ## Suite de tests
	$(PY) -m pytest tests/ -q

hooks: ## Instalar el hook de pre-commit
	$(PY) scripts/install_hooks.py
